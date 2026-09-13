import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const backend = process.env.NEUROLOOP_INTERNAL_API || "http://127.0.0.1:8010";
const allowed = new Set(["meta", "google", "tiktok"]);

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ provider: string }> },
) {
  const { provider } = await context.params;
  if (!allowed.has(provider))
    return NextResponse.redirect(new URL("/publish/oauth-return?status=error&code=UNKNOWN_PROVIDER", request.url));
  const target = `${backend}/api/v2/publish/oauth/${encodeURIComponent(provider)}/callback${request.nextUrl.search}`;
  try {
    const upstream = await fetch(target, {
      method: "GET",
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(30000),
    });
    const location = upstream.headers.get("location");
    if (location && upstream.status >= 300 && upstream.status < 400)
      return NextResponse.redirect(location, upstream.status as 301 | 302 | 303 | 307 | 308);
    return NextResponse.redirect(new URL(`/publish/oauth-return?status=error&code=CALLBACK_FAILED&provider=${provider}`, request.url));
  } catch {
    return NextResponse.redirect(new URL(`/publish/oauth-return?status=error&code=API_UNAVAILABLE&provider=${provider}`, request.url));
  }
}
