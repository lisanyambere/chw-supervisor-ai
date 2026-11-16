# Handover: getting this project portfolio-ready

Context for a new working session. The project appears on Elizabeth's portfolio
(https://www.elizabethnyambere.com, repo `../personal-portfolio`) as
"Community Health AI Assistant". The goal of this round of work is to finish
the project enough to show it well, and to produce the material the portfolio
needs.

## How it will be shown on the portfolio

The full stack (OpenMRS 3, Postgres, Redis, Prometheus, Grafana) is too heavy
to keep running publicly: OpenMRS alone takes 10-15 minutes on first boot. So
the portfolio will not embed a live instance. Instead it gets a case-study
page at `/work/community-health` built from:

1. **A short demo video (60-90 s).** A supervisor asks for the Monday briefing,
   the plan timeline ticks live, the answer arrives with flagged households and
   citations, then a click into a CHW. End on the Langfuse trace or Grafana.
2. **4-5 screenshots:** the briefing answer, the CHW detail drawer, the
   activity chart, a Langfuse trace, the Grafana dashboard.
3. **Evaluation numbers** from the golden-question runner and judges, stated
   with the dataset size and what they do and do not measure.
4. **An architecture diagram:** OpenMRS/FHIR → tools → LangGraph agent →
   evaluators → FastAPI SSE → Next.js, with Langfuse and Prometheus alongside.
5. **The story:** who the supervisor is, what their Monday looks like without
   this, what changes with it, and what it does not do (synthetic data only, no
   real patients; limitations).
6. Optional, later: a **replay mode**, recorded briefing streams served as
   static files so visitors can click through a real run without a backend.

The written case study also goes into the portfolio's content library as
`content/projects/community-health.md` (one `## ` heading per section) so the
site's assistant can answer questions about it.

## Work in this repo, in order

From `TODO.md` "Next up", chosen for what the case study needs:

1. Fix the encounter idempotency bug in `data/load_to_openmrs.py` (a re-run
   doubles encounter rows) and reset the data, so recordings are clean.
2. CHW detail drawer (Phase 4).
3. Activity charts view (Phase 4).
4. Run the evaluator suite and save a dated report with the numbers.
5. Mobile pass on the frontend, enough for screenshots at phone width.
6. Record the video and screenshots.
7. Draft the case-study text (sections: Problem, What it does, How it works,
   Evaluation, Observability, Limitations, What's next).

Deployment (Phase 6) is not needed for the portfolio and can wait.

## Working rules

- Follow `~/Documents/Prescott/AGENTS.md`: small verified commits,
  Conventional Commits, prefixed branches, stage explicit files, no
  co-author or tool attribution in commit messages. Push and open PRs only
  when Elizabeth says so.
- Synthetic data only. Never print or commit API keys.
