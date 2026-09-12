"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/types";
import { Panel, errorText } from "./UI";
export type Preferences = {
  workspace_name: string;
  display_name: string;
  reduced_motion: boolean;
};
export default function ProfileSettings() {
  const [value, setValue] = useState<Preferences>({
      workspace_name: "My workspace",
      display_name: "NeuroLoop",
      reduced_motion: false,
    }),
    [ready, setReady] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [saved, setSaved] = useState(false);
  useEffect(() => {
    let live = true;
    api<Preferences>("preferences")
      .then((x) => {
        if (live) {
          setValue(x);
          setReady(true);
        }
      })
      .catch((e) => {
        if (live) setError(errorText(e));
      });
    return () => {
      live = false;
    };
  }, []);
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setSaved(false);
    try {
      await api("preferences", { method: "PUT", body: JSON.stringify(value) });
      document.documentElement.dataset.motion = value.reduced_motion
        ? "reduced"
        : "full";
      window.dispatchEvent(
        new CustomEvent("neuroloop-preferences", { detail: value }),
      );
      setSaved(true);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Panel
      title="Make it yours"
      description="Your display preferences for this workspace."
    >
      <form className="panel-body" onSubmit={save}>
        {error && (
          <div className="notice error" role="alert">
            {error}
          </div>
        )}
        <div className="field-row">
          <label className="field">
            <span>Display name</span>
            <input
              maxLength={60}
              required
              value={value.display_name}
              onChange={(e) => {
                setValue({ ...value, display_name: e.target.value });
                setSaved(false);
              }}
            />
          </label>
          <label className="field">
            <span>Workspace name</span>
            <input
              maxLength={60}
              required
              value={value.workspace_name}
              onChange={(e) => {
                setValue({ ...value, workspace_name: e.target.value });
                setSaved(false);
              }}
            />
          </label>
        </div>
        <label className="check">
          <input
            type="checkbox"
            checked={value.reduced_motion}
            onChange={(e) => {
              setValue({ ...value, reduced_motion: e.target.checked });
              setSaved(false);
            }}
          />
          <span>
            Reduce interface motion
            <small>
              Your operating system’s reduced-motion preference is also
              respected.
            </small>
          </span>
        </label>
        <div className="button-row section-space">
          <button className="button primary" disabled={!ready || busy}>
            {busy ? "Saving…" : "Save preferences"}
          </button>
          {saved && (
            <span className="saved-preferences" role="status">
              Preferences saved
            </span>
          )}
        </div>
      </form>
    </Panel>
  );
}
