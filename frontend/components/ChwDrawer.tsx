"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { getChwDetail, type ChwDetail } from "@/lib/api";

const LOOKBACK_DAYS = 30;

export function ChwDrawer({
  chwId,
  onClose,
}: {
  chwId: string | null;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<ChwDetail | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [error, setError] = useState<string>("");

  // Fetch whenever the selected CHW changes. Abort in-flight requests so a
  // fast chip-to-chip switch doesn't render a stale panel.
  useEffect(() => {
    if (!chwId) return;
    const ctrl = new AbortController();
    setStatus("loading");
    setDetail(null);
    setError("");
    getChwDetail(chwId, { days: LOOKBACK_DAYS, signal: ctrl.signal })
      .then((d) => {
        setDetail(d);
        setStatus("idle");
      })
      .catch((e: unknown) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setError(e instanceof Error ? e.message : "Failed to load CHW.");
        setStatus("error");
      });
    return () => ctrl.abort();
  }, [chwId]);

  // Close on Escape while open.
  useEffect(() => {
    if (!chwId) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [chwId, onClose]);

  if (!chwId) return null;

  return (
    <div className="drawer-overlay" onClick={onClose}>
      <aside
        className="drawer-panel"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="CHW detail"
      >
        <header className="drawer-head">
          <div>
            <div className="drawer-head__id">{chwId}</div>
            <div className="drawer-head__name">
              {detail?.name || (status === "loading" ? "Loading..." : "Unknown CHW")}
            </div>
          </div>
          <button className="drawer-close" onClick={onClose} type="button" aria-label="Close">
            <X size={16} />
          </button>
        </header>

        {status === "error" && (
          <div className="drawer-error">{error}</div>
        )}

        {status === "loading" && (
          <div className="drawer-muted">Loading CHW detail...</div>
        )}

        {detail && (
          <div className="drawer-body">
            <div className="drawer-stats">
              <div className="drawer-stat">
                <div className="drawer-stat__value">{detail.encounter_count}</div>
                <div className="drawer-stat__label">encounters · {detail.days}d</div>
              </div>
              <div className="drawer-stat">
                <div className="drawer-stat__value">{detail.patient_count}</div>
                <div className="drawer-stat__label">patients seen</div>
              </div>
            </div>

            <div className="panel">
              <div className="panel__head">Recent patient panel</div>
              {detail.patients.length === 0 ? (
                <div className="drawer-muted drawer-muted--inset">
                  No patients in the last {detail.days} days.
                </div>
              ) : (
                detail.patients.map((p) => (
                  <div key={p.patient_uuid} className="panel__row">
                    <div className="font-medium">{p.name || "(unnamed)"}</div>
                    <div className="panel__row__mid">
                      {p.last_encounter_date?.slice(0, 10) ?? "—"}
                    </div>
                    <div className="panel__row__right">{p.encounter_count}x</div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}
