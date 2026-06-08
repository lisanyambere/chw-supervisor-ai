"use client";

import { useEffect, useState } from "react";

const SUGGESTIONS: { cat: string; q: string }[] = [
  { cat: "anomaly", q: "Which CHWs are completely inactive in the last 7 days?" },
  { cat: "trend",   q: "What's the daily encounter trend over the last 30 days?" },
  { cat: "panel",   q: "Show me chw-009's patient panel for the last 30 days." },
  { cat: "scope",   q: "How many patients touched by the team in the last 30 days?" },
];

function formatEyebrow(d: Date): string {
  const wk = d.toLocaleString("en-US", { weekday: "short" }).toUpperCase();
  const mo = d.toLocaleString("en-US", { month: "short" }).toUpperCase();
  const hh = d.getHours().toString().padStart(2, "0");
  const mm = d.getMinutes().toString().padStart(2, "0");
  return `${wk} · ${mo} ${d.getDate()}, ${d.getFullYear()} · ${hh}:${mm} EAT`;
}

export function Hero({ onAsk }: { onAsk: (q: string) => void }) {
  // Render the wall-clock on the client only — SSR would render a different
  // value than hydration and trip React's mismatch warning.
  const [dateStr, setDateStr] = useState<string>("");
  useEffect(() => {
    setDateStr(formatEyebrow(new Date()));
    const i = setInterval(() => setDateStr(formatEyebrow(new Date())), 30_000);
    return () => clearInterval(i);
  }, []);

  return (
    <div className="max-w-[940px] mx-auto px-6 pt-12 pb-10">
      <p className="text-[12px] uppercase tracking-[0.08em] font-medium text-[var(--ink-3)] flex items-center gap-2 mb-5">
        <span className="pulse-dot" />
        {dateStr}
      </p>
      <h1 className="text-[30px] font-semibold leading-[1.15] tracking-[-0.02em] max-w-[20ch]">
        What{" "}
        <span className="font-bold" style={{ color: "var(--accent-ink)" }}>
          changed
        </span>{" "}
        on the team this week?
      </h1>
      <p className="text-[15px] text-[var(--ink-2)] max-w-[56ch] mt-4 leading-relaxed">
        Generate a Monday-morning briefing from FHIR data, ask follow-ups in
        plain English, and inspect every tool call the agent made along the way.
      </p>

      <div className="flex gap-3 mt-7">
        <button
          className="btn-primary"
          onClick={() =>
            onAsk(
              "Give me the Monday-morning briefing for the team over the last 30 days, with anomalies and recommended follow-ups.",
            )
          }
        >
          Generate Monday briefing
        </button>
        <button
          className="btn-ghost"
          onClick={() =>
            onAsk(
              "Surface only the anomalies I should act on today across the CHW team.",
            )
          }
        >
          Surface anomalies only
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3 mt-9 max-w-[680px]">
        {SUGGESTIONS.map((s) => (
          <button
            key={s.cat}
            className="suggestion"
            onClick={() => onAsk(s.q)}
          >
            <div className="suggestion__cat">{s.cat}</div>
            <div className="suggestion__q">{s.q}</div>
          </button>
        ))}
      </div>
    </div>
  );
}
