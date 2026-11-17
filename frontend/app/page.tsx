"use client";

import { useEffect, useRef, useState } from "react";
import { Sidebar, type NavId } from "@/components/Sidebar";
import { Topbar } from "@/components/Topbar";
import { Hero } from "@/components/Hero";
import { Composer } from "@/components/Composer";
import { AiTurn, UserTurn, type Turn } from "@/components/Conversation";
import { ChwDrawer } from "@/components/ChwDrawer";
import { getReady, streamBriefing } from "@/lib/api";
import { EMPTY_TEAM, applyFrame } from "@/lib/team";

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
  const [drawerChw, setDrawerChw] = useState<string | null>(null);
  const [backendStatus, setBackendStatus] = useState<
    "checking" | "ready" | "down"
  >("checking");
  const [backendReason, setBackendReason] = useState<string>(
    "Checking backend...",
  );
  // Active stream's close() — invoked on unmount so EventSource doesn't
  // outlive the page. Also lets a future "stop" button cancel a run.
  const closeStream = useRef<(() => void) | null>(null);
  // Scroll container + "user is pinned to bottom" flag. We only auto-scroll
  // while pinned so a manual scroll-up to re-read isn't yanked back down.
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const pinnedRef = useRef(true);

  useEffect(() => () => closeStream.current?.(), []);

  // Mount-time backend probe. Aborts on unmount so a slow probe doesn't
  // setState after teardown.
  useEffect(() => {
    const ctrl = new AbortController();
    getReady({ signal: ctrl.signal })
      .then((r) => {
        if (r.status === "ready") {
          setBackendStatus("ready");
          return;
        }
        setBackendStatus("down");
        setBackendReason(
          r.openmrs
            ? "Backend unavailable - downstream not ready."
            : "Backend unavailable - OpenMRS unreachable.",
        );
      })
      .catch((e: unknown) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setBackendStatus("down");
        setBackendReason("Backend unavailable - cannot reach service.");
      });
    return () => ctrl.abort();
  }, []);

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
      team: EMPTY_TEAM,
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
          patchAi((t) => {
            const next = { ...t, team: applyFrame(t.team, frame) };
            if (frame.kind === "response") {
              return {
                ...next,
                doc: frame.answer_doc,
                sources: frame.answer_doc?.sources ?? [],
                traceId: frame.trace_id,
                done: true,
              };
            }
            if (frame.kind === "error") {
              return {
                ...next,
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
              };
            }
            return next;
          });
        },
        onTransportError: (e) => {
          console.error("briefing stream transport error", e);
          patchAi((t) =>
            t.done
              ? t
              : {
                  ...t,
                  team: { ...t.team, done: true },
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
    <div className="app-shell grid h-[100dvh]">
      <Sidebar active={nav} onSelect={setNav} />
      <div className="main-stage flex flex-col overflow-hidden">
        <Topbar breadcrumb={`workspace / ${navLabel(nav)}`} />
        <main ref={scrollRef} onScroll={onScroll} className="content-scroll flex-1 overflow-y-auto">
          {isEmpty ? (
            <Hero onAsk={ask} />
          ) : (
            <div className="pb-4">
              {turns.map((t) =>
                t.role === "user" ? (
                  <UserTurn key={t.id} q={t.q} t={t.t} />
                ) : (
                  <AiTurn key={t.id} turn={t} onSelectChw={setDrawerChw} />
                ),
              )}
            </div>
          )}
        </main>
        <Composer
          busy={busy}
          onSubmit={ask}
          disabled={backendStatus !== "ready"}
          disabledReason={
            backendStatus === "checking" ? "Checking backend..." : backendReason
          }
        />
      </div>
      <ChwDrawer
        chwId={drawerChw}
        onClose={() => setDrawerChw(null)}
        onAsk={ask}
      />
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
