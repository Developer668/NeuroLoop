"use client";

import dynamic from "next/dynamic";
import { AlertCircle, ArrowRight } from "lucide-react";
import { Brand } from "./UI";

const EntranceBrain = dynamic(() => import("./BrainCanvas"), { ssr: false });

/** V1's entrance, with authentication still owned by the current workspace. */
export default function LoopLogin({ busy, error, token, setToken, connect }: {
  busy: boolean;
  error: string;
  token: string;
  setToken: (token: string) => void;
  connect: (local: boolean) => Promise<void>;
}) {
  return (
    <main className="auth-layout">
      <section className="auth-story" aria-label="Welcome to NeuroLoop">
        <Brand />
        <div className="auth-observatory">
          <EntranceBrain publicMesh cinematic />
        </div>
        <div className="auth-story-copy">
          <span className="eyebrow">A SPACE FOR CLOSER LOOKS</span>
          <h1>Bring something<br />worth exploring.</h1>
          <p>Your creative. A considered experiment. A record you can return to.</p>
        </div>
        <span className="auth-note">20,484 SURFACE VERTICES / TWO HEMISPHERES</span>
      </section>
      <section className="auth-form" aria-labelledby="workspace-login-title">
        <div className="auth-card">
          <span className="eyebrow">Welcome to the lab</span>
          <h2 id="workspace-login-title">Open your workspace.</h2>
          <p>Pick up where you left off. Your creatives, experiments and saved responses are waiting here.</p>
          {error && <div role="alert" className="notice error"><AlertCircle size={16} />{error}</div>}
          <button className="button primary" disabled={busy}
            aria-label="Connect to this computer — Open local workspace"
            onClick={() => void connect(true)}>
            {busy ? "Connecting…" : "Connect to this computer"}<ArrowRight size={15} />
          </button>
          <details className="token-access">
            <summary>Connect with an access token</summary>
            <form onSubmit={(event) => { event.preventDefault(); if (!busy && token.trim()) void connect(false); }}>
              <label className="field">
                <span>Workspace access token</span>
                <input type="password" autoComplete="off" value={token}
                  onChange={(event) => setToken(event.target.value)}
                  placeholder="Paste your token" required disabled={busy} />
              </label>
              <button className="button" disabled={busy || !token.trim()}>Connect securely</button>
            </form>
          </details>
          <footer><a href="/">Return to homepage</a></footer>
        </div>
      </section>
    </main>
  );
}
