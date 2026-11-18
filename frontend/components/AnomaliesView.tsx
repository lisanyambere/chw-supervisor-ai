"use client";

import type { ReactNode } from "react";
import { ArrowRight } from "lucide-react";
import type { Anomalies } from "@/lib/api";
import type { LoadState } from "@/lib/useLoad";
import { cn } from "@/lib/cn";
import { LoadNote, ViewHeader } from "@/components/ViewHeader";
import { PATTERN_LABELS, patternNote } from "@/components/RosterView";

function shortDate(iso: string) {
  return new Date(`${iso.slice(0, 10)}T00:00:00Z`).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
}

/**
 * Everything the tools flag, straight from OpenMRS with no model in the loop.
 * The briefing explains and ranks these; this view lists them.
 */
export function AnomaliesView({
  state,
  onSelectChw,
  onAsk,
}: {
  state: LoadState<Anomalies>;
  onSelectChw: (id: string) => void;
  onAsk: (q: string) => void;
}) {
  return (
    <div className="view">
      <ViewHeader
        kicker={
          state.status === "ready"
            ? `Anomalies · last ${state.data.days} days · no model`
            : "Anomalies"
        }
        title="What needs attention"
      />
      {state.status !== "ready" ? (
        <div className="mt-5">
          <LoadNote state={state} />
        </div>
      ) : (
        <Sections a={state.data} onSelectChw={onSelectChw} onAsk={onAsk} />
      )}
    </div>
  );
}

function Sections({
  a,
  onSelectChw,
  onAsk,
}: {
  a: Anomalies;
  onSelectChw: (id: string) => void;
  onAsk: (q: string) => void;
}) {
  const chip = (id: string | null) =>
    id ? (
      <button
        className="chip chip-clickable"
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onSelectChw(id);
        }}
      >
        {id}
      </button>
    ) : null;

  return (
    <div className="anomalies">
      <Group title="Patients to reach today" tone="alert" empty="No children with danger signs and no overdue follow-ups.">
        {a.children.map((c) => (
          <Item
            key={`child-${c.patient_name}`}
            primary={`${c.patient_name}, ${c.age_months} months: breathing ${c.respiratory_rate}/min${
              c.temperature_c ? `, ${c.temperature_c} °C` : ""
            }`}
            secondary={`Danger signs · seen ${shortDate(c.date)} in ${c.ward ?? "unknown ward"} · needs same-day referral`}
            chip={chip(c.chw_id)}
          />
        ))}
        {a.overdue.map((p) => (
          <Item
            key={`overdue-${p.patient_name}`}
            primary={`${p.patient_name}: ${p.days_overdue} days overdue${p.pregnant ? ", pregnant" : ""}${
              p.last_systolic_bp ? `, last BP ${p.last_systolic_bp}` : ""
            }`}
            secondary={`Return visit was due ${shortDate(p.return_date)} · last seen ${shortDate(p.last_visit)} in ${p.ward ?? "unknown ward"}`}
            chip={chip(p.chw_id)}
            urgent={(p.last_systolic_bp ?? 0) >= 140}
          />
        ))}
      </Group>

      <Group title="Possible outbreaks" tone="alert" empty="No ward has three or more fever cases.">
        {a.fever_clusters.map((w) => (
          <Item
            key={w.ward}
            primary={`${w.ward}: ${w.case_count} fever cases, ${w.malaria_diagnosed} with malaria`}
            secondary={`${shortDate(w.first_date)} – ${shortDate(w.last_date)}`}
            chip={<>{w.chw_ids.map((id) => <span key={id}>{chip(id)}</span>)}</>}
          />
        ))}
      </Group>

      <Group title="CHW activity" tone="warn" empty="Every CHW kept the team's working pattern.">
        {a.activity_gaps.rows.map((g) => (
          <Item
            key={g.chw_id}
            primary={`${PATTERN_LABELS[g.pattern]}: ${patternNote(g.pattern, g.last_active)}`}
            secondary={
              g.pattern === "stopped_early"
                ? `Missed ${g.weekdays_missed_before_team_last_active} working days the rest of the team worked`
                : g.first_active
                  ? `First visit ${shortDate(g.first_active)}`
                  : "No visits in the window"
            }
            chip={chip(g.chw_id)}
            onClick={() => onSelectChw(g.chw_id)}
          />
        ))}
      </Group>

      <Group title="Records to check" tone="warn" empty="No records out of line.">
        {a.visits_after_death.rows.map((v) => (
          <Item
            key={`death-${v.patient_name}-${v.visit_date}`}
            primary={`Visit to ${v.patient_name} on ${shortDate(v.visit_date)}`}
            secondary={`Death recorded ${shortDate(v.death_date)} · ${v.ward ?? "unknown ward"}`}
            chip={chip(v.chw_id)}
          />
        ))}
        {a.missing_location.total_missing_location > 0 && (
          <Item
            primary={`${a.missing_location.total_missing_location} visits saved with no location`}
            secondary={a.missing_location.rows
              .map((r) => `${r.chw_id} ×${r.missing_location}`)
              .join(" · ")}
          />
        )}
      </Group>

      <button
        className="btn-primary anomalies__ask"
        type="button"
        onClick={() => onAsk("Surface anomalies only, ranked by urgency, with a next step for each.")}
      >
        Ask the briefing team to rank these
        <ArrowRight size={14} />
      </button>
    </div>
  );
}

function Group({
  title,
  tone,
  empty,
  children,
}: {
  title: string;
  tone: "alert" | "warn";
  empty: string;
  children: ReactNode;
}) {
  const items = (Array.isArray(children) ? children.flat() : [children]).filter(Boolean);
  return (
    <section className="ranked">
      <div className={cn("ranked__head", `ranked__head--${tone}`)}>
        <span className="pip" />
        <span>{title}</span>
        <span className="ml-auto font-mono text-[11px] text-[var(--ink-3)]">{items.length}</span>
      </div>
      {items.length ? children : <div className="anomalies__empty">{empty}</div>}
    </section>
  );
}

function Item({
  primary,
  secondary,
  chip,
  urgent,
  onClick,
}: {
  primary: string;
  secondary: string;
  chip?: ReactNode;
  urgent?: boolean;
  onClick?: () => void;
}) {
  return (
    <div
      className={cn("anomaly-row", onClick && "is-clickable")}
      onClick={onClick}
    >
      <div className="min-w-0">
        <div className={cn("ranked__row__primary", urgent && "tone-alert")}>{primary}</div>
        <div className="ranked__row__secondary">{secondary}</div>
      </div>
      <div className="anomaly-row__chips">{chip}</div>
    </div>
  );
}
