"use client";

import { useEffect, useState } from "react";

export function Topbar({
  breadcrumb,
  status = "fhir · langfuse · azure",
}: {
  breadcrumb: string;
  status?: string;
}) {
  // Client-only to avoid SSR/CSR hydration mismatch on the date string.
  const [dateStr, setDateStr] = useState<string>("");
  useEffect(() => {
    const fmt = () =>
      new Date()
        .toLocaleDateString("en-GB", {
          weekday: "short",
          day: "numeric",
          month: "short",
          year: "numeric",
        })
        .toLowerCase();
    setDateStr(fmt());
    const i = setInterval(() => setDateStr(fmt()), 60_000);
    return () => clearInterval(i);
  }, []);

  return (
    <div
      className="h-[46px] border-b border-[var(--line)] flex items-center justify-between px-5 sticky top-0 z-10"
      style={{ background: "var(--bg)" }}
    >
      <div className="font-mono text-[12px] text-[var(--ink-3)]">
        {breadcrumb}
      </div>
      <div className="flex items-center gap-3">
        <div className="font-mono text-[11px] text-[var(--ink-3)]">{dateStr}</div>
        <div
          className="font-mono text-[11px] flex items-center gap-2 px-2.5 py-1 rounded-full border"
          style={{
            background: "var(--surface)",
            borderColor: "var(--line)",
            color: "var(--ink-2)",
          }}
        >
          <span className="pulse-dot pulse-dot--ok" />
          {status}
        </div>
      </div>
    </div>
  );
}
