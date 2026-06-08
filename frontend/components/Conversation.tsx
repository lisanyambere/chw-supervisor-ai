"use client";

import type { AnswerDoc, PlanStep } from "@/lib/api";
import { AnswerCard } from "@/components/AnswerCard";
import { PlanTimeline } from "@/components/PlanTimeline";
import { useDebug } from "@/lib/debug";

export type Turn =
  | { id: string; role: "user"; q: string; t: string }
  | {
      id: string;
      role: "ai";
      plan: PlanStep[];
      activeIdx: number;
      doc: AnswerDoc | null;
      sources: string[];
      traceId: string | null;
      done: boolean;
    };

export function UserTurn({ q, t }: { q: string; t: string }) {
  return (
    <div className="max-w-[940px] mx-auto px-6 pt-6">
      <div className="flex items-center gap-2 mb-3">
        <div
          className="w-[18px] h-[18px] rounded-full grid place-items-center text-[9px] font-mono font-semibold"
          style={{ background: "var(--accent-2)", color: "var(--accent-ink)" }}
        >
          MK
        </div>
        <div className="font-mono text-[12px] text-[var(--ink-3)]">you · {t}</div>
      </div>
      <div className="user-turn">{q}</div>
    </div>
  );
}

export function AiTurn({
  turn,
  onSelectChw,
}: {
  turn: Extract<Turn, { role: "ai" }>;
  onSelectChw?: (id: string) => void;
}) {
  const { debug } = useDebug();
  return (
    <div className="max-w-[940px] mx-auto px-6 pt-6 space-y-4">
      {/* The tool plan is developer instrumentation — Debug Mode only. */}
      {debug && turn.plan.length > 0 && (
        <PlanTimeline plan={turn.plan} activeIdx={turn.activeIdx} done={turn.done} />
      )}
      {/* Default view gets a clean "working" pill instead of the raw plan. */}
      {!debug && !turn.done && (
        <div className="thinking">
          <span className="spinner" />
          Analyzing the team’s activity…
        </div>
      )}
      {turn.doc && (
        <AnswerCard
          doc={turn.doc}
          sources={turn.sources}
          traceId={turn.traceId}
          onSelectChw={onSelectChw}
        />
      )}
    </div>
  );
}
