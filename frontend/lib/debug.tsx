"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";

/**
 * Debug Mode — hides developer-facing instrumentation (the tool plan, ms
 * timings, trace ids, raw provider/model strings, observability links) behind
 * an opt-in toggle so the default view stays clean for a field supervisor.
 *
 * Toggle with the topbar control or Ctrl/Cmd + Shift + D. Persisted to
 * localStorage so a developer's preference survives reloads.
 */

type DebugContextValue = {
  debug: boolean;
  toggle: () => void;
  set: (value: boolean) => void;
};

const DebugContext = createContext<DebugContextValue>({
  debug: false,
  toggle: () => {},
  set: () => {},
});

const STORAGE_KEY = "cha:debug:v1";

export function DebugProvider({ children }: { children: React.ReactNode }) {
  const [debug, setDebug] = useState(false);

  // Hydrate once on mount. Defaults to off (supervisor view) when unset.
  useEffect(() => {
    try {
      setDebug(window.localStorage.getItem(STORAGE_KEY) === "1");
    } catch {
      // Private mode / quota — just stay in the default (off) state.
    }
  }, []);

  // Persist on change.
  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, debug ? "1" : "0");
    } catch {
      // Ignore persistence failures.
    }
  }, [debug]);

  // Keyboard shortcut: Ctrl/Cmd + Shift + D.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (
        (e.ctrlKey || e.metaKey) &&
        e.shiftKey &&
        (e.key === "D" || e.key === "d")
      ) {
        e.preventDefault();
        setDebug((d) => !d);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const toggle = useCallback(() => setDebug((d) => !d), []);

  return (
    <DebugContext.Provider value={{ debug, toggle, set: setDebug }}>
      {children}
    </DebugContext.Provider>
  );
}

export function useDebug(): DebugContextValue {
  return useContext(DebugContext);
}
