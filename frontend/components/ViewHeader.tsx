import type { LoadState } from "@/lib/useLoad";

/** Kicker line and serif title shared by the non-conversation views. */
export function ViewHeader({ kicker, title }: { kicker: string; title: string }) {
  return (
    <>
      <div className="hero-kicker">
        <span className="pulse-dot pulse-dot--ok" />
        {kicker}
      </div>
      <h1 className="view-title">{title}</h1>
    </>
  );
}

/** "Loading…" or the error, for a view still waiting on its data. */
export function LoadNote({ state }: { state: LoadState<unknown> }) {
  if (state.status === "loading") {
    return <div className="drawer__note">Loading from OpenMRS…</div>;
  }
  if (state.status === "error") {
    return (
      <div className="drawer__note drawer__note--alert" role="alert">
        {state.message}
      </div>
    );
  }
  return null;
}
