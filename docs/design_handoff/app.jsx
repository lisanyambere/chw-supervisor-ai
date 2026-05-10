/* eslint-disable */
const { useState, useEffect, useRef, useMemo, Fragment } = React;
const D = window.PROTO_DATA;

// ── Icons (inline, minimal) ─────────────────────────────────────────────
const I = {
  brief:  (p) => <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.5" {...p}><path d="M2 4h12M2 8h12M2 12h7"/></svg>,
  alert:  (p) => <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.5" {...p}><path d="M8 2L1.5 13.5h13L8 2zM8 6.5v3M8 11.5v.1"/></svg>,
  team:   (p) => <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.5" {...p}><circle cx="6" cy="6" r="2.5"/><path d="M2 13.5c0-2.2 1.8-4 4-4s4 1.8 4 4"/><circle cx="11" cy="5.5" r="2"/><path d="M10 13.5c0-1.5 1-3.2 3.5-3.5"/></svg>,
  panel:  (p) => <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.5" {...p}><rect x="2" y="3" width="12" height="10" rx="1"/><path d="M2 6.5h12"/></svg>,
  chart:  (p) => <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.5" {...p}><path d="M2 13h12M4 11V7M7 11V4M10 11V8M13 11V5"/></svg>,
  arrow:  (p) => <svg viewBox="0 0 16 16" width="10" height="10" fill="none" stroke="currentColor" strokeWidth="1.5" {...p}><path d="M3 8h10M9 4l4 4-4 4"/></svg>,
  send:   (p) => <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M2 8L14 2L9 14L7.5 9L2 8z"/></svg>,
  ext:    (p) => <svg viewBox="0 0 16 16" width="10" height="10" fill="none" stroke="currentColor" strokeWidth="1.5" {...p}><path d="M6 3H3v10h10v-3M9 3h4v4M13 3L7 9"/></svg>,
  check:  (p) => <svg viewBox="0 0 10 10" width="10" height="10" fill="none" stroke="white" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M2 5l2 2 4-4"/></svg>,
  x:      (p) => <svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" {...p}><path d="M3 3l10 10M13 3L3 13"/></svg>,
  attach: (p) => <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.5" {...p}><path d="M11 5L5.5 10.5a2 2 0 002.8 2.8L14 7.5a3.5 3.5 0 00-4.9-4.9L3.2 8.5a5 5 0 007 7l5.3-5.3"/></svg>,
};

// ── Sidebar ─────────────────────────────────────────────────────────────
function Sidebar({ active, onNav, alerts }) {
  return (
    <aside className="sb">
      <div className="sb__brand">
        <div className="sb__mark">CH</div>
        <div>
          <div className="sb__title">Field Briefing</div>
          <div className="sb__sub">kakamega · v0.3</div>
        </div>
      </div>

      <div className="sb__group">
        <div className="sb__label">Workspace</div>
        <button className={"sb__item" + (active === "brief" ? " is-active" : "")} onClick={() => onNav("brief")}>
          <I.brief /> Monday briefing
        </button>
        <button className={"sb__item is-alert" + (active === "alert" ? " is-active" : "")} onClick={() => onNav("alert")}>
          <I.alert /> Anomalies <span className="sb__count">{alerts}</span>
        </button>
        <button className={"sb__item" + (active === "team" ? " is-active" : "")} onClick={() => onNav("team")}>
          <I.team /> CHW roster <span className="sb__count">30</span>
        </button>
        <button className={"sb__item" + (active === "patient" ? " is-active" : "")} onClick={() => onNav("patient")}>
          <I.panel /> Patient lookup
        </button>
        <button className={"sb__item" + (active === "chart" ? " is-active" : "")} onClick={() => onNav("chart")}>
          <I.chart /> Activity charts
        </button>
      </div>

      <div className="sb__group">
        <div className="sb__label">Observability</div>
        <a className="sb__ext" href="#" onClick={e => e.preventDefault()}>langfuse <span className="arr"><I.ext /></span></a>
        <a className="sb__ext" href="#" onClick={e => e.preventDefault()}>grafana <span className="arr"><I.ext /></span></a>
        <a className="sb__ext" href="#" onClick={e => e.preventDefault()}>openmrs <span className="arr"><I.ext /></span></a>
        <a className="sb__ext" href="#" onClick={e => e.preventDefault()}>prometheus <span className="arr"><I.ext /></span></a>
      </div>

      <div className="sb__user">
        <div className="sb__avatar">MK</div>
        <div>
          <div className="sb__user-name">Margaret Kimani</div>
          <div className="sb__user-role">Program supervisor</div>
        </div>
      </div>
    </aside>
  );
}

// ── Tool plan timeline ──────────────────────────────────────────────────
function PlanTimeline({ plan, progressIndex, doneAt }) {
  return (
    <div className="plan">
      <div className="plan__head">
        <span>Tool plan</span>
        {progressIndex < plan.length ? (
          <span className="live"><span className="dot"></span> running</span>
        ) : (
          <span style={{ marginLeft: "auto", color: "var(--ok)" }}>completed in {doneAt}ms</span>
        )}
      </div>
      {plan.map((p, i) => {
        const status = i < progressIndex ? "is-done" : i === progressIndex ? "is-running" : "is-pending";
        return (
          <div key={i} className={"plan__row " + status}>
            <div className="plan__bullet">
              {status === "is-done"
                ? <span style={{ background: "var(--ok)", width: 14, height: 14, borderRadius: "50%", display: "grid", placeItems: "center" }}><I.check /></span>
                : <span className="ring"></span>}
            </div>
            <div>
              <span className="plan__name">{p.tool}</span>
              <span className="plan__args"> {p.args}</span>
            </div>
            <div className="plan__rows">{status === "is-pending" ? "—" : `${p.rows} rows`}</div>
            <div className="plan__time">{status === "is-pending" ? "—" : `${p.ms}ms`}</div>
          </div>
        );
      })}
    </div>
  );
}

// ── Stat / callout / ranked / panel sections ────────────────────────────
function Section({ s, onChip }) {
  if (s.kind === "stat-row") {
    return (
      <div className="ans__section statgrid">
        {s.stats.map((st, i) => (
          <div key={i} className="stat">
            <div className="stat__l">{st.label}</div>
            <div className="stat__v">{st.value}</div>
            <div className={"stat__d is-" + st.deltaTone}>{st.delta}</div>
            <div className="stat__s">{st.sub}</div>
          </div>
        ))}
      </div>
    );
  }
  if (s.kind === "callout") {
    const icon = s.tone === "alert" ? "!" : s.tone === "warn" ? "?" : "✓";
    return (
      <div className={"ans__section callout callout--" + s.tone}>
        <div className="callout__icon">{icon}</div>
        <div>
          <div className="callout__t">{s.title}</div>
          <div className="callout__b">{s.body}</div>
          {s.evidence && (
            <div className="callout__ev">
              {s.evidence.map((e, i) => <span key={i} className="tag">{e}</span>)}
            </div>
          )}
        </div>
      </div>
    );
  }
  if (s.kind === "ranked") {
    return (
      <div className={"ans__section ranked ranked--" + s.tone}>
        <div className="ranked__t"><span className="pip"></span>{s.title}</div>
        <div className="ranked__list">
          {s.items.map((it, i) => (
            <div key={i} className="ranked__row" onClick={() => onChip(it.id)}>
              <button className="chip" onClick={e => { e.stopPropagation(); onChip(it.id); }}>{it.id}</button>
              <div>
                <div className="ranked__pri">{it.primary}</div>
                <div className="ranked__sec">{it.secondary}</div>
              </div>
              <div className="ranked__arr"><I.arrow /></div>
            </div>
          ))}
        </div>
      </div>
    );
  }
  if (s.kind === "panel") {
    return (
      <div className="ans__section panel">
        <div className="panel__t">{s.title}</div>
        {s.rows.map((r, i) => (
          <div key={i} className="panel__row">
            <div className="left">{r.left}</div>
            <div className="mid">{r.mid}</div>
            <div className="right">{r.right}</div>
          </div>
        ))}
      </div>
    );
  }
  return null;
}

function Answer({ data, traceId, onChip }) {
  return (
    <div className="ans">
      {data.period && <div className="ans__period">{data.period}</div>}
      <h3 className="ans__head">{data.headline}</h3>
      {data.sections.map((s, i) => <Section key={i} s={s} onChip={onChip} />)}
      <div className="trace">
        <span>sources</span>
        <div className="trace__sources">
          {data.sources.map((s, i) => <span key={i} className="tag">{s}</span>)}
        </div>
        <a className="trace__link" onClick={e => e.preventDefault()}>
          trace · {traceId} <I.ext />
        </a>
      </div>
    </div>
  );
}

// ── Right drawer for CHW detail ─────────────────────────────────────────
function ChwDrawer({ chw, onClose }) {
  const open = !!chw;
  return (
    <Fragment>
      <div className={"drawer-mask " + (open ? "is-open" : "")} onClick={onClose}></div>
      <div className={"drawer " + (open ? "is-open" : "")}>
        {chw && (
          <Fragment>
            <div className="drawer__head">
              <div>
                <div className="drawer__id">{chw.id}</div>
                <div className="drawer__name">{chw.name}</div>
              </div>
              <button className="drawer__close" onClick={onClose}><I.x /></button>
            </div>
            <div className="drawer__body">
              <div className="drawer__row"><span className="k">Sub-county</span><span className="v">{chw.area}</span></div>
              <div className="drawer__row"><span className="k">Encounters · 30d</span><span className="v">{chw.encounters30}</span></div>
              <div className="drawer__row"><span className="k">Encounters · 7d</span><span className="v">{chw.encounters7}</span></div>
              <div className="drawer__row"><span className="k">Status</span><span className="v">{chw.status}</span></div>
              <div className="drawer__row"><span className="k">FHIR Practitioner</span><span className="v">f3a8…b21c</span></div>

              <div className="drawer__chart">
                <h4>Last 7 days · daily encounters</h4>
                <div className="spark">
                  {chw.trend.map((v, i) => (
                    <div key={i} className={"spark__b" + (v === 0 ? " is-zero" : "")} style={{ height: `${(v / 6) * 100}%` }}></div>
                  ))}
                </div>
                <div className="bars__legend">
                  <span>Mon</span><span>Tue</span><span>Wed</span><span>Thu</span><span>Fri</span><span>Sat</span><span>Sun</span>
                </div>
              </div>

              <div style={{ marginTop: 18, display: "flex", gap: 8 }}>
                <button className="btn btn--ghost" style={{ flex: 1 }}>Open patient panel</button>
                <button className="btn btn--ghost" style={{ flex: 1 }}>Call CHW</button>
              </div>
            </div>
          </Fragment>
        )}
      </div>
    </Fragment>
  );
}

// ── Composer ────────────────────────────────────────────────────────────
function Composer({ onSubmit, busy }) {
  const [v, setV] = useState("");
  const ta = useRef(null);
  const submit = () => {
    if (!v.trim() || busy) return;
    onSubmit(v.trim());
    setV("");
    if (ta.current) ta.current.style.height = "auto";
  };
  const onKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
  };
  const grow = (e) => {
    setV(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = Math.min(e.target.scrollHeight, 160) + "px";
  };
  return (
    <div className="composer">
      <div className="composer__inner">
        <div className="composer__row">
          <textarea
            ref={ta}
            className="composer__ta"
            value={v}
            onChange={grow}
            onKeyDown={onKey}
            placeholder={busy ? "Agent running…" : "Ask about a CHW, patient, or trend.  Try \"why is chw-002 quiet?\""}
            rows={1}
            disabled={busy}
          ></textarea>
          <button className="composer__send" onClick={submit} disabled={!v.trim() || busy} aria-label="Send">
            <I.send />
          </button>
        </div>
        <div className="composer__hint">
          <span>↵ send · ⇧↵ newline</span>
          <span className="sep"></span>
          <span>model: <b style={{ color: "var(--ink-2)" }}>gpt-5.5 (azure)</b></span>
          <span className="sep"></span>
          <span>lookback: 30d</span>
          <span className="sep"></span>
          <span className="ok">● fhir healthy</span>
          <span style={{ marginLeft: "auto" }}>verify in OpenMRS before action</span>
        </div>
      </div>
    </div>
  );
}

// ── Hero / empty state ──────────────────────────────────────────────────
function Hero({ onAsk, onBriefing }) {
  const suggestions = [
    { cat: "anomaly",  q: "Why has chw-002 been quiet for the last week?" },
    { cat: "trend",    q: "Show team daily visits for the last 30 days, flag drops." },
    { cat: "panel",    q: "Patient panel for chw-009 — last 30 days, top by encounter count." },
    { cat: "scope",    q: "What happened on Friday May 1? Is it a real outage?" },
  ];
  return (
    <div className="hero">
      <div className="hero__eyebrow"><span className="pulse"></span>Mon · May 10, 2026 · 07:42 EAT</div>
      <h1 className="hero__h">Good morning, Margaret. Here is what <em>changed</em> over the weekend.</h1>
      <p className="hero__sub">
        Your assistant has access to OpenMRS FHIR for 30 CHWs across Kakamega and the last 30 days of encounters.
        Generate the briefing or ask anything in natural language — the agent will plan tool calls, fetch from FHIR, and cite sources.
      </p>
      <div className="cta-row">
        <button className="btn btn--primary" onClick={onBriefing}>
          <I.brief /> Generate Monday briefing <span className="kbd">G</span>
        </button>
        <button className="btn" onClick={() => onAsk("What anomalies should I look at first?")}>
          Surface anomalies only
        </button>
      </div>
      <div className="sugg">
        {suggestions.map((s, i) => (
          <button key={i} className="sugg__item" onClick={() => onAsk(s.q)}>
            <div className="sugg__cat">{s.cat}</div>
            <div className="sugg__q">{s.q}</div>
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Main App ────────────────────────────────────────────────────────────
const BRIEFING_Q = "Give me the Monday morning briefing — top and bottom CHWs, anomalies, data quality issues, and anything I should act on today.";

function App() {
  const [turns, setTurns] = useState([]); // { id, role, q?, plan?, planIdx, response?, traceId, t0 }
  const [busy, setBusy] = useState(false);
  const [drawerChw, setDrawerChw] = useState(null);
  const [active, setActive] = useState("brief");
  const scrollRef = useRef(null);

  const scrollDown = () => {
    requestAnimationFrame(() => {
      if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    });
  };

  const findResponse = (q) => {
    for (const fu of D.FOLLOWUPS) if (fu.match.test(q)) return fu;
    // default echo to briefing
    return { plan: D.BRIEFING_PLAN, response: { ...D.BRIEFING, period: "Apr 11 → May 10 · 30d" } };
  };

  const ask = (q, isBriefing = false) => {
    const matched = isBriefing
      ? { plan: D.BRIEFING_PLAN, response: D.BRIEFING }
      : findResponse(q);

    const userTurn = { id: crypto.randomUUID().slice(0, 8), role: "user", q };
    const aiId = crypto.randomUUID().slice(0, 8);
    const aiTurn = {
      id: aiId,
      role: "ai",
      plan: matched.plan,
      planIdx: 0,
      response: null,
      traceId: aiId + "-" + crypto.randomUUID().slice(0, 4),
      t0: performance.now(),
      _resp: matched.response,
    };

    setTurns(t => [...t, userTurn, aiTurn]);
    setBusy(true);
    scrollDown();

    // Drive the plan animation
    let i = 0;
    const tick = () => {
      const step = matched.plan[i];
      if (!step) {
        const total = matched.plan.reduce((a, p) => a + p.ms, 0);
        setTurns(arr => arr.map(x => x.id === aiId ? { ...x, planIdx: matched.plan.length, response: matched.response, doneAt: total } : x));
        setBusy(false);
        scrollDown();
        return;
      }
      // simulated wall time = real ms scaled down so it feels live but doesn't take 5s
      const wall = Math.max(280, Math.min(900, step.ms * 0.45));
      setTimeout(() => {
        i += 1;
        setTurns(arr => arr.map(x => x.id === aiId ? { ...x, planIdx: i } : x));
        scrollDown();
        tick();
      }, wall);
    };
    tick();
  };

  const onChip = (id) => {
    const chw = D.CHWS.find(c => c.id === id);
    if (chw) setDrawerChw(chw);
  };

  // Activity charts view (simple stand-alone view)
  const renderCharts = () => {
    const max = Math.max(...D.VISITS_BY_DAY);
    return (
      <div style={{ paddingTop: 28 }}>
        <div className="hero__eyebrow"><span className="pulse"></span>Activity · last 30 days</div>
        <h1 className="hero__h" style={{ fontSize: 32 }}>Daily team encounters across Kakamega</h1>
        <div className="ans" style={{ marginTop: 18 }}>
          <div className="ans__period">visits_by_day(30) · per FHIR Encounter.period.start</div>
          <h3 className="ans__head" style={{ fontSize: 16, fontWeight: 600, fontFamily: "var(--sans)" }}>Friday May 1 stands out — the only zero day in the window.</h3>
          <div className="bars">
            {D.VISITS_BY_DAY.map((v, i) => {
              const d = D.VISITS_LABELS[i];
              const wk = d.getDay();
              const cls = v === 0 ? "is-zero" : (wk === 0 || wk === 6) ? "is-weekend" : "";
              return (
                <div key={i} className={"bars__b " + cls} style={{ height: `${(v / max) * 100}%` }} title={`${d.toDateString()}: ${v}`}></div>
              );
            })}
          </div>
          <div className="bars__legend">
            <span>Apr 11</span><span>Apr 18</span><span>Apr 25</span><span>May 1</span>
          </div>
          <div className="trace">
            <span>sources</span>
            <div className="trace__sources">
              <span className="tag">visits_by_day(30)</span>
            </div>
          </div>
        </div>
      </div>
    );
  };

  const renderRoster = () => (
    <div style={{ paddingTop: 28 }}>
      <div className="hero__eyebrow"><span className="pulse"></span>roster · 30 active CHWs</div>
      <h1 className="hero__h" style={{ fontSize: 32 }}>CHW roster — Kakamega</h1>
      <div className="ans" style={{ marginTop: 18, padding: 0 }}>
        {D.CHWS.map((c, i) => (
          <div key={c.id} className="ranked__row" onClick={() => setDrawerChw(c)} style={{ borderBottom: i === D.CHWS.length - 1 ? "none" : "1px solid var(--line)" }}>
            <button className="chip">{c.id}</button>
            <div>
              <div className="ranked__pri">{c.name}</div>
              <div className="ranked__sec">{c.area} · {c.encounters30} enc / 30d · {c.encounters7} / 7d</div>
            </div>
            <div className="ranked__arr"><I.arrow /></div>
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <div className="app">
      <Sidebar active={active} onNav={setActive} alerts={2} />
      <main className="main">
        <div className="topbar">
          <div className="topbar__crumb">workspace / <b>{active === "brief" ? "Monday briefing" : active === "team" ? "CHW roster" : active === "chart" ? "Activity charts" : active === "alert" ? "Anomalies" : "Patient lookup"}</b></div>
          <div className="topbar__date">may 10, 2026 · 07:42</div>
          <div className="topbar__pill"><span className="dot"></span>fhir · langfuse · azure</div>
        </div>

        <div className="scroll" ref={scrollRef}>
          <div className="col">
            {active === "chart" && renderCharts()}
            {active === "team" && renderRoster()}
            {(active === "brief" || active === "alert" || active === "patient") && (
              turns.length === 0
                ? <Hero onAsk={(q) => ask(q)} onBriefing={() => ask(BRIEFING_Q, true)} />
                : (
                  <div style={{ paddingTop: 8 }}>
                    {turns.map(t => t.role === "user" ? (
                      <div key={t.id} className="turn turn--user">
                        <div className="turn__meta"><span className="av">MK</span> you · 07:42</div>
                        <div className="user-q">{t.q}</div>
                      </div>
                    ) : (
                      <div key={t.id} className="turn turn--ai">
                        <div className="turn__meta"><span className="av">CH</span> assistant · gpt-5.5 · trace {t.traceId}</div>
                        <PlanTimeline plan={t.plan} progressIndex={t.planIdx} doneAt={t.doneAt} />
                        {t.response && <Answer data={t.response} traceId={t.traceId} onChip={onChip} />}
                      </div>
                    ))}
                  </div>
                )
            )}
          </div>
        </div>

        {(active === "brief" || active === "alert" || active === "patient") && (
          <Composer onSubmit={(q) => ask(q)} busy={busy} />
        )}
      </main>

      <ChwDrawer chw={drawerChw} onClose={() => setDrawerChw(null)} />
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
