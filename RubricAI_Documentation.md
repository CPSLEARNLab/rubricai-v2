# RubricAI v2
## Product Documentation for Lab Directors and Researchers
### CPS LEARN Lab · Northeastern University

---

## Overview

RubricAI is an AI-powered evaluation platform built to assess student performance at scale using structured rubrics applied to unstructured transcript data. It replaces manual rubric scoring by processing student interview transcripts through a large language model pipeline and returning scored, evidence-grounded outputs for every participant — within minutes, not days.

The platform supports two simultaneous evaluation sessions per student (for example, a User Interview session and a Client Conversation session), produces indicator-level scores, generates written rationale with transcript citations, flags at-risk participants, and outputs cohort-level analytics with visual charts and exportable reports.

---

## The Problem RubricAI Solves

Rubric-based assessment of qualitative data — transcripts, interviews, simulations — is labor-intensive, difficult to standardize, and nearly impossible to scale. A single researcher reviewing 300 student transcripts across 10 rubric indicators, for two sessions per student, represents thousands of individual scoring decisions. That process introduces inter-rater variability, consumes researcher time that could be directed toward analysis, and creates a bottleneck between data collection and insight.

RubricAI eliminates that bottleneck.

---

## Core Capabilities

### 1. Transcript-Based Rubric Evaluation

RubricAI takes unstructured transcript data (CSV or Excel format) and scores each participant against a researcher-defined rubric. The rubric is uploaded as a structured markdown file organized by competency clusters and indicators. The system extracts only the relevant rubric sections for each evaluation call, reducing token overhead and ensuring the model reasons against precise criteria rather than the entire rubric.

Each participant receives:

- A numeric score per indicator (1 = Beginning, 2 = Developing, 3 = Applying, 4 = Mastery)
- A 2-3 sentence rationale citing specific rubric criteria and specific transcript evidence
- Actionable feedback for reaching the next performance level
- Up to two verbatim quotes from the transcript supporting the score
- A narrative summary of overall performance patterns for that session

### 2. Multi-Session Evaluation

The platform supports multiple simultaneous simulation types per participant. Researchers configure sessions in the Data Setup interface (for example, Session 1: User Interview, Session 2: Client Conversation). Each session has its own independent indicator assignments. Both sessions are evaluated in parallel for every participant, and the results are unified into a single participant record.

Session labels, indicator assignments, and rubric sections are fully configurable — nothing is hardcoded to a specific use case.

### 3. Parallel Processing at Scale

Evaluations run in parallel using an asyncio-based concurrency model with a configurable semaphore (default: 10 concurrent participants, each with 2 sessions running simultaneously, yielding up to 20 concurrent API calls). Error handling is built in at every layer: if an individual participant evaluation fails, the system records a null result and continues without blocking the rest of the cohort.

Observed throughput: 300 students evaluated across two sessions in approximately 15 minutes.

### 4. Indicator Configuration and Session Assignment

Researchers select indicators from the uploaded rubric and assign each indicator to one or more sessions using a checkbox interface. The session names displayed in the interface are drawn directly from the researcher's Data Setup configuration. This means the same platform can be reused across different program contexts, courses, and simulation types without any code changes.

### 5. Column Auto-Detection

Data files do not need to conform to a fixed schema. RubricAI scans the uploaded file, detects column names using pattern matching, and suggests a field mapping (participant ID, simulation, transcript fields, completion status, batch/class) for researcher review before the evaluation runs. This accommodates the real-world variability in how research datasets are structured and named.

### 6. Class and Cohort Filtering

Results are segmented by batch (class section, cohort group, or any categorical grouping present in the data). Researchers can filter all analytics to a specific class at any time using filter chips on both the Class Overview and Summary pages. Each class filter operates independently per page.

### 7. Analytics and Visualization

The Summary page presents:

- Cohort KPI cards: total participants, completion rate, average communication score, average critical thinking score per session
- Score distribution bar chart: color-coded bars for each performance level (Beginning through Mastery) with counts and percentages
- Completion status donut chart: proportion of participants who completed both sessions
- Indicator averages horizontal bar chart: per-indicator mean scores color-coded by performance quartile
- AI-generated cohort narrative: a 3-4 sentence analytical summary generated from the cohort's aggregated scores, optionally scoped to a specific class

All charts respond to the active class filter. Generating a summary for Class B, for example, uses only the data from that class.

### 8. Export Options

Three export formats are available:

**Individual Student PDF:** Per-participant report including scores for all indicators across both sessions, written rationale, direct transcript quotes, and session-level narrative. Suitable for student feedback or portfolio documentation.

**Cohort CSV:** Flat file containing all participant scores, session scores, indicator-level scores, and metadata fields. Ready for downstream statistical analysis in R, Python, SPSS, or any spreadsheet tool.

**Cohort PDF Report:** A formatted institutional report including the KPI table, completion donut chart, score distribution bar chart, indicator averages bar chart, and the AI-generated cohort narrative. Scoped to the active class filter when a class is selected.

### 9. AI Cohort Chat

A conversational interface allows researchers to query the cohort data in natural language. Example queries:

- "Which participants need the most support based on their scores?"
- "What is the cohort average across all indicators?"
- "Compare User Interview vs Client Conversation scores."
- "Which participants scored at Beginning level on two or more indicators?"

The chat interface has access to the full evaluated dataset and responds in plain text without markdown formatting.

---

## Evaluation Methodology

### Rubric Structure

The rubric is organized into competency clusters (for example, Communication, Critical Thinking) and individual indicators within each cluster. Each indicator has level descriptors for levels 1 through 4. The system extracts only the sections relevant to the indicators being evaluated, so the model reasons against precise, scoped criteria.

### Scoring Logic

Scoring is performed by a large language model (Anthropic Claude Haiku 4.5) operating at temperature 0 for deterministic outputs. The model is instructed to score strictly against rubric level descriptors rather than general impression, and to cite specific evidence from the transcript in every rationale.

Aggregate communication and critical thinking scores are computed server-side from the returned indicator scores using a cluster-based heuristic: indicators in competency clusters 1 and 2 are treated as communication indicators, and indicators in clusters 3 and above are treated as critical thinking indicators. This avoids asking the model to compute averages, which introduces inconsistency.

### Flagging

Participants are automatically flagged if they score at Level 1 (Beginning) on two or more indicators in a session, or if their session average falls below 2.0. Flags are surfaced in the Class Overview table for immediate researcher attention.

### Evidence Grounding

Every score is accompanied by a rationale that cites both the rubric criterion and the specific transcript passage supporting the score, as well as verbatim quotes from the transcript. This creates an auditable scoring record that can be reviewed, disputed, or used for qualitative analysis alongside the quantitative scores.

---

## Technical Architecture

| Component | Technology |
|-----------|------------|
| Backend | Python, FastAPI |
| Frontend | Single-page HTML/CSS/JavaScript |
| LLM | Anthropic Claude Haiku 4.5 (claude-haiku-4-5-20251001) |
| Parallelism | asyncio, ThreadPoolExecutor, asyncio.Semaphore |
| File Formats | CSV, XLSX, XLS |
| PDF Generation | ReportLab |
| Deployment (planned) | Vercel (frontend), Railway (backend) |

### API Endpoints

| Endpoint | Purpose |
|----------|---------|
| POST /api/detect-columns | Auto-map uploaded file columns to internal schema |
| POST /api/evaluate-stream | Stream evaluation results in real time as each participant completes |
| POST /api/evaluate | Non-streaming batch evaluation |
| POST /api/export/csv | Export scored results as CSV |
| POST /api/export/pdf | Generate individual student PDF report |
| POST /api/export/cohort-pdf | Generate cohort PDF report with visual charts |
| POST /api/chat | Natural language query against cohort data |

---

## Cost and Performance

RubricAI uses the Anthropic API, billed per token. Based on observed runs:

| Cohort Size | Approximate Runtime | Estimated API Cost |
|-------------|--------------------|--------------------|
| 100 students | 5-6 minutes | $1.50 - $2.00 |
| 300 students | 14-16 minutes | $4.00 - $6.00 |

These estimates assume two sessions per participant and 7-10 indicators per session. Cost scales with the number of indicators selected and the length of transcripts.

Token usage is tracked per run. After each evaluation completes, the system logs the total input tokens, output tokens, API call count, and estimated cost to the server console.

---

## Data and Privacy Considerations

- All transcript data remains within the research team's infrastructure. No transcript data is stored by Anthropic beyond the scope of a single API call.
- The platform does not persist evaluation results to a database. Results live in the browser session and are exported at the researcher's discretion.
- Uploaded files are processed in memory and not written to disk (except the rubric file, which is saved locally for reuse across sessions).
- The platform is designed for research use and should be operated in compliance with the institution's IRB protocols governing transcript data.

---

## Intended Users

| User Type | How They Use RubricAI |
|-----------|----------------------|
| Lab Directors | Review cohort-level analytics, download institutional reports, compare class sections |
| Researchers | Configure rubrics and indicators, interpret per-student outputs, export data for statistical analysis |
| Educators / Instructors | Review flagged participants, access individual student feedback, track cohort progress |
| Data Analysts | Use CSV exports for downstream analysis in R, Python, or SPSS |

---

## Current Status and Roadmap

RubricAI v2 is in active development and testing. A full evaluation of 300 students across two simulation types and multiple rubric indicators has been completed successfully. Deployment to a hosted environment (Vercel and Railway) is planned within the next two weeks, at which point the tool will be accessible to the full lab team via a web URL without any local setup.

Planned enhancements include:

- Role-based access and authentication
- Persistent result storage across sessions
- Multi-rubric support within a single evaluation run
- Longitudinal tracking across cohort timepoints
- Configurable scoring scales beyond the 1-4 rubric structure

---

## Contact

Tanvi Sanjeev Kadam
Research AI Engineer, CPS LEARN Lab
Northeastern University
kadam.ta@northeastern.edu
