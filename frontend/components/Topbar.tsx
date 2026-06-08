"use client";

import { useEffect, useState } from "react";
import { Bug } from "lucide-react";
import { cn } from "@/lib/cn";
import { useDebug } from "@/lib/debug";

export function Topbar({
  breadcrumb,
  status = "fhir · langfuse · azure",
}: {
  breadcrumb: string;
  status?: string;
}) {
  const { debug, toggle } = useDebug();
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
      <div className="text-[12px] text-[var(--ink-2)]">{breadcrumb}</div>
      <div className="flex items-center gap-3">
        <div className="text-[12px] text-[var(--ink-3)]">{dateStr}</div>
        <div
          className="text-[12px] flex items-center gap-2 px-2.5 py-1 rounded-full border"
          style={{
            background: "var(--surface)",
            borderColor: "var(--line)",
            color: "var(--ink-2)",
          }}
        >
          <span className="pulse-dot pulse-dot--ok" />
          {/* Friendly by default; the raw provider string only in Debug Mode. */}
          {debug ? status : "All systems normal"}
        </div>
        <button
          type="button"
          onClick={toggle}
          className={cn("debug-toggle", debug && "debug-toggle--on")}
          title="Toggle Debug Mode (Ctrl/Cmd + Shift + D)"
          aria-pressed={debug}
        >
          <Bug size={13} />
          {debug ? "Debug on" : "Debug"}
        </button>
      </div>
    </div>
  );
}
