"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, XCircle } from "lucide-react";

export default function OAuthReturn() {
  const [result, setResult] = useState({ status: "working", provider: "", code: "" });
  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    setResult({
      status: query.get("status") || "error",
      provider: query.get("provider") || "provider",
      code: query.get("code") || "CONNECT_FAILED",
    });
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
        {result.status === "working" ? null : ok ? <CheckCircle2 size={38} /> : <XCircle size={38} />}
        <h1>{result.status === "working" ? "Checking connection…" : ok ? "Account connected" : "Connection didn’t finish"}</h1>
        <p>
          {result.status === "working" ? "Reading the authorization result…" : ok
            ? `${result.provider} is ready in NeuroLoop. You can close this window.`
            : `The provider returned ${result.code.replaceAll("_", " ").toLowerCase()}.`}
        </p>
        <a href="/workspace?view=publish">Return to Publish Ads</a>
      </div>
    </main>
  );
}
