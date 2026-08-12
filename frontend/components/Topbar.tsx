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
    <header className="topbar flex items-center justify-between px-6 sticky top-0 z-10">
      <div className="flex items-center gap-3 min-w-0">
        <span className="topbar-index">01</span>
        <div className="topbar-breadcrumb truncate">{breadcrumb}</div>
      </div>
      <div className="flex items-center gap-3">
        <div className="topbar-date">{dateStr}</div>
        <div className="system-status">
          <span className="pulse-dot pulse-dot--ok" />
          {status}
        </div>
      </div>
    </header>
  );
}
