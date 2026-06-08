"use client";

import { SendHorizontal } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useDebug } from "@/lib/debug";

export function Composer({
  busy,
  onSubmit,
  disabled = false,
  disabledReason,
}: {
  busy: boolean;
  onSubmit: (q: string) => void;
  disabled?: boolean;
  disabledReason?: string;
}) {
  const { debug } = useDebug();
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement | null>(null);

  // Auto-grow up to max-height set in CSS.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
  }, [value]);

  function submit() {
    const q = value.trim();
    if (!q || busy || disabled) return;
    onSubmit(q);
    setValue("");
  }

  return (
    <div className="max-w-[940px] mx-auto px-6 pb-6 sticky bottom-0" style={{ background: "var(--bg)" }}>
      <div className="composer">
        <div className="flex items-end gap-3">
          <textarea
            ref={ref}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            rows={1}
            disabled={disabled}
            placeholder={
              disabled
                ? (disabledReason ?? "Backend unavailable.")
                : `Ask about a CHW, patient, or trend.  Try "why is chw-002 quiet?"`
            }
          />
          <button
            className="composer__send"
            onClick={submit}
            disabled={busy || disabled || !value.trim()}
            aria-label="Send"
          >
            <SendHorizontal size={14} />
          </button>
        </div>
        <div className="composer__hint">
          <span>↵ send · ⇧↵ newline</span>
          {debug && <span>model: gpt-5.5 (azure)</span>}
          {debug && <span>lookback: 30d</span>}
          <span className="flex items-center gap-1.5">
            <span
              className={`pulse-dot ${disabled ? "pulse-dot--alert" : "pulse-dot--ok"}`}
            />
            {disabled
              ? "Backend offline"
              : debug
                ? "fhir healthy"
                : "Connected"}
          </span>
          <span className="right text-[var(--ink-3)]">
            verify in OpenMRS before action
          </span>
        </div>
      </div>
    </div>
  );
}
