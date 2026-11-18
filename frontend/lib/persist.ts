import type { Turn } from "@/components/Conversation";

// Bump the version whenever the Turn shape changes, so an old saved
// conversation is dropped instead of crashing the renderer.
const KEY = "field-briefing:turns:v1";

/** The saved conversation, or [] when there is none or storage is blocked. */
export function loadTurns(): Turn[] {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return [];
    const turns = JSON.parse(raw) as Turn[];
    // A run in progress when the page closed can never finish: its stream
    // is gone. Close it with a note rather than leave it spinning.
    return turns.map((t) =>
      t.role === "ai" && !t.done
        ? {
            ...t,
            done: true,
            team: { ...t.team, done: true, revising: false },
            doc: t.doc ?? {
              headline: "This run was interrupted when the page closed.",
              period: "",
              sections: [],
              sources: [],
            },
          }
        : t,
    );
  } catch {
    return [];
  }
}

export function saveTurns(turns: Turn[]): void {
  try {
    if (turns.length) window.localStorage.setItem(KEY, JSON.stringify(turns));
    else window.localStorage.removeItem(KEY);
  } catch {
    // Storage full or blocked (private mode): the conversation still works,
    // it just will not survive a reload.
  }
}
