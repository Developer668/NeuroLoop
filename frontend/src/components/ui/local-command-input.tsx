"use client";
import { useEffect, useRef, useState } from "react";
import { ArrowUp, Command, Plus, X } from "lucide-react";

/** Expanding composer adapted from the supplied design to the actual command API. */
export function PromptInput({
  value,
  onChange,
  onSubmit,
  busy,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  busy: boolean;
}) {
  const [focused, setFocused] = useState(false);
  const [menu, setMenu] = useState(false);
  const input = useRef<HTMLTextAreaElement>(null);
  const expanded = focused || !!value || menu;
  useEffect(() => {
    if (!input.current) return;
    input.current.style.height = "auto";
    input.current.style.height = `${Math.min(160, input.current.scrollHeight)}px`;
  }, [value, expanded]);
  return (
    <form
      className="neuro-composer prompt-input"
      data-expanded={expanded}
      onFocus={() => setFocused(true)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) {
          setFocused(false);
          setMenu(false);
        }
      }}
      onSubmit={(e) => {
        e.preventDefault();
        if (!busy && value.trim()) onSubmit();
      }}
    >
      <label className="sr-only" htmlFor="neuro-input">
        Local command or saved draft
      </label>
      <textarea
        id="neuro-input"
        ref={input}
        value={value}
        maxLength={2500}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Type /help or choose a command…"
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            setMenu(false);
            input.current?.blur();
          }
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            if (!busy && value.trim()) onSubmit();
          }
        }}
      />
      <div className="neuro-compose-tools">
        <button
          type="button"
          className="neuro-command-toggle"
          aria-expanded={menu}
          aria-controls="neuro-command-menu"
          onClick={() => setMenu(!menu)}
        >
          {menu ? <X size={16} /> : <Plus size={16} />} Commands
        </button>
        <span className="prompt-provider">
          <Command size={13} /> Local evidence
        </span>
        <span className="neuro-draft-state">
          {value.length ? `${value.length} / 2,500` : ""}
        </span>
        <button
          type="submit"
          className="neuro-send"
          disabled={busy || !value.trim()}
          aria-label="Run local command"
        >
          <ArrowUp size={18} />
        </button>
      </div>
      {menu && (
        <div id="neuro-command-menu" className="neuro-command-menu">
          {["/status", "/latest", "/experiments", "/connections", "/help"].map(
            (command) => (
              <button
                key={command}
                type="button"
                onClick={() => {
                  onChange(command);
                  setMenu(false);
                  input.current?.focus();
                }}
              >
                <Command size={13} />
                {command}
              </button>
            ),
          )}
        </div>
      )}
    </form>
  );
}
