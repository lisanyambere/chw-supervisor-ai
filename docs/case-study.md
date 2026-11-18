---
title: Community Health AI Assistant
---

A team of AI agents that reads a community health programme's records and writes the supervisor's Monday-morning briefing: which patients need someone today, which health workers have gone quiet, and which records cannot be right. Every figure in the briefing is checked against the data before the supervisor sees it. I built it solo, on synthetic data only, with no real patients. Code: https://github.com/lisanyambere/chw-supervisor-ai

## Problem

In Kenya, community health workers (CHWs) visit households and log each visit, and a supervisor oversees a team of them. In this project the supervisor runs 30 CHWs across 10 wards of Kakamega County, covering about 550 patients and 4,700 visits a month.

On Monday morning that supervisor needs to know three things. Which patients need someone today: a child with danger signs, a pregnant woman who missed her check-up. Which CHWs need a call: someone who stopped working mid-week, or a new starter whose low numbers are not a problem. And which records are wrong.

The answers are in the records system (OpenMRS, which many Kenyan health programmes run), but only as thousands of individual visits. A dashboard can count visits per worker. It cannot notice that eight fever cases in one ward in five days look like an outbreak, or tell a CHW who stopped on Wednesday from one who only joined on Thursday. Doing that by hand takes hours the supervisor does not have.

## What it does

The supervisor asks a question in plain language, or presses one button for the Monday briefing. About 30 seconds later they get a short, ranked briefing. On the demo data it reports:

- a child under five with fast breathing and a 39.1 °C fever, with the CHW to call to confirm the referral;
- three pregnant women overdue for follow-up, one with a blood pressure of 145;
- eight fever cases in Lurambi ward within five days, all diagnosed with malaria;
- one CHW who stopped logging visits after Tuesday, and one whose low total is a short history rather than low effort;
- visits saved with no location, and visits logged for patients whose death was already recorded.

Each line names the patient, CHW or ward, gives the figures, and ends with a next step. While it works, the screen shows which specialists are running and every data query they make. The answer arrives with a note that its figures were checked against the data. Clicking any CHW opens their 30-day activity, and an activity chart shows the team's visits day by day.

## How it works

The data lives in a real OpenMRS 3 server and is read over FHIR, the healthcare data standard. I generated about 550 patients with Synthea, rewrote names and places to be plausible for Kakamega, and added 30 CHWs and a month of visits. Into that data I planted seven situations a supervisor should catch, stored as ordinary clinical records (temperatures, breathing rates, blood pressures, return-visit dates, diagnoses) rather than as labels the agents could look up. The planted situations are also written to a ground-truth file that the evaluation uses.

The briefing is produced by a LangGraph graph of agents:

- **Router.** Reads the question and engages only the specialists it needs. A general briefing needs all three; a question about one CHW's visits needs only one.
- **Three specialists, in parallel.** Each is a tool-calling agent with its own small set of tools (15 in total) that query OpenMRS. *Team activity* looks at visit counts and gaps in working days. *Clinical signals* looks for fever clusters by ward, children with danger signs and overdue follow-ups. *Data quality* looks for visits with no location and visits after a recorded death.
- **Lead analyst.** Merges the specialists' findings into one briefing, most urgent first.
- **Verifier.** Plain code, not a model. It checks that every number and CHW id in the briefing appears in what the tools returned. If anything does not, the briefing goes back to the lead analyst once to be corrected.

The backend is FastAPI and streams each step to a Next.js frontend as it happens. A second model call reformats the briefing into the structured card the supervisor sees, with the plain-text version kept as a fallback. The design keeps the model away from arithmetic: tools return counts, dates and names, and the agents decide what matters. Malformed tool calls are handed back to the model to retry rather than failing the run, and each agent has a turn limit.

## Evaluation

Because the seven situations were planted, I know what a good briefing should contain, so I can measure whether it does. The evaluation runs the full briefing five times. For each planted finding, a separate model call is told the finding and asked whether the briefing conveys it. Another lists every problem the briefing raises and matches each to a planted finding, so anything it flags beyond them can be counted and read.

Latest run (gpt-5.5 on Azure, five runs):

- **35 of 35** planted findings conveyed: all seven in every run.
- **36 of 37** problems raised matched a planted finding. The other was a suggestion to spot-check the busiest CHWs' records, which is a judgement call rather than a wrong figure.
- **5 of 5** briefings passed the figure check, about 80 figures each.
- About 24 seconds, 8 model calls and 7 tool calls per briefing.

It did not start there. The first version scored 18 of 21 over three runs. Reading the misses showed the lead analyst dropping lower-priority findings to stay within its bullet limit; one instruction (combine findings rather than drop them) took it to 31 of 35. The remaining miss was always the same: the briefing reported 14 visits with no location but could not say they were recent, because the tool returned how many, not when. I changed the tool to break them down by week, and named the week in that finding's description instead of "the latest week", which gave 35 of 35.

Building the evaluation also exposed bugs the agents could not have shown me. The data loader had been silently discarding most of the planted situations, so an earlier version of the agent could only ever count visits. And OpenMRS reads "before 14 November" as "before the end of 14 November", which double-counted visits in the daily totals.

What these numbers do not show: five runs over seven planted situations is a small sample, and every planted situation is one the tools were built to find. The judge is the same model as the agents and has not yet been checked against my own ratings; the project includes a rating sheet and a script that reports agreement once I have filled it in. The figure check proves a number came from the data, not that it is attached to the right person.

## Observability

Every briefing is traced in Langfuse: one span per agent, every model call with its token usage, and every tool call with its inputs and outputs. Evaluation scores are attached to the same trace, so a miss can be followed back to the exact step that caused it. The backend also exports Prometheus metrics for request, tool and model-call latency, shown on a Grafana dashboard, and separates "the service is up" from "OpenMRS and the model are reachable" in its health checks.

## Limitations

- **Synthetic data only.** No real patients, and nothing here has been validated clinically or with real supervisors.
- **Planted findings, not real ones.** The evaluation shows the pipeline catches what it was designed to catch. It says nothing about situations nobody planted.
- **A small, friendly evaluation.** Five runs, seven planted situations, and a judge not yet checked against a person.
- **Not deployed.** OpenMRS alone takes 10–15 minutes to start, so the system runs locally and is shown here as a recording.
- **Supervisor-facing, not clinical.** It tells a supervisor whom to call. It does not diagnose, and every flagged record is meant to be confirmed in OpenMRS first.

## What's next

- Rate a sample of briefings myself and report how often the judge agrees.
- Plant situations the tools were not built for, to see what the agents miss.
- Package it to run with one command, then try it with someone who supervises CHWs.
