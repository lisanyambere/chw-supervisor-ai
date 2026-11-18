import { useEffect, useState } from "react";

export type LoadState<T> =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: T };

/**
 * Run `load` on mount (and when `key` changes), aborting it on unmount, and
 * track its outcome. `key` stands in for a dependency list.
 */
export function useLoad<T>(
  load: (signal: AbortSignal) => Promise<T>,
  key: unknown = null,
): LoadState<T> {
  const [state, setState] = useState<LoadState<T>>({ status: "loading" });
  useEffect(() => {
    setState({ status: "loading" });
    const ctrl = new AbortController();
    load(ctrl.signal)
      .then((data) => setState({ status: "ready", data }))
      .catch((e: unknown) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setState({
          status: "error",
          message: e instanceof Error ? e.message : "Request failed.",
        });
      });
    return () => ctrl.abort();
    // `load` is usually an inline closure; re-running on `key` is the intent.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return state;
}
