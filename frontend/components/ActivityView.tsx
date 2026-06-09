"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ChevronDown } from "lucide-react";
import {
  getActivity,
  getChws,
  type ActivityDay,
  type ActivityResponse,
  type ChwRosterEntry,
} from "@/lib/api";
import { cn } from "@/lib/cn";

const DAY_OPTIONS = [7, 14, 30] as const;

/** "2026-05-14" → "5/14" (no leading zeros, locale-free, hydration-safe). */
function shortDate(iso: string): string {
  const [, m, d] = iso.split("-");
  return `${Number(m)}/${Number(d)}`;
}

/** "2026-05-14" → "Thu, May 14". */
function longDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

export function ActivityView() {
  const [roster, setRoster] = useState<ChwRosterEntry[]>([]);
  // null = whole team.
  const [chwId, setChwId] = useState<string | null>(null);
  const [days, setDays] = useState<number>(30);
  const [data, setData] = useState<ActivityResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Roster loads once; a failure just leaves the selector team-only.
  useEffect(() => {
    const ctrl = new AbortController();
    getChws({ signal: ctrl.signal })
      .then(setRoster)
      .catch(() => {
        /* selector degrades to whole-team only */
      });
    return () => ctrl.abort();
  }, []);

  // Reload the series whenever the window or CHW scope changes.
  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);
    getActivity({ days, chwId, signal: ctrl.signal })
      .then((d) => {
        setData(d);
        setLoading(false);
      })
      .catch((e: unknown) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setError(e instanceof Error ? e.message : "Failed to load activity.");
        setLoading(false);
      });
    return () => ctrl.abort();
  }, [days, chwId]);

  const scopeLabel = chwId ?? "the whole team";

  return (
    <section className="activity">
      <header className="activity__head">
        <div>
          <h1 className="activity__title">Field activity</h1>
          <p className="activity__sub">
            Daily encounters logged by {scopeLabel} over the last {days} days.
          </p>
        </div>
        <div className="activity__controls">
          <div className="activity-select-wrap">
            <select
              className="activity-select"
              value={chwId ?? ""}
              onChange={(e) => setChwId(e.target.value || null)}
              aria-label="Scope activity to a CHW"
            >
              <option value="">Whole team</option>
              {roster.map((r) => (
                <option key={r.chw_id} value={r.chw_id}>
                  {r.chw_id}
                </option>
              ))}
            </select>
            <ChevronDown size={14} className="activity-select-chevron" />
          </div>
          <div className="seg" role="group" aria-label="Look-back window">
            {DAY_OPTIONS.map((d) => (
              <button
                key={d}
                type="button"
                className={cn(days === d && "is-active")}
                onClick={() => setDays(d)}
              >
                {d}d
              </button>
            ))}
          </div>
        </div>
      </header>

      {error ? (
        <div className="activity-error">
          <AlertTriangle size={16} />
          <span>{error}</span>
        </div>
      ) : loading || !data ? (
        <ActivitySkeleton days={days} />
      ) : (
        <ActivityChart data={data} />
      )}
    </section>
  );
}

/* ─── stats + chart ──────────────────────────────────────────────────── */

function ActivityChart({ data }: { data: ActivityResponse }) {
  const { series, stats } = data;

  // Busiest day — drives the "peak" stat's context line. First match is fine.
  const busiest = useMemo(
    () => series.find((s) => s.encounter_count === stats.max) ?? null,
    [series, stats.max],
  );

  const periodLabel =
    series.length > 0
      ? `${longDate(series[0].date)} – ${longDate(series[series.length - 1].date)}`
      : "";

  return (
    <>
      <div className="stat-row activity-stats">
        <StatTile
          label="Total encounters"
          value={stats.total.toLocaleString()}
          sub={`across ${data.days} days`}
        />
        <StatTile
          label="Daily average"
          value={stats.mean.toFixed(1)}
          sub="encounters per day"
        />
        <StatTile
          label="Busiest day"
          value={stats.max.toLocaleString()}
          sub={busiest ? longDate(busiest.date) : "—"}
        />
        <StatTile
          label="Zero-activity days"
          value={String(stats.zero_days)}
          delta={stats.zero_days > 0 ? "needs follow-up" : "full coverage"}
          deltaTone={stats.zero_days > 0 ? "alert" : "ok"}
          sub={`of ${data.days} days`}
        />
      </div>

      <div className="activity-card">
        <div className="activity-card__head">
          <div className="activity-card__title">Encounters per day</div>
          <div className="activity-card__period">{periodLabel}</div>
        </div>
        <Chart series={series} max={stats.max} />
        <div className="chart-legend">
          <span className="chart-legend__item">
            <span
              className="chart-legend__swatch"
              style={{ background: "var(--accent)" }}
            />
            encounters
          </span>
          <span className="chart-legend__item">
            <span
              className="chart-legend__swatch"
              style={{ background: "var(--surface-2)" }}
            />
            weekend
          </span>
          <span className="chart-legend__item">
            <span
              className="chart-legend__swatch"
              style={{ background: "var(--alert)" }}
            />
            no activity
          </span>
        </div>
      </div>
    </>
  );
}

function Chart({ series, max }: { series: ActivityDay[]; max: number }) {
  // Guard the divisor — an all-zero window must not divide by zero.
  const scale = Math.max(max, 1);
  const n = series.length;

  return (
    <>
      <div className="chart" role="img" aria-label="Daily encounter counts">
        {series.map((d) => {
          const pct = (d.encounter_count / scale) * 100;
          return (
            <div
              key={d.date}
              className={cn(
                "chart-col",
                d.is_weekend && "chart-col--weekend",
                d.is_zero && "chart-col--zero",
              )}
              title={`${longDate(d.date)} — ${d.encounter_count} encounter${
                d.encounter_count === 1 ? "" : "s"
              }`}
            >
              <div
                className="chart-fill"
                style={{ height: d.is_zero ? undefined : `${pct}%` }}
              />
            </div>
          );
        })}
      </div>
      <div className="chart-axis" aria-hidden>
        {series.map((d, i) => {
          const show = i === 0 || i === n - 1 || d.weekday === "Mon";
          return (
            <div key={d.date} className="chart-axis__tick">
              {show ? shortDate(d.date) : ""}
            </div>
          );
        })}
      </div>
    </>
  );
}

function StatTile({
  label,
  value,
  delta,
  deltaTone,
  sub,
}: {
  label: string;
  value: string;
  delta?: string;
  deltaTone?: "ok" | "warn" | "alert" | "muted";
  sub: string;
}) {
  return (
    <div className="stat-tile">
      <div className="stat-tile__label">{label}</div>
      <div className="stat-tile__value">{value}</div>
      {delta ? (
        <div className={cn("stat-tile__delta", `tone-${deltaTone ?? "muted"}`)}>
          {delta}
        </div>
      ) : null}
      <div className="stat-tile__sub">{sub}</div>
    </div>
  );
}

function ActivitySkeleton({ days }: { days: number }) {
  // Deterministic heights keep the skeleton stable across renders.
  const bars = Array.from({ length: days }, (_, i) => 30 + ((i * 37) % 55));
  return (
    <>
      <div className="stat-row activity-stats">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="stat-tile">
            <div className="skel skel--label" />
            <div className="skel skel--value" />
            <div className="skel skel--sub" />
          </div>
        ))}
      </div>
      <div className="activity-card">
        <div className="activity-card__head">
          <div className="skel skel--title" />
        </div>
        <div className="chart">
          {bars.map((h, i) => (
            <div key={i} className="chart-col">
              <div
                className="chart-fill chart-fill--skel"
                style={{ height: `${h}%` }}
              />
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
