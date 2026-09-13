import type { NextRequest } from "next/server";

/** Next's internal request URL can use localhost behind its production server.
 * Prefer an explicit public origin; otherwise use the browser's actual Host.
 * Do not accept arbitrary X-Forwarded-Host values as an authentication origin.
 */
export function publicOrigin(request: NextRequest): string {
  const configured = process.env.NEUROLOOP_FRONTEND_ORIGIN;
  return configured
    ? new URL(configured).origin
    : new URL(
        `${request.nextUrl.protocol}//${request.headers.get("host") || request.nextUrl.host}`,
      ).origin;
}

/**
 * Local development commonly uses either localhost or 127.0.0.1. Treat those
 * loopback aliases as equivalent while keeping protocol and port strict.
 */
function equivalentOrigin(expected: string, actual: string): boolean {
  if (expected === actual) return true;
  try {
    const configured = new URL(expected), incoming = new URL(actual);
    const loopback = new Set(["localhost", "127.0.0.1", "[::1]"]);
    return (
      configured.protocol === incoming.protocol &&
      configured.port === incoming.port &&
      loopback.has(configured.hostname) &&
      loopback.has(incoming.hostname)
    );
  } catch {
    return false;
  }
}
export function sameOrigin(request: NextRequest): boolean {
  const origin = request.headers.get("origin");
  return !origin || equivalentOrigin(publicOrigin(request), origin);
}
