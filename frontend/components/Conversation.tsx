"use client";

import type { AnswerDoc } from "@/lib/api";
import type { TeamRun } from "@/lib/team";
import { AnswerCard } from "@/components/AnswerCard";
import { TeamTimeline } from "@/components/TeamTimeline";

export type Turn =
  | { id: string; role: "user"; q: string; t: string }
  | {
      id: string;
      role: "ai";
      team: TeamRun;
      doc: AnswerDoc | null;
      sources: string[];
      traceId: string | null;
      traceUrl: string | null;
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
        <div className="font-mono text-[11px] text-[var(--ink-3)]">you · {t}</div>
      </div>
      <div
        className="font-serif text-[22px] leading-[1.3] pl-4"
        style={{ borderLeft: "2px solid var(--line-2)" }}
      >
        {q}
      </div>
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
  return (
    <div className="max-w-[940px] mx-auto px-6 pt-6 space-y-4">
      <TeamTimeline team={turn.team} />
      {turn.doc && (
        <AnswerCard
          doc={turn.doc}
          sources={turn.sources}
          traceId={turn.traceId}
          traceUrl={turn.traceUrl}
          onSelectChw={onSelectChw}
        />
      )}
    </div>
  );
}
