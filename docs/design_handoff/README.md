# Handoff: Supervisor Workspace — Community Health AI Assistant

## Overview
The Supervisor Workspace is the Phase-4 frontend for the Community Health AI Assistant. It is a single-pane workspace where a community health program supervisor (persona: "Margaret Kimani, Kakamega") generates a Monday-morning briefing, asks follow-up questions in natural language, and inspects the agent's tool plan, sources, and traces.

The interface is built around three contracts the existing Phase-2/Phase-3 backend already provides:

1. `POST /briefing` returns `{ answer, trace_id }` — the agent has already run a ReAct loop over OpenMRS FHIR data and emits a structured response.
2. Each turn has an associated Langfuse trace; the UI surfaces the trace id and links out.
3. The agent's tool plan (from `tool_plan` metadata in Langfuse) can be replayed/streamed to the UI so the user sees what the agent did and how long each step took.

## About the Design Files
The files in this bundle are **design references created in HTML** — a prototype showing intended look and behavior, **not production code to copy directly**. The task is to recreate these designs in the existing `frontend/` Next.js scaffold using the project's planned stack: **Next.js (App Router) + Tailwind + shadcn/ui** as called out in the project README.

The HTML prototype uses inline JSX + a hand-written CSS file because that's the fastest way to express the design; the production implementation should use Next.js components, Tailwind utility classes, and shadcn primitives where they exist (Card, Button, Input, ScrollArea, Badge, Separator, Skeleton, Sheet for the right drawer).

## Fidelity
**High-fidelity.** Final colors, typography, spacing, layout, and interaction states are all defined. Recreate pixel-perfectly, but substitute the project's chosen primitives (e.g. shadcn `<Card>` instead of the bare `.ans` div, shadcn `<Sheet>` instead of the hand-rolled drawer).

## Persona & content rules
- The supervisor is a real human reading this on Monday morning before standup. Information density should be **report-grade**, not chatbot-grade. Numbers earn their place; emoji do not.
- The agent's response is **structured JSON**, not free-text markdown. Each "section" has a `kind` (`stat-row` | `callout` | `ranked` | `panel`) the frontend renders as a typed component. The backend should be updated to emit this shape (see "Backend changes required").
- Every CHW id mentioned in the response is a **clickable chip** that opens a context drawer.
- Every response shows its **sources** (the tool calls that produced it) and a **trace id** linking to Langfuse.

## Screens / Views

### 1. App shell
- **Layout**: 2-column CSS grid, `244px 1fr`. Full viewport height. Sidebar is `overflow-y: auto`; main column is `flex` with topbar (fixed 46px) + scroll body + sticky composer.
- **Background**: page `oklch(0.985 0.004 95)` (warm off-white). Surface (cards, sidebar) `#fff`. Subtle warm-tinted neutrals throughout — never pure cool grays.

### 2. Sidebar (244px)
- **Brand block**: 26×26 dark square mark with mono "CH", title "Field Briefing" (13px/600), subtitle "kakamega · v0.3" (11px mono).
- **Workspace nav**: Monday briefing, Anomalies (badge "2", alert color), CHW roster (badge "30"), Patient lookup, Activity charts. Active item gets a white surface + 1px line ring inset.
- **Observability group**: lowercase mono links to langfuse, grafana, openmrs, prometheus with a small `↗` arrow icon at right.
- **User block** at bottom: 28px circular avatar (teal-tinted), name + role.

### 3. Topbar (46px)
- Left: breadcrumb in mono, e.g. `workspace / Monday briefing`.
- Right cluster: date in mono, then a status pill `● fhir · langfuse · azure` with a green pulsing dot.

### 4. Empty state (the "Hero")
Shown when `turns.length === 0`.
- Eyebrow: pulsing teal dot + `Mon · May 10, 2026 · 07:42 EAT` (mono, uppercase, tracked).
- Headline: serif (Source Serif 4), 44px, weight 400, `letter-spacing: -0.02em`, max-width 18ch. Word "changed" italicized in the teal accent ink.
- Subhead: 15px, ink-2, max-width 56ch.
- CTA row: primary dark pill button "Generate Monday briefing" + ghost button "Surface anomalies only".
- 2×2 suggestion grid: each tile has a mono uppercase category label (`anomaly`, `trend`, `panel`, `scope`) and a 13px question. Hover lifts 1px and adds a soft shadow.

### 5. Conversation turn — user
- Meta line: 18×18 teal-tinted "MK" avatar + `you · 07:42`.
- Question: serif, 22px, with a 2px left border in `--line-2`, padded 16px from the rule.

### 6. Conversation turn — AI
Three stacked elements:

**(a) Tool plan timeline** — the differentiating element.
- Card-shaped, mono 12px.
- Header: `TOOL PLAN` (uppercase, tracked) on the left; right side shows either `● running` (teal pulsing dot) or `completed in 4310ms` (ok color).
- Each row: 4-column grid `18px 1fr auto auto`.
  - Column 1: status bullet — pending = dashed ring, running = teal arc spinner (0.8s linear), done = filled green disc with white check.
  - Column 2: tool name in ink + args in ink-3 (e.g. `team_activity_summary (days=30)`).
  - Column 3: row count (`30 rows`) or `—` when pending.
  - Column 4: ms timing or `—` when pending.
- Rows separated by 1px dashed lines.

**(b) Structured answer card** (`.ans`) — `border-radius: 14px`, 1px line, white surface, 22/24px padding.
- `ans__period`: mono 11px uppercase, e.g. `Apr 11 → May 10 · 30-day lookback`.
- `ans__head`: serif, 22px, `text-wrap: pretty`. The single one-sentence headline of the answer.
- Then 1..N typed sections, separated by 22px:

  - **`stat-row`**: 4-column grid of stat tiles, hairlines via 1px gap on a colored background. Each tile: 11px uppercase label, 28px serif value, mono delta colored by tone (`ok | warn | alert | muted`), 11px sub.
  - **`callout`**: rounded card tinted by tone. 18px circular icon (filled with tone color, white glyph: `!` alert, `?` warn, `✓` ok). Title 13/600 + body 13/ink-2. Optional `evidence` row of mono tag pills naming the tools that produced this conclusion.
  - **`ranked`**: bordered card with a tinted header row (`pip` dot in tone color + title). Each item is a 3-column row: a mono `chw-NNN` chip on the left (clickable → drawer), 13px primary line + 12px ink-3 secondary in the middle, `→` arrow on the right. Whole row hover-tints + click also opens drawer.
  - **`panel`**: striped 3-column data table — left bold name, mid mono demographic, right mono date/count.

- **Trace footer**: dashed 1px top border, mono 11px row.
  - `sources` label, then a row of mono tag pills with each tool call (e.g. `team_activity_summary(30)`).
  - Right-aligned link `trace · {short_id} ↗` in accent ink.

### 7. Right drawer (CHW detail)
- Triggered by clicking any `chw-NNN` chip or any `.ranked__row`.
- 420px wide, slides in from right with cubic-bezier(0.32, 0.72, 0, 1) over 240ms. Backdrop fades to `oklch(0 0 0 / 0.18)`.
- Header: mono id, then 16/600 name. Close button (28×28, line border, `×` glyph).
- Body: stacked key/value rows (sub-county, encounters 30d, encounters 7d, status, FHIR Practitioner uuid).
- Mini chart: surface-2 panel with a 7-day sparkline (teal bars, alert-red for zero days) and Mon..Sun labels.
- Two ghost buttons at bottom: "Open patient panel" / "Call CHW".

### 8. Composer (sticky bottom)
- Pill-rounded surface card with a 1px border, focus state adds 3px teal halo + accent border.
- Auto-growing textarea (max 160px), placeholder `Ask about a CHW, patient, or trend.  Try "why is chw-002 quiet?"`. ⏎ submits, ⇧⏎ newlines.
- 32×32 dark square send button, disabled when empty or while busy.
- Hint row beneath in 10px mono, separated by thin vertical rules: `↵ send · ⇧↵ newline`, `model: gpt-5.5 (azure)`, `lookback: 30d`, `● fhir healthy` (ok color), right-aligned `verify in OpenMRS before action`.

### 9. Activity charts view
- 30-bar daily encounter chart. Weekend bars tinted to `ink` 0.4 opacity. Zero days rendered in alert red. Hover tooltip via title attr in prototype; production should use a real tooltip primitive.

### 10. CHW roster view
- Stacked rows reusing the ranked-row pattern. Each row opens the drawer.

## Interactions & Behavior
- **Submit a question** → push user turn, push AI turn with `planIdx: 0, response: null`. Drive a tick-loop that increments `planIdx` per step. Each step's wall time = `clamp(step.ms * 0.45, 280, 900)` so the timeline feels live without taking 5s. When `planIdx === plan.length`, set `response`, set `doneAt = sum(ms)`, set `busy = false`.
- **Clicking a `chw-NNN` chip** → fetch CHW details, open right drawer.
- **`Cmd/Ctrl+K`** (planned) — focus composer.
- **`G`** (planned) — trigger Monday briefing from empty state.
- **Escape** while drawer is open → close drawer.
- **Streaming (production)** — replace the simulated tick-loop with SSE from a `/briefing/stream` endpoint that emits one event per tool call: `{type: 'tool_start', name, args}` and `{type: 'tool_done', name, ms, rows}`, then a final `{type: 'response', sections, trace_id}`.

## State Management
Single conversation reducer, shape:
```ts
type Turn =
  | { id: string; role: 'user'; q: string }
  | { id: string; role: 'ai'; plan: PlanStep[]; planIdx: number;
      response: AnswerDoc | null; traceId: string; doneAt?: number };

type State = {
  turns: Turn[];
  busy: boolean;
  drawerChw: Chw | null;
  activeNav: 'brief' | 'alert' | 'team' | 'patient' | 'chart';
};
```
React Query (or SWR) for the CHW roster + drawer detail fetches. The conversation can stay in component state until you add persistence.

## Backend changes required
The current `/briefing` returns `{ answer: string, trace_id }`. To support the structured layout, evolve to:

```json
{
  "trace_id": "…",
  "plan": [
    {"tool": "team_activity_summary", "args": "(days=30)", "ms": 1820, "rows": 30}, …
  ],
  "answer": {
    "headline": "…",
    "period": "Apr 11 → May 10 · 30-day lookback",
    "sections": [ {"kind": "stat-row", "stats": [...]}, … ],
    "sources": ["team_activity_summary(30)", …]
  }
}
```

The simplest approach: keep the LLM emitting markdown for now, but add a second prompt step ("structured-answer formatter") that re-renders the markdown into the typed schema above. Or have the LLM emit the JSON directly via tool-calling. Either way, the markdown path stays as a fallback so old clients keep working.

## Design Tokens

### Color (oklch — paste into Tailwind config or CSS variables)
```
--bg:        oklch(0.985 0.004 95);    /* warm off-white page */
--surface:   oklch(1 0 0);
--surface-2: oklch(0.975 0.005 95);    /* sidebar, table stripes, panel headers */
--line:      oklch(0.91 0.006 95);
--line-2:    oklch(0.86 0.008 95);
--ink:       oklch(0.22 0.012 250);    /* primary text */
--ink-2:     oklch(0.42 0.012 250);
--ink-3:     oklch(0.58 0.010 250);    /* mono muted */
--ink-4:     oklch(0.74 0.008 250);    /* hairline labels */
--accent:    oklch(0.46 0.09 195);     /* deep teal — primary action */
--accent-2:  oklch(0.92 0.04 195);
--accent-ink:oklch(0.34 0.09 195);
--ok:        oklch(0.55 0.10 158);     /* green */
--ok-bg:     oklch(0.96 0.04 158);
--warn:      oklch(0.62 0.13 70);      /* amber */
--warn-bg:   oklch(0.96 0.05 70);
--alert:     oklch(0.55 0.16 25);      /* terracotta */
--alert-bg:  oklch(0.96 0.04 25);
```

### Typography
- **Sans (UI/body)**: Inter Tight, 400/500/600/700. Feature settings `"ss01", "cv11"`.
- **Serif (headlines, stat values)**: Source Serif 4, 400/500 + 400 italic for the accented word in the hero.
- **Mono (IDs, traces, timestamps, KPIs deltas)**: JetBrains Mono, 400/500/600.
- Body 14/1.5. Hero h1 44/1.05/-0.02em. Card head 22/1.3/-0.01em. Stat value 28 serif. Labels 11 uppercase tracked 0.05–0.08em.

### Spacing
- Container: `min(940px, calc(100% - 48px))`, centered.
- Card padding: 22/24. Tile padding: 14/16. List row padding: 12/14.
- Section gap: 22px.

### Radius
`--r-sm: 6px` (chips/nav items), `--r-md: 10px` (callouts, panels, plan card), `--r-lg: 14px` (the answer card and composer).

### Shadows
- Suggestion hover: `0 4px 12px oklch(0 0 0 / 0.04)`.
- Composer: `0 6px 18px oklch(0 0 0 / 0.04), 0 1px 2px oklch(0 0 0 / 0.04)`.
- Composer focus halo: `0 0 0 3px oklch(0.46 0.09 195 / 0.12)`.

### Motion
- Spinner: 0.8s linear infinite.
- Pulse dot: 1.6s ease-out infinite, expanding 0–8px shadow ring.
- Drawer: 240ms cubic-bezier(0.32, 0.72, 0, 1).
- Hover lifts: 120–140ms ease.

## Assets
- **Fonts**: Google Fonts (Inter Tight, Source Serif 4, JetBrains Mono).
- **Icons**: hand-rolled inline SVGs in `app.jsx` (`I.brief`, `I.alert`, `I.team`, `I.panel`, `I.chart`, `I.arrow`, `I.send`, `I.ext`, `I.check`, `I.x`, `I.attach`). In production, swap for `lucide-react` equivalents: `FileText`, `AlertTriangle`, `Users`, `Table2`, `BarChart3`, `ArrowRight`, `SendHorizontal`, `ExternalLink`, `Check`, `X`, `Paperclip`.
- **No raster assets**.

## Files in this bundle
- `Supervisor Workspace.html` — the prototype shell (loads React, Babel, fonts, data, app).
- `app.jsx` — full React app: sidebar, hero, conversation turns, plan timeline, structured answer renderer, drawer, composer, charts and roster views.
- `data.js` — the canned dataset: `CHWS`, `VISITS_BY_DAY`, `BRIEFING`, `BRIEFING_PLAN`, and three `FOLLOWUPS` (chw-002 deep dive, chw-009 panel, May-1 zero-day diagnosis). This is the **shape** of the agent response the production backend must emit.
- `styles.css` — the full design system (tokens, layout, every component class).
- `tweaks-panel.jsx` — unused in this version; safe to ignore for the production port.

## Implementation order suggested
1. Port `styles.css` tokens to Tailwind config (`theme.extend.colors`, `fontFamily`, `borderRadius`).
2. Build the typed answer schema in TS and wire the four section renderers (`StatRow`, `Callout`, `Ranked`, `Panel`) as shadcn-flavored components.
3. Rebuild the plan timeline as a small `<PlanTimeline>` with the same status state machine; behind a feature flag, swap the canned tick-loop for SSE from the backend.
4. Drawer = shadcn `<Sheet side="right">`. Composer = `<Card>` + auto-grow `<Textarea>` + shadcn `<Button>`.
5. Empty state, then conversation, then activity charts and roster views (use `recharts` for the bar chart in production).
6. CORS + env: `NEXT_PUBLIC_BACKEND_URL` defaulting to `http://localhost:8000`. Phase-6 Docker compose service `frontend` mapping `3000:3000`.
