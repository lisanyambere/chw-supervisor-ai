"use client";

import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { getChwDetail, type ChwDetail } from "@/lib/api";
import { cn } from "@/lib/cn";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; chw: ChwDetail };

function weekday(isoDate: string) {
  // Parse as UTC so the label matches the backend's UTC day buckets.
  return new Date(`${isoDate}T00:00:00Z`).toLocaleDateString("en-GB", {
    weekday: "short",
    timeZone: "UTC",
  });
}

export function ChwDrawer({
  chwId,
  onClose,
  onAsk,
}: {
  chwId: string | null;
  onClose: () => void;
  onAsk: (q: string) => void;
}) {
  const open = chwId !== null;
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const closeRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (chwId === null) return;
    setState({ status: "loading" });
    const ctrl = new AbortController();
    getChwDetail(chwId, { signal: ctrl.signal })
      .then((chw) => setState({ status: "ready", chw }))
      .catch((e: unknown) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setState({
          status: "error",
          message: e instanceof Error ? e.message : "CHW lookup failed.",
        });
      });
    return () => ctrl.abort();
  }, [chwId]);

  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  function askAndClose(q: string) {
    onClose();
    onAsk(q);
  }

  return (
    <>
      <div
        className={cn("drawer-mask", open && "is-open")}
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        className={cn("drawer", open && "is-open")}
        role="dialog"
        aria-modal="true"
        aria-label={chwId ? `Details for ${chwId}` : undefined}
        aria-hidden={!open}
      >
        {chwId && (
          <>
            <div className="drawer__head">
              <div>
                <div className="drawer__id">{chwId}</div>
                <div className="drawer__name">
                  {state.status === "ready"
                    ? (state.chw.name ?? "Community health worker")
                    : "\u00a0"}
                </div>
              </div>
              <button
                ref={closeRef}
                className="drawer__close"
                onClick={onClose}
                type="button"
                aria-label="Close"
              >
                <X size={14} />
              </button>
            </div>
            <div className="drawer__body">
              {state.status === "loading" && (
                <div className="drawer__note">Loading from OpenMRS…</div>
              )}
              {state.status === "error" && (
                <div className="drawer__note drawer__note--alert" role="alert">
                  {state.message}
                </div>
              )}
              {state.status === "ready" && (
                <ChwBody chw={state.chw} onAsk={askAndClose} />
              )}
            </div>
          </>
        )}
      </aside>
    </>
  );
}

function ChwBody({
  chw,
  onAsk,
}: {
  chw: ChwDetail;
  onAsk: (q: string) => void;
}) {
  const quiet = chw.encounters_7d === 0;
  const max = Math.max(1, ...chw.daily.map((d) => d.encounter_count));
  return (
    <>
      <dl>
        {chw.ward && <Row k="Ward" v={chw.ward} />}
        <Row k="Encounters · 30d" v={chw.encounters_30d} />
        <Row k="Encounters · 7d" v={chw.encounters_7d} />
        <Row k="Patients seen · 30d" v={chw.patients_30d} />
        <Row
          k="Status"
          v={quiet ? "no visits in 7 days" : "active"}
          tone={quiet ? "alert" : "ok"}
        />
        <Row k="FHIR Practitioner" v={chw.practitioner_uuid.slice(0, 8)} />
      </dl>

      <div className="drawer__chart">
        <h4>Last 7 days · daily encounters</h4>
        <div className="spark">
          {chw.daily.map((d) => (
            <div
              key={d.date}
              className={cn("spark__b", d.encounter_count === 0 && "is-zero")}
              style={{ height: `${(d.encounter_count / max) * 100}%` }}
              title={`${d.date}: ${d.encounter_count}`}
            />
          ))}
        </div>
        <div className="spark__legend">
          {chw.daily.map((d) => (
            <span key={d.date}>{weekday(d.date)}</span>
          ))}
        </div>
      </div>

      <div className="drawer__actions">
        <button
          className="btn-ghost"
          type="button"
          onClick={() => onAsk(`Show the patient panel for ${chw.chw_id}.`)}
        >
          Open patient panel
        </button>
        <button
          className="btn-ghost"
          type="button"
          onClick={() =>
            onAsk(`How has ${chw.chw_id}'s activity changed over 30 days?`)
          }
        >
          Ask about activity
        </button>
      </div>
    </>
  );
}

function Row({
  k,
  v,
  tone,
}: {
  k: string;
  v: string | number;
  tone?: "ok" | "alert";
}) {
  return (
    <div className="drawer__row">
      <dt>{k}</dt>
      <dd className={tone && `tone-${tone}`}>{v}</dd>
    </div>
  );
}
