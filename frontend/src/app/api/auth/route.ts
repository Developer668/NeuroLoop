import { NextRequest, NextResponse } from "next/server";
import { publicOrigin, sameOrigin } from "@/lib/request-origin";
export const runtime = "nodejs";
const backend = process.env.NEUROLOOP_INTERNAL_API || "http://127.0.0.1:8010";
export async function POST(request: NextRequest) {
  if (!sameOrigin(request))
    return NextResponse.json(
      { detail: "Cross-origin authentication denied" },
      { status: 403 },
    );
  try {
    const body = await request.json();
    let upstream: Response;
    if (body.mode === "local") {
      const key = process.env.NEUROLOOP_LOCAL_BOOTSTRAP_TOKEN;
      if (
        !["localhost", "127.0.0.1"].includes(
          new URL(publicOrigin(request)).hostname,
        ) ||
        !key
      )
        return NextResponse.json(
          {
            detail:
              "Local bootstrap is not configured. Run scripts/setup.py or sign in with an operator key.",
          },
          { status: 403 },
        );
      upstream = await fetch(backend + "/auth/local", {
        method: "POST",
        headers: { "X-NeuroLoop-Bootstrap": key },
        cache: "no-store",
        signal: AbortSignal.timeout(10000),
      });
    } else {
      if (typeof body.token !== "string" || body.token.length > 256)
        return NextResponse.json(
          { detail: "Valid operator key required" },
          { status: 400 },
        );
      upstream = await fetch(backend + "/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: body.token }),
        cache: "no-store",
        signal: AbortSignal.timeout(10000),
      });
    }
    if (!upstream.ok)
      return NextResponse.json(
        { detail: "Backend did not authorize this session" },
        { status: upstream.status },
      );
    const data = await upstream.json();
    const response = NextResponse.json({ authenticated: true });
    response.cookies.set("neuroloop_session", data.token, {
      httpOnly: true,
      secure: new URL(publicOrigin(request)).protocol === "https:",
      sameSite: "strict",
      path: "/",
      maxAge: data.expires_in || 28800,
    });
    return response;
  } catch {
    return NextResponse.json(
      {
        detail:
          "Cannot reach the NeuroLoop API. Start the new backend and retry.",
      },
      { status: 503 },
    );
  }
}
export async function DELETE(request: NextRequest) {
  if (!sameOrigin(request))
    return NextResponse.json(
      { detail: "Cross-origin sign-out denied" },
      { status: 403 },
    );
  const token = request.cookies.get("neuroloop_session")?.value;
  if (token) {
    try {
      const r = await fetch(backend + "/auth/revoke", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        signal: AbortSignal.timeout(10000),
      });
      if (!r.ok && r.status !== 401) throw new Error();
    } catch {
      return NextResponse.json(
        { detail: "Backend unavailable; session has not been revoked. Retry." },
        { status: 503 },
      );
    }
  }
  const response = NextResponse.json({ authenticated: false });
  response.cookies.set("neuroloop_session", "", {
    httpOnly: true,
    path: "/",
    maxAge: 0,
  });
  return response;
}
