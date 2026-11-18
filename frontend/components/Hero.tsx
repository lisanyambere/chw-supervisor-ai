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
    <div className="hero max-w-[1040px] mx-auto px-8 pt-14 pb-12">
      <div className="hero-kicker">
        <span className="pulse-dot" />
        <span>{dateStr}</span>
        <span className="hero-kicker__line" />
        <span>30 field workers</span>
      </div>

      <div className="hero-heading-wrap">
        <span className="hero-issue" aria-hidden="true">FIELD NOTE / 01</span>
        <h1 className="hero-title">
          What <em>changed</em><br />
          in the field?
        </h1>
        <div className="hero-stamp" aria-hidden="true">
          <span>FHIR</span>
          <small>LIVE</small>
        </div>
      </div>

      <div className="hero-intro">
        <p>
          Turn raw community health activity into a clear Monday brief—then
          follow the evidence down to each worker, patient, and tool call.
        </p>
        <span className="hero-rule" />
        <span className="hero-coordinate">0.2827° N<br />34.7519° E</span>
      </div>

      <div className="hero-actions flex gap-3 mt-8">
        <button
          className="btn-primary"
          onClick={() =>
            onAsk(
              "Give me the Monday-morning briefing for the team over the last 30 days, with anomalies and recommended follow-ups.",
            )
          }
        >
          <span>Generate Monday briefing</span>
          <span aria-hidden="true">→</span>
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

      <div className="suggestion-grid grid grid-cols-2 gap-3 mt-11 max-w-[760px]">
        {SUGGESTIONS.map((s) => (
          <button
            key={s.cat}
            className="suggestion"
            onClick={() => onAsk(s.q)}
          >
            <div className="suggestion__cat">0{SUGGESTIONS.indexOf(s) + 1} / {s.cat}</div>
            <div className="suggestion__q">{s.q}</div>
          </button>
        ))}
      </div>
    </div>
  );
}
