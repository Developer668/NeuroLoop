"use client";

import { useEffect, useMemo } from "react";
import { CheckCircle2, XCircle } from "lucide-react";

export default function OAuthReturn() {
  const result = useMemo(() => {
    if (typeof window === "undefined") return { status: "working", provider: "", code: "" };
    const query = new URLSearchParams(window.location.search);
    return {
      status: query.get("status") || "error",
      provider: query.get("provider") || "provider",
      code: query.get("code") || "CONNECT_FAILED",
    };
  }, []);

  useEffect(() => {
    if (result.status === "working") return;
    if (window.opener && !window.opener.closed) {
      window.opener.postMessage(
        { type: "neuroloop-publish-oauth", ...result },
        window.location.origin,
      );
      window.setTimeout(() => window.close(), 500);
    }
  }, [result]);

  const ok = result.status === "connected";
  return (
    <main className="oauth-return-page">
      <div className="oauth-return-card">
        {ok ? <CheckCircle2 size={38} /> : <XCircle size={38} />}
        <h1>{ok ? "Account connected" : "Connection didn’t finish"}</h1>
        <p>
          {ok
            ? `${result.provider} is ready in NeuroLoop. You can close this window.`
            : `The provider returned ${result.code.replaceAll("_", " ").toLowerCase()}.`}
        </p>
        <a href="/workspace?view=publish">Return to Publish Ads</a>
      </div>
    </main>
  );
}
