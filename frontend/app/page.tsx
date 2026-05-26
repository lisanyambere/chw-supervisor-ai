"use client";

import { useEffect, useRef, useState } from "react";
import { Sidebar, type NavId } from "@/components/Sidebar";
import { Topbar } from "@/components/Topbar";
import { Hero } from "@/components/Hero";
import { Composer } from "@/components/Composer";
import { AiTurn, UserTurn, type Turn } from "@/components/Conversation";
import { streamBriefing, type PlanStep } from "@/lib/api";

function uid() {
  return Math.random().toString(36).slice(2, 10);
}

function nowHHMM() {
  const d = new Date();
  return `${d.getHours().toString().padStart(2, "0")}:${d
    .getMinutes()
    .toString()
    .padStart(2, "0")}`;
}

export default function HomePage() {
  const [nav, setNav] = useState<NavId>("brief");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  // Active stream's close() — invoked on unmount so EventSource doesn't
  // outlive the page. Also lets a future "stop" button cancel a run.
  const closeStream = useRef<(() => void) | null>(null);
  // Scroll container + "user is pinned to bottom" flag. We only auto-scroll
  // while pinned so a manual scroll-up to re-read isn't yanked back down.
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const pinnedRef = useRef(true);

  useEffect(() => () => closeStream.current?.(), []);

  // Re-pin whenever turns change and we were already at the bottom.
  useEffect(() => {
    if (!pinnedRef.current) return;
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [turns]);

  function onScroll() {
    const el = scrollRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    pinnedRef.current = distanceFromBottom < 64;
  }

  function ask(q: string) {
    if (busy) return;
    setBusy(true);
    const userTurn: Turn = { id: uid(), role: "user", q, t: nowHHMM() };
    const aiId = uid();
    const placeholder: Turn = {
      id: aiId,
      role: "ai",
      plan: [],
      activeIdx: 0,
      doc: null,
      sources: [],
      traceId: null,
      done: false,
    };
    setTurns((prev) => [...prev, userTurn, placeholder]);

    // Helper: mutate just the matching AI turn.
    const patchAi = (
      patch: (t: Extract<Turn, { role: "ai" }>) => Extract<Turn, { role: "ai" }>,
    ) =>
      setTurns((prev) =>
        prev.map((t) => (t.id === aiId && t.role === "ai" ? patch(t) : t)),
      );

    closeStream.current = streamBriefing(
      q,
      {
        onFrame: (frame) => {
          if (frame.kind === "tool_start") {
            // Append a row in `running` state — the spinner is driven by
            // i === activeIdx, so we push a placeholder PlanStep and bump
            // activeIdx to it.
            const step: PlanStep = {
              tool: frame.tool,
              args: frame.args,
              ms: 0,
              rows: 0,
            };
            patchAi((t) => ({
              ...t,
              plan: [...t.plan, step],
              activeIdx: t.plan.length,
            }));
          } else if (frame.kind === "tool_done") {
            // Replace the matching pending row with timed values. Match
            // on (tool, args) FIFO — same semantics as backend _derive_plan.
            patchAi((t) => {
              const idx = t.plan.findIndex(
                (s) =>
                  s.tool === frame.tool &&
                  s.args === frame.args &&
                  s.ms === 0,
              );
              if (idx === -1) return t;
              const next = t.plan.slice();
              next[idx] = {
                tool: frame.tool,
                args: frame.args,
                ms: frame.ms,
                rows: frame.rows,
              };
              return { ...t, plan: next, activeIdx: idx + 1 };
            });
          } else if (frame.kind === "response") {
            patchAi((t) => ({
              ...t,
              plan: frame.plan, // canonical ordering from backend
              activeIdx: frame.plan.length,
              doc: frame.answer_doc,
              sources: frame.answer_doc?.sources ?? [],
              traceId: frame.trace_id,
              done: true,
            }));
          } else if (frame.kind === "error") {
            patchAi((t) => ({
              ...t,
              plan: [],
              doc: {
                headline: "The briefing run failed.",
                period: "",
                sections: [
                  {
                    kind: "callout",
                    tone: "alert",
                    title: "Agent error",
                    body: frame.message,
                    evidence: [],
                  },
                ],
                sources: [],
              },
              done: true,
            }));
          }
        },
        onTransportError: (e) => {
          console.error("briefing stream transport error", e);
          patchAi((t) =>
            t.done
              ? t
              : {
                  ...t,
                  doc: {
                    headline: "Couldn't reach the briefing service.",
                    period: "",
                    sections: [
                      {
                        kind: "callout",
                        tone: "alert",
                        title: "Connection lost",
                        body: "The SSE stream dropped before the agent finished.",
                        evidence: [],
                      },
                    ],
                    sources: [],
                  },
                  done: true,
                },
          );
        },
        onClose: () => {
          closeStream.current = null;
          setBusy(false);
        },
      },
      { lookbackDays: 30 },
    );
  }

  const isEmpty = turns.length === 0;

  return (
    <div
      className="grid h-screen"
      style={{ gridTemplateColumns: "244px 1fr" }}
    >
      <Sidebar active={nav} onSelect={setNav} />
      <div className="flex flex-col overflow-hidden">
        <Topbar breadcrumb={`workspace / ${navLabel(nav)}`} />
        <div ref={scrollRef} onScroll={onScroll} className="flex-1 overflow-y-auto">
          {isEmpty ? (
            <Hero onAsk={ask} />
          ) : (
            <div className="pb-4">
              {turns.map((t) =>
                t.role === "user" ? (
                  <UserTurn key={t.id} q={t.q} t={t.t} />
                ) : (
                  <AiTurn key={t.id} turn={t} />
                ),
              )}
            </div>
          )}
        </div>
        <Composer busy={busy} onSubmit={ask} />
      </div>
    </div>
  );
}

function navLabel(id: NavId): string {
  return {
    brief: "Monday briefing",
    alert: "Anomalies",
    team: "CHW roster",
    patient: "Patient lookup",
    chart: "Activity charts",
  }[id];
}
