import { NextRequest, NextResponse } from "next/server";
import { sameOrigin } from "@/lib/request-origin";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const backend = process.env.NEUROLOOP_INTERNAL_API || "http://127.0.0.1:8010";

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  if (
    !["GET", "HEAD"].includes(request.method) &&
    !sameOrigin(request)
  )
    return NextResponse.json(
      { detail: "Cross-origin writes are not permitted" },
      { status: 403 },
    );
  const token = request.cookies.get("neuroloop_session")?.value;
  if (!token)
    return NextResponse.json(
      { detail: "Connect this browser to your workspace" },
      { status: 401 },
    );
  const { path } = await context.params;
  if (path.some((segment) => segment === ".." || segment.includes("\\")))
    return NextResponse.json({ detail: "Invalid API path" }, { status: 400 });
  const target =
    backend +
    "/api/" +
    path.map(encodeURIComponent).join("/") +
    request.nextUrl.search;
  const headers = new Headers({ Authorization: `Bearer ${token}` });
  for (const name of [
    "content-type",
    "range",
    "last-event-id",
    "idempotency-key",
  ]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const init: RequestInit & { duplex?: "half" } = {
    method: request.method,
    headers,
    cache: "no-store",
    redirect: "manual",
  };
  if (!["GET", "HEAD"].includes(request.method)) {
    init.body = request.body;
    init.duplex = "half";
  }
  try {
    const upstream = await fetch(target, init);
    const resultHeaders = new Headers();
    for (const name of [
      "content-type",
      "content-disposition",
      "content-length",
      "content-range",
      "accept-ranges",
      "cache-control",
      "x-accel-buffering",
    ]) {
      const value = upstream.headers.get(name);
      if (value) resultHeaders.set(name, value);
    }
    return new Response(upstream.body, {
      status: upstream.status,
      headers: resultHeaders,
    });
  } catch {
    return NextResponse.json(
      {
        detail:
          "The local API is unavailable. Your saved assets and results have not changed.",
      },
      { status: 503 },
    );
  }
}
export {
  proxy as GET,
  proxy as POST,
  proxy as PUT,
  proxy as DELETE,
  proxy as HEAD,
};
