"""Second-pass LLM formatter that renders a markdown briefing answer into
the typed UI schema described in `frontend/_design_handoff/README.md`.

Why a second pass instead of asking the agent for JSON directly?
----------------------------------------------------------------
The ReAct loop is already optimised for grounded, action-oriented prose; making
it also emit a strict UI schema in the same call costs accuracy and means a
single bad token blocks the whole response. Splitting the concern keeps the
agent loop simple and lets us evolve the UI schema without retraining the
agent prompt. We also keep the markdown around as a fallback so old clients,
the eval runner, and the trace dashboard keep working.

Schema (mirrors `frontend/_design_handoff/data.js` BRIEFING):

    {
      "headline": str,
      "period": str,                       # e.g. "Apr 11 → May 10 · 30-day lookback"
      "sections": [
        {"kind": "stat-row", "stats": [
          {"label": str, "value": str, "delta": str, "deltaTone": "ok|warn|alert|muted", "sub": str}
        ]},
        {"kind": "callout", "tone": "ok|warn|alert", "title": str, "body": str,
         "evidence": [tool_name, ...]},
        {"kind": "ranked", "title": str, "tone": "ok|warn|alert",
         "items": [{"id": "chw-NNN", "primary": str, "secondary": str}]},
        {"kind": "panel", "title": str,
         "rows": [{"left": str, "mid": str, "right": str}]}
      ],
      "sources": ["tool_name(arg=val)", ...]
    }
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.core import get_logger
from app.llm import LLM, get_llm

if TYPE_CHECKING:
    from app.agents.briefing import BriefingResult, PlanStep

log = get_logger(__name__)


# ─── prompt ────────────────────────────────────────────────────────────────

_FORMATTER_SYSTEM = """You are a strict JSON formatter for a community-health
supervisor dashboard. You will be given:
  • the supervisor's question,
  • a compact summary of the tool calls the agent made,
  • the agent's free-text markdown answer.

Your job is to re-render the answer into the typed UI schema below. You must
NOT invent new facts — every number, name, and CHW id you emit must already
appear in the markdown answer or the tool summary. Drop anything you cannot
ground.

Reply with ONE JSON object, exactly matching this shape:

{
  "headline": "<one short sentence summarising the answer>",
  "period": "<e.g. 'Apr 11 → May 10 · 30-day lookback', or '' if not applicable>",
  "sections": [
    /* zero or more of: */
    {"kind": "stat-row", "stats": [
      {"label": "<11-char uppercase label>", "value": "<short number/text>",
       "delta": "<short delta phrase>", "deltaTone": "ok|warn|alert|muted",
       "sub": "<one-line context>"}
    ]},
    {"kind": "callout", "tone": "ok|warn|alert",
     "title": "<short title>", "body": "<1-2 sentences>",
     "evidence": ["<tool_name>", "..."]},
    {"kind": "ranked", "title": "<title>", "tone": "ok|warn|alert",
     "items": [{"id": "chw-NNN", "primary": "<one line>",
                "secondary": "<one line of context>"}]},
    {"kind": "panel", "title": "<title>",
     "rows": [{"left": "<name>", "mid": "<demographic>", "right": "<date/count>"}]}
  ],
  "sources": ["tool_name(args)", "..."]
}

Rules:
- 1–4 sections total. Pick the kinds that fit; do not pad with empty ones.
- Use `stat-row` only when you can fill 2–4 stats. Otherwise use `callout`.
- Use `ranked` for any list of CHWs. The id MUST be a literal "chw-NNN".
- Use `panel` for patient lists.
- `tone` and `deltaTone` are conservative: "alert" only for things requiring
  same-day supervisor action, "warn" for trending issues, "ok" for positive,
  "muted" for neutral context.
- `sources` echoes the tool calls from the trace summary.
- If the answer is a one-liner ("There are 30 CHWs"), emit a single stat-row
  with one stat and no other sections.
"""


# ─── helpers ────────────────────────────────────────────────────────────────


def _summarise_plan(plan: list["PlanStep"]) -> str:
    if not plan:
        return "(no tools called)"
    return "\n".join(f"  - {s.tool}{s.args}  →  {s.rows} rows, {s.ms}ms" for s in plan)


def _safe_parse(raw: str) -> dict[str, Any] | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return data


_VALID_SECTION_KINDS = {"stat-row", "callout", "ranked", "panel"}
_VALID_TONES = {"ok", "warn", "alert", "muted"}


def _coerce_str(v: Any, *, default: str = "") -> str:
    if v is None:
        return default
    if isinstance(v, str):
        return v
    return str(v)


def _normalise_section(section: Any) -> dict[str, Any] | None:
    """Validate and clean a single section. Drops anything malformed."""
    if not isinstance(section, dict):
        return None
    kind = section.get("kind")
    if kind not in _VALID_SECTION_KINDS:
        return None

    if kind == "stat-row":
        stats_raw = section.get("stats") or []
        if not isinstance(stats_raw, list) or not stats_raw:
            return None
        stats: list[dict[str, str]] = []
        for s in stats_raw:
            if not isinstance(s, dict):
                continue
            tone = _coerce_str(s.get("deltaTone"), default="muted")
            if tone not in _VALID_TONES:
                tone = "muted"
            stats.append({
                "label": _coerce_str(s.get("label")),
                "value": _coerce_str(s.get("value")),
                "delta": _coerce_str(s.get("delta")),
                "deltaTone": tone,
                "sub": _coerce_str(s.get("sub")),
            })
        return {"kind": "stat-row", "stats": stats[:4]}  # design caps at 4

    if kind == "callout":
        tone = _coerce_str(section.get("tone"), default="ok")
        if tone not in {"ok", "warn", "alert"}:
            tone = "ok"
        evidence_raw = section.get("evidence") or []
        evidence = [
            _coerce_str(e) for e in evidence_raw
            if isinstance(e, (str, int, float))
        ]
        return {
            "kind": "callout",
            "tone": tone,
            "title": _coerce_str(section.get("title")),
            "body": _coerce_str(section.get("body")),
            "evidence": evidence,
        }

    if kind == "ranked":
        tone = _coerce_str(section.get("tone"), default="ok")
        if tone not in {"ok", "warn", "alert"}:
            tone = "ok"
        items_raw = section.get("items") or []
        items: list[dict[str, str]] = []
        for it in items_raw:
            if not isinstance(it, dict):
                continue
            cid = _coerce_str(it.get("id"))
            if not cid:
                continue
            items.append({
                "id": cid,
                "primary": _coerce_str(it.get("primary")),
                "secondary": _coerce_str(it.get("secondary")),
            })
        if not items:
            return None
        return {
            "kind": "ranked",
            "title": _coerce_str(section.get("title")),
            "tone": tone,
            "items": items,
        }

    if kind == "panel":
        rows_raw = section.get("rows") or []
        rows: list[dict[str, str]] = []
        for r in rows_raw:
            if not isinstance(r, dict):
                continue
            rows.append({
                "left": _coerce_str(r.get("left")),
                "mid": _coerce_str(r.get("mid")),
                "right": _coerce_str(r.get("right")),
            })
        if not rows:
            return None
        return {
            "kind": "panel",
            "title": _coerce_str(section.get("title")),
            "rows": rows,
        }
    return None


@dataclass
class AnswerDoc:
    headline: str
    period: str
    sections: list[dict[str, Any]]
    sources: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "headline": self.headline,
            "period": self.period,
            "sections": self.sections,
            "sources": list(self.sources),
        }


# ─── public API ────────────────────────────────────────────────────────────


def _default_sources(plan: list["PlanStep"]) -> list[str]:
    """Build the `sources` list from the executed plan."""
    return [f"{s.tool}{s.args}" for s in plan]


def _fallback_doc(result: "BriefingResult") -> AnswerDoc:
    """When the formatter fails, surface the markdown as a single callout so
    the UI still has something to render."""
    return AnswerDoc(
        headline=(result.answer or "(no answer)").splitlines()[0][:200],
        period="",
        sections=[
            {
                "kind": "callout",
                "tone": "warn",
                "title": "Unstructured answer",
                "body": (result.answer or "")[:1200],
                "evidence": [s.tool for s in result.plan],
            }
        ],
        sources=_default_sources(result.plan),
    )


async def format_answer(
    result: "BriefingResult",
    question: str,
    *,
    llm: LLM | None = None,
) -> AnswerDoc:
    """Re-render the markdown briefing into the typed UI schema.

    Falls back to a single-callout doc if the LLM call or JSON parsing fails;
    callers should always be able to render the result.
    """
    llm = llm or get_llm()
    user = (
        f"QUESTION:\n{question}\n\n"
        f"TOOL CALLS:\n{_summarise_plan(result.plan)}\n\n"
        f"MARKDOWN ANSWER:\n{result.answer}\n"
    )
    try:
        completion = await llm.chat(
            messages=[
                {"role": "system", "content": _FORMATTER_SYSTEM},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
        )
        raw = completion.choices[0].message.content or ""
    except Exception as e:  # noqa: BLE001
        log.warning("formatter.llm_failed", error=str(e))
        return _fallback_doc(result)

    data = _safe_parse(raw)
    if not data:
        log.warning("formatter.parse_failed", raw=raw[:200])
        return _fallback_doc(result)

    sections_raw = data.get("sections") or []
    if not isinstance(sections_raw, list):
        sections_raw = []
    sections = [s for s in (_normalise_section(x) for x in sections_raw) if s]

    sources_raw = data.get("sources") or []
    if not isinstance(sources_raw, list):
        sources_raw = []
    sources = [_coerce_str(s) for s in sources_raw if isinstance(s, (str, int, float))]
    if not sources:
        sources = _default_sources(result.plan)

    if not sections:
        # The model returned valid JSON but nothing renderable — fall back
        # so the UI never shows an empty card.
        return _fallback_doc(result)

    return AnswerDoc(
        headline=_coerce_str(data.get("headline"))
                 or (result.answer or "(no headline)").splitlines()[0][:200],
        period=_coerce_str(data.get("period")),
        sections=sections,
        sources=sources,
    )


__all__ = ["AnswerDoc", "format_answer"]
