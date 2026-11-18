import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { Turn } from "@/components/Conversation";
import { loadTurns, saveTurns } from "@/lib/persist";
import { EMPTY_TEAM } from "@/lib/team";

const KEY = "field-briefing:turns:v1";

function aiTurn(done: boolean): Turn {
  return {
    id: "a1",
    role: "ai",
    team: { ...EMPTY_TEAM, done },
    doc: null,
    sources: [],
    traceId: null,
    traceUrl: null,
    done,
  };
}

// jsdom in this setup has no localStorage; give each test an in-memory one.
beforeEach(() => {
  const store = new Map<string, string>();
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
      removeItem: (k: string) => void store.delete(k),
    },
  });
});

afterEach(() => {
  Reflect.deleteProperty(window, "localStorage");
});

describe("persist", () => {
  it("round-trips a conversation", () => {
    const turns: Turn[] = [{ id: "u1", role: "user", q: "hello", t: "07:42" }];
    saveTurns(turns);
    expect(loadTurns()).toEqual(turns);
  });

  it("closes a run that was still streaming when the page closed", () => {
    saveTurns([aiTurn(false)]);
    const [turn] = loadTurns();
    if (turn.role !== "ai") throw new Error("expected an ai turn");
    expect(turn.done).toBe(true);
    expect(turn.team.done).toBe(true);
    expect(turn.doc?.headline).toMatch(/interrupted/);
  });

  it("starts empty when the saved data is unreadable", () => {
    window.localStorage.setItem(KEY, "{not json");
    expect(loadTurns()).toEqual([]);
  });

  it("clears storage when the conversation is cleared", () => {
    saveTurns([aiTurn(true)]);
    saveTurns([]);
    expect(window.localStorage.getItem(KEY)).toBeNull();
  });
});
