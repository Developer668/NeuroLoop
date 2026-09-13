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
export function sameOrigin(request: NextRequest): boolean {
  const origin = request.headers.get("origin");
  return !origin || origin === publicOrigin(request);
}
