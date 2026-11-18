"""Export briefing traces from Langfuse as evidence: raw spans plus a summary.

    python scripts/export_traces.py --since 2026-11-18T05:00:00Z [--until ...]
        [--label eval] [--example <trace id>]

Reads every observation in the window from Langfuse's public API, groups
them into traces, and keeps the briefing traces (those rooted at
agent.run_briefing). Writes, under docs/evidence/:

  <date>-traces-<label>.json  every span: name, type, timings, tokens, cost
  <date>-traces-<label>.md    per-trace latency, model calls, tokens and cost,
                               the averages, and the span tree of one trace

Cost is what Langfuse computed from its own model price table. Needs
LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY in .env.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, median
from typing import Any

import httpx

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "backend"))

from app.core import get_settings  # noqa: E402

ROOT_NAME = "agent.run_briefing"
FIELDS = "core,basic,usage"


def fetch(client: httpx.Client, since: str, until: str) -> list[dict[str, Any]]:
    """Every observation that started in [since, until), across pages."""
    out: list[dict[str, Any]] = []
    params: dict[str, Any] = {
        "fields": FIELDS,
        "fromStartTime": since,
        "toStartTime": until,
        "limit": 100,
    }
    while True:
        resp = client.get("/api/public/v2/observations", params=params)
        if resp.status_code == 429:
            # Langfuse rate-limits the public API; wait as told and retry.
            time.sleep(float(resp.headers.get("retry-after", "10")))
            continue
        resp.raise_for_status()
        body = resp.json()
        out.extend(body["data"])
        cursor = (body.get("meta") or {}).get("cursor")
        if not cursor or not body["data"]:
            return out
        params["cursor"] = cursor


def _seconds(o: dict[str, Any]) -> float:
    start = datetime.fromisoformat(o["startTime"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(
        (o["endTime"] or o["startTime"]).replace("Z", "+00:00")
    )
    return (end - start).total_seconds()


def summarise(spans: list[dict[str, Any]]) -> dict[str, Any]:
    root = next(o for o in spans if o["name"] == ROOT_NAME)
    calls = [o for o in spans if o["type"] == "GENERATION"]
    return {
        "trace_id": root["traceId"],
        "start": root["startTime"],
        "seconds": round(_seconds(root), 1),
        "model_calls": len(calls),
        "tool_calls": sum(o["type"] == "TOOL" for o in spans),
        "input_tokens": sum(o.get("inputUsage") or 0 for o in calls),
        "output_tokens": sum(o.get("outputUsage") or 0 for o in calls),
        "cost_usd": round(sum(o.get("totalCost") or 0 for o in calls), 4),
        "formatter_traced": any(o["name"] == "llm.format" for o in calls),
    }


def tree(spans: list[dict[str, Any]]) -> list[str]:
    """The trace as an indented list, children in start order."""
    children: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
    ids = {o["id"] for o in spans}
    for o in spans:
        parent = o.get("parentObservationId")
        children[parent if parent in ids else None].append(o)
    lines: list[str] = []

    def walk(o: dict[str, Any], depth: int) -> None:
        detail = f"{_seconds(o):.1f}s"
        if o["type"] == "GENERATION":
            detail += (
                f", {o.get('inputUsage') or 0:,} in / {o.get('outputUsage') or 0:,} out"
                f", ${o.get('totalCost') or 0:.4f}"
            )
        lines.append(f"{'  ' * depth}- `{o['name']}` ({o['type'].lower()}, {detail})")
        for c in sorted(children[o["id"]], key=lambda c: c["startTime"]):
            walk(c, depth + 1)

    for top in sorted(children[None], key=lambda c: c["startTime"]):
        walk(top, 0)
    return lines


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--since", required=True, help="ISO time, e.g. 2026-11-18T05:00:00Z")
    p.add_argument(
        "--until", default=datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    p.add_argument("--label", default="briefings")
    p.add_argument("--example", help="Trace id to show as a span tree (default: first)")
    args = p.parse_args()

    s = get_settings()
    client = httpx.Client(
        base_url=s.langfuse_host,
        auth=(s.langfuse_public_key, s.langfuse_secret_key),
        timeout=60,
    )
    by_trace: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for o in fetch(client, args.since, args.until):
        by_trace[o["traceId"]].append(o)
    briefings = {
        tid: spans
        for tid, spans in by_trace.items()
        if any(o["name"] == ROOT_NAME for o in spans)
    }
    if not briefings:
        raise SystemExit("No briefing traces in that window.")
    rows = sorted(
        (summarise(sp) for sp in briefings.values()), key=lambda r: r["start"]
    )

    example = args.example or rows[0]["trace_id"]
    project = by_trace[example][0]["projectId"]
    link = f"{s.langfuse_host}/project/{project}/traces/{example}"

    out = _REPO_ROOT / "docs" / "evidence"
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{datetime.now(tz=UTC):%Y-%m-%d}-traces-{args.label}"
    (out / f"{stem}.json").write_text(
        json.dumps({"traces": rows, "spans": briefings}, indent=2)
    )

    def avg(key: str) -> float:
        return mean(r[key] for r in rows)

    costs = [r["cost_usd"] for r in rows]

    md = [
        f"# Briefing traces — {args.label}",
        "",
        f"Exported from Langfuse on {datetime.now(tz=UTC):%Y-%m-%d}: every briefing "
        f"trace that started between {args.since} and {args.until}. Cost is "
        "Langfuse's, from its own model price table.",
        "",
        f"- Briefings: {len(rows)}",
        f"- Latency: {median(r['seconds'] for r in rows):.1f}s median, "
        f"{max(r['seconds'] for r in rows):.1f}s slowest",
        f"- Per briefing: {avg('model_calls'):.1f} model calls, "
        f"{avg('tool_calls'):.1f} tool calls, {avg('input_tokens'):,.0f} input and "
        f"{avg('output_tokens'):,.0f} output tokens",
        f"- Cost per briefing: ${avg('cost_usd'):.3f} on average "
        f"(${min(costs):.3f}–${max(costs):.3f}); ${sum(costs):.2f} in total",
        "",
        "| Trace | Started (UTC) | Seconds | Model calls | Tool calls "
        "| Tokens in / out | Cost |",
        "|---|---|---|---|---|---|---|",
        *(
            f"| `{r['trace_id'][:8]}` | {r['start'][11:19]} | {r['seconds']} | "
            f"{r['model_calls']} | {r['tool_calls']} | "
            f"{r['input_tokens']:,} / {r['output_tokens']:,} | ${r['cost_usd']:.3f} |"
            for r in rows
        ),
        "",
        f"## One trace, span by span (`{example[:8]}`)",
        "",
        f"Langfuse: {link} (opens without a login only if the trace was made public)",
        "",
        *tree(briefings[example]),
        "",
    ]
    if not all(r["formatter_traced"] for r in rows):
        md.insert(
            4,
            "\nSome traces predate tracing of the answer formatter (`llm.format`), so "
            "their cost leaves out that one call.\n",
        )
    (out / f"{stem}.md").write_text("\n".join(md))
    print(f"{len(rows)} briefing traces written to {out / stem}.md")


if __name__ == "__main__":
    main()
