"use client";

import { useEffect, useState } from "react";
import { getDailyActivity, type DailyActivity, type DailyCount } from "@/lib/api";
import { cn } from "@/lib/cn";

const DAYS = 30;

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: DailyActivity };

type Day = DailyCount & { weekend: boolean; missed: boolean };

function utc(isoDate: string) {
  return new Date(`${isoDate}T00:00:00Z`);
}

function label(isoDate: string, opts: Intl.DateTimeFormatOptions) {
  return utc(isoDate).toLocaleDateString("en-GB", { timeZone: "UTC", ...opts });
}

/**
 * Weekends are expected to be quiet; a weekday with no visits is not. The
 * last day in the series is today, which is not over yet, so it never counts
 * as missed.
 */
export function classifyDays(series: DailyCount[]): Day[] {
  return series.map((d, i) => {
    const dow = utc(d.date).getUTCDay();
    const weekend = dow === 0 || dow === 6;
    const today = i === series.length - 1;
    return {
      ...d,
      weekend,
      missed: !weekend && !today && d.encounter_count === 0,
    };
  });
}

export function ActivityView() {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [asTable, setAsTable] = useState(false);

  useEffect(() => {
    const ctrl = new AbortController();
    getDailyActivity(DAYS, { signal: ctrl.signal })
      .then((data) => setState({ status: "ready", data }))
      .catch((e: unknown) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setState({
          status: "error",
          message: e instanceof Error ? e.message : "Activity lookup failed.",
        });
      });
    return () => ctrl.abort();
  }, []);

  return (
    <div className="max-w-[940px] mx-auto px-6 pt-8 pb-6">
      <div className="hero-kicker">
        <span className="pulse-dot pulse-dot--ok" />
        Activity · last {DAYS} days
      </div>
      <h1 className="activity-title">Daily team encounters across Kakamega</h1>

      <article className="ans ans--plain mt-5">
        <div className="ans__period">
          visits_by_day({DAYS}) · per FHIR Encounter.period.start
        </div>
        {state.status === "loading" && (
          <div className="drawer__note">Loading from OpenMRS…</div>
        )}
        {state.status === "error" && (
          <div className="drawer__note drawer__note--alert" role="alert">
            {state.message}
          </div>
        )}
        {state.status === "ready" && (
          <Chart
            days={classifyDays(state.data.series)}
            total={state.data.total}
            asTable={asTable}
            onToggle={() => setAsTable((v) => !v)}
          />
        )}
      </article>
    </div>
  );
}

function headline(days: Day[]): string {
  const missed = days.filter((d) => d.missed);
  if (missed.length === 0) return "Visits were logged on every weekday in the window.";
  const last = missed[missed.length - 1];
  return missed.length === 1
    ? `${label(last.date, { weekday: "long", day: "numeric", month: "short" })} is the only weekday with no visits.`
    : `${missed.length} weekdays have no visits, most recently ${label(last.date, { weekday: "long", day: "numeric", month: "short" })}.`;
}

function Chart({
  days,
  total,
  asTable,
  onToggle,
}: {
  days: Day[];
  total: number;
  asTable: boolean;
  onToggle: () => void;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(1, ...days.map((d) => d.encounter_count));

  return (
    <>
      <h2 className="activity-head">{headline(days)}</h2>
      <div className="activity-meta">
        <span>
          <b>{total.toLocaleString()}</b> encounters
        </span>
        <span className="activity-key">
          <i className="activity-swatch" /> weekday
        </span>
        <span className="activity-key">
          <i className="activity-swatch activity-swatch--weekend" /> weekend
        </span>
        <span className="activity-key">
          <i className="activity-swatch activity-swatch--missed" /> ✕ weekday
          with no visits
        </span>
        <button className="activity-toggle" type="button" onClick={onToggle}>
          {asTable ? "Show chart" : "Show as table"}
        </button>
      </div>

      {asTable ? (
        <table className="activity-table">
          <thead>
            <tr>
              <th scope="col">Date</th>
              <th scope="col">Encounters</th>
            </tr>
          </thead>
          <tbody>
            {days.map((d) => (
              <tr key={d.date}>
                <td>
                  {label(d.date, { weekday: "short", day: "numeric", month: "short" })}
                </td>
                <td>
                  {d.encounter_count}
                  {d.missed && " — no visits"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="activity-plot" onMouseLeave={() => setHover(null)}>
          <div className="activity-grid" aria-hidden="true">
            <span>{max}</span>
            <span>{Math.round(max / 2)}</span>
            <span>0</span>
          </div>
          <div
            className="activity-bars"
            role="img"
            aria-label={`Bar chart of encounters per day for the last ${days.length} days. ${headline(days)}`}
          >
            {days.map((d, i) => (
              // The whole column is the hover target, not just the bar.
              <div
                key={d.date}
                className={cn("activity-col", i === hover && "is-focus")}
                onMouseEnter={() => setHover(i)}
              >
                {i === hover && (
                  <div
                    className={cn(
                      "activity-tip",
                      i > days.length / 2 && "activity-tip--left",
                    )}
                  >
                    <b>{d.encounter_count}</b>
                    <span>
                      {label(d.date, { weekday: "short", day: "numeric", month: "short" })}
                      {d.missed && " · no visits"}
                    </span>
                  </div>
                )}
                {d.missed ? (
                  <span className="activity-missed">✕</span>
                ) : (
                  <span
                    className={cn("activity-bar", d.weekend && "is-weekend")}
                    style={{ height: `${(d.encounter_count / max) * 100}%` }}
                  />
                )}
              </div>
            ))}
          </div>
          <div className="activity-axis" aria-hidden="true">
            {days.map((d, i) => (
              <span key={d.date}>
                {utc(d.date).getUTCDay() === 1 || i === 0
                  ? label(d.date, { day: "numeric", month: "short" })
                  : ""}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="trace-footer">
        <span className="trace-footer__label">sources</span>
        <span className="chip">visits_by_day({days.length})</span>
      </div>
    </>
  );
}
