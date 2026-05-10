"use client";

import { useState } from "react";
import { Sidebar, type NavId } from "@/components/Sidebar";
import { Topbar } from "@/components/Topbar";
import { Hero } from "@/components/Hero";
import { Composer } from "@/components/Composer";
import { AiTurn, UserTurn, type Turn } from "@/components/Conversation";
import { postBriefing } from "@/lib/api";

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

  async function ask(q: string) {
    if (busy) return;
    setBusy(true);
    const userTurn: Turn = { id: uid(), role: "user", q, t: nowHHMM() };
    const aiId = uid();
    // Placeholder AI turn with a single "thinking" row until the real plan
    // lands. No fake choreography — when /briefing resolves we swap in the
    // real plan with backend-measured ms timings, all marked done at once.
    const placeholder: Turn = {
      id: aiId,
      role: "ai",
      plan: [{ tool: "agent", args: "(thinking…)", ms: 0, rows: 0 }],
      activeIdx: 0,
      doc: null,
      sources: [],
      traceId: null,
      done: false,
    };
    setTurns((prev) => [...prev, userTurn, placeholder]);

    try {
      const res = await postBriefing(q);
      setTurns((prev) =>
        prev.map((t) =>
          t.id === aiId && t.role === "ai"
            ? {
                ...t,
                plan: res.plan,
                activeIdx: res.plan.length,
                doc: res.answer_doc,
                sources: res.answer_doc?.sources ?? [],
                traceId: res.trace_id,
                done: true,
              }
            : t,
        ),
      );
    } catch (err) {
      console.error(err);
      setTurns((prev) =>
        prev.map((t) =>
          t.id === aiId && t.role === "ai"
            ? {
                ...t,
                plan: [],
                doc: {
                  headline: "Couldn't reach the briefing service.",
                  period: "",
                  sections: [
                    {
                      kind: "callout",
                      tone: "alert",
                      title: "Request failed",
                      body: String(err),
                      evidence: [],
                    },
                  ],
                  sources: [],
                },
                done: true,
              }
            : t,
        ),
      );
    } finally {
      setBusy(false);
    }
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
        <div className="flex-1 overflow-y-auto">
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
