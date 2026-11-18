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

Because the seven situations were planted, I know what a good briefing should contain, so I can measure whether it does. The evaluation runs the full briefing five times and asks a separate model, given each known finding, whether the briefing conveys it.

Latest run (gpt-5.5 on Azure, five runs):

- **31 of 35** planted findings conveyed. Six of the seven were caught in every run.
- **5 of 5** briefings passed the figure check, checking about 75 figures each.
- About 28 seconds and 8 model calls per briefing.

The first version scored 18 of 21 over three runs. Reading the misses showed the lead analyst dropping lower-priority findings to stay within its bullet limit. One instruction (combine findings rather than drop them) fixed most of it. The remaining miss is consistent: the briefing reports 14 visits with no location but cannot say they happened this week, because that tool reports how many, not when. It is the next fix.

Building the evaluation also exposed bugs the agents could not have shown me. The data loader had been silently discarding most of the planted situations, so an earlier version of the agent could only ever count visits. And OpenMRS reads "before 14 November" as "before the end of 14 November", which double-counted visits in the daily totals.

What these numbers do not show: they measure whether real findings are caught, not false alarms. The judge is the same model as the agents and has not been checked against human ratings. The figure check proves a number came from the data, not that it is attached to the right person. And the data and the planted situations come from the same project as the tools.

## Observability

Every briefing is traced in Langfuse: one span per agent, every model call with its token usage, and every tool call with its inputs and outputs. Evaluation scores are attached to the same trace, so a miss can be followed back to the exact step that caused it. The backend also exports Prometheus metrics for request, tool and model-call latency, shown on a Grafana dashboard, and separates "the service is up" from "OpenMRS and the model are reachable" in its health checks.

## Limitations

- **Synthetic data only.** No real patients, and nothing here has been validated clinically or with real supervisors.
- **Planted findings, not real ones.** The evaluation shows the pipeline catches what it was designed to catch. It says nothing about situations nobody planted.
- **Recall only.** False alarms are not yet measured, and the judge has not been calibrated against people.
- **Not deployed.** OpenMRS alone takes 10–15 minutes to start, so the system runs locally and is shown here as a recording.
- **Supervisor-facing, not clinical.** It tells a supervisor whom to call. It does not diagnose, and every flagged record is meant to be confirmed in OpenMRS first.

## What's next

- Give the location check a date, so the briefing can say the unlocated visits are recent.
- Add a false-alarm measure, and calibrate the judge against a sample I rate by hand.
- Remember the conversation, so follow-up questions build on the briefing.
- Package it to run with one command, then try it with someone who supervises CHWs.
