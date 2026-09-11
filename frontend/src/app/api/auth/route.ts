import { NextRequest, NextResponse } from "next/server";
export const runtime = "nodejs";
const backend = process.env.NEUROLOOP_INTERNAL_API || "http://127.0.0.1:8010";

export async function POST(request: NextRequest) {
  const origin = request.headers.get("origin");
  if (origin && origin !== request.nextUrl.origin)
    return NextResponse.json(
      { detail: "Cross-origin authentication is not permitted" },
      { status: 403 },
    );
  try {
    const body = await request.json();
    let token: string;
    if (body.mode === "local") {
      if (!["localhost", "127.0.0.1"].includes(request.nextUrl.hostname))
        return NextResponse.json(
          { detail: "Local access is unavailable on a public hostname" },
          { status: 403 },
        );
      const response = await fetch(backend + "/auth/local", {
        method: "POST",
        headers: {
          Origin: request.nextUrl.origin,
          "X-NeuroLoop-Local": "browser",
        },
        cache: "no-store",
        signal: AbortSignal.timeout(10000),
      });
      if (!response.ok)
        return NextResponse.json(
          {
            detail: "The local backend did not authorize this browser session",
          },
          { status: response.status },
        );
      token = (await response.json()).token;
    } else {
      if (typeof body.token !== "string" || body.token.length > 256)
        return NextResponse.json(
          { detail: "A valid access token is required" },
          { status: 400 },
        );
      token = body.token;
      const response = await fetch(backend + "/api/capabilities", {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
        signal: AbortSignal.timeout(10000),
      });
      if (!response.ok)
        return NextResponse.json(
          { detail: "Access token was not accepted" },
          { status: 401 },
        );
    }
    const response = NextResponse.json({ authenticated: true });
    response.cookies.set("neuroloop_session", token, {
      httpOnly: true,
      secure: request.nextUrl.protocol === "https:",
      sameSite: "strict",
      path: "/",
      maxAge: 28800,
    });
    return response;
  } catch {
    return NextResponse.json(
      {
        detail:
          "Cannot reach the NeuroLoop backend. Start the API service and try again.",
      },
      { status: 503 },
    );
  }
}
export async function DELETE(request: NextRequest) {
  const origin = request.headers.get("origin");
  if (origin && origin !== request.nextUrl.origin) return NextResponse.json({detail:"Cross-origin sign-out is not permitted"},{status:403});
  const token = request.cookies.get("neuroloop_session")?.value;
  if (token) {
    try {
      const revoked = await fetch(backend + "/auth/revoke", {method:"POST",headers:{Authorization:`Bearer ${token}`},signal:AbortSignal.timeout(10000)});
      if (!revoked.ok && revoked.status !== 401) throw new Error("Revocation failed");
    } catch {
      return NextResponse.json({detail:"Could not revoke the session. Retry when the backend is reachable."},{status:503});
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
