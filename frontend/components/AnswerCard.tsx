"use client";

import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ExternalLink,
  Lightbulb,
} from "lucide-react";
import type {
  AnswerDoc,
  PanelRow,
  RankedItem,
  Section,
  Stat,
  Tone,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { useDebug } from "@/lib/debug";

/* ─── small helpers ──────────────────────────────────────────────────── */

function ChwChip({
  id,
  onClick,
}: {
  id: string;
  onClick?: (id: string) => void;
}) {
  // Render a plain <span> unless an onClick is supplied. Inside a ranked row
  // (which is itself a <button>) a nested <button> is invalid HTML and trips
  // a hydration error; the row already handles the click, so the chip there
  // is decorative. Standalone, clickable chips still get a real button.
  if (!onClick) {
    return <span className="chip">{id}</span>;
  }
  return (
    <button
      className="chip chip-clickable"
      onClick={() => onClick(id)}
      type="button"
    >
      {id}
    </button>
  );
}

function CalloutIcon({ tone }: { tone: Tone }) {
  // A lightbulb reads as "insight", not the old "?" which implied confusion.
  const Icon =
    tone === "alert" ? AlertTriangle : tone === "warn" ? Lightbulb : CheckCircle2;
  return <Icon size={12} strokeWidth={2.5} />;
}

/* ─── section renderers ──────────────────────────────────────────────── */

function StatRow({ stats }: { stats: Stat[] }) {
  return (
    <div className="stat-row">
      {stats.map((s, i) => (
        <div key={i} className="stat-tile">
          <div className="stat-tile__label">{s.label}</div>
          <div className="stat-tile__value">{s.value}</div>
          <div className={cn("stat-tile__delta", `tone-${s.deltaTone}`)}>
            {s.delta}
          </div>
          <div className="stat-tile__sub">{s.sub}</div>
        </div>
      ))}
    </div>
  );
}

function Callout({
  tone,
  title,
  body,
  evidence,
}: {
  tone: Tone;
  title: string;
  body: string;
  evidence: string[];
}) {
  return (
    <div className={cn("callout", `callout--${tone}`)}>
      <div className="callout__icon">
        <CalloutIcon tone={tone} />
      </div>
      <div>
        <div className="callout__title">{title}</div>
        <div className="callout__body">{body}</div>
        {evidence.length > 0 && (
          <div className="callout__evidence">
            {evidence.map((e) => (
              <span key={e} className="chip">
                {e}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function Ranked({
  title,
  tone,
  items,
  onSelectChw,
}: {
  title: string;
  tone: Tone;
  items: RankedItem[];
  onSelectChw?: (id: string) => void;
}) {
  return (
    <div className="ranked">
      <div className={cn("ranked__head", `ranked__head--${tone}`)}>
        <span className="pip" />
        <span>{title}</span>
      </div>
      {items.map((it, i) => (
        <button
          key={i}
          className="ranked__row text-left w-full"
          onClick={() => onSelectChw?.(it.id)}
          type="button"
        >
          <ChwChip id={it.id} />
          <div>
            <div className="ranked__row__primary">{it.primary}</div>
            <div className="ranked__row__secondary">{it.secondary}</div>
          </div>
          <ArrowRight size={14} className="text-[var(--ink-4)]" />
        </button>
      ))}
    </div>
  );
}

function Panel({ title, rows }: { title: string; rows: PanelRow[] }) {
  return (
    <div className="panel">
      <div className="panel__head">{title}</div>
      {rows.map((r, i) => (
        <div key={i} className="panel__row">
          <div className="font-medium">{r.left}</div>
          <div className="panel__row__mid">{r.mid}</div>
          <div className="panel__row__right">{r.right}</div>
        </div>
      ))}
    </div>
  );
}

/* ─── orchestrator ───────────────────────────────────────────────────── */

export function AnswerCard({
  doc,
  sources,
  traceId,
  onSelectChw,
}: {
  doc: AnswerDoc;
  sources: string[];
  traceId: string | null;
  onSelectChw?: (id: string) => void;
}) {
  return (
    <article className="ans">
      {doc.period && <div className="ans__period">{doc.period}</div>}
      <h2 className="ans__head">{doc.headline}</h2>
      <div className="ans__sections">
        {doc.sections.map((sec, i) => (
          <SectionRenderer key={i} section={sec} onSelectChw={onSelectChw} />
        ))}
      </div>
      <TraceFooter sources={sources} traceId={traceId} />
    </article>
  );
}

function SectionRenderer({
  section,
  onSelectChw,
}: {
  section: Section;
  onSelectChw?: (id: string) => void;
}) {
  switch (section.kind) {
    case "stat-row":
      return <StatRow stats={section.stats} />;
    case "callout":
      return (
        <Callout
          tone={section.tone}
          title={section.title}
          body={section.body}
          evidence={section.evidence}
        />
      );
    case "ranked":
      return (
        <Ranked
          title={section.title}
          tone={section.tone}
          items={section.items}
          onSelectChw={onSelectChw}
        />
      );
    case "panel":
      return <Panel title={section.title} rows={section.rows} />;
  }
}

function TraceFooter({
  sources,
  traceId,
}: {
  sources: string[];
  traceId: string | null;
}) {
  const { debug } = useDebug();
  const langfuseHost =
    process.env.NEXT_PUBLIC_LANGFUSE_HOST ?? "http://localhost:3100";
  const shortId = traceId ? traceId.slice(0, 8) : null;
  return (
    <div className="trace-footer">
      <span className="trace-footer__label">sources</span>
      {sources.map((s) => (
        <span key={s} className="chip">
          {s}
        </span>
      ))}
      {debug && shortId && (
        <a
          className="trace-footer__link inline-flex items-center gap-1"
          href={`${langfuseHost}/trace/${traceId}`}
          target="_blank"
          rel="noreferrer"
        >
          trace · {shortId} <ExternalLink size={10} />
        </a>
      )}
    </div>
  );
}
