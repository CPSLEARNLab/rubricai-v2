# RubricAI v2

AI-powered rubric-based transcript evaluation for academic simulation assessments.
Built at the CPS LEARN Lab · Northeastern University

---

## Overview

RubricAI v2 evaluates student simulation transcripts against a structured rubric using Claude AI. Researchers and instructors upload a rubric and a CSV of transcripts — the system scores every participant on every indicator and returns evidence-based scores, rationale, actionable feedback, and direct transcript quotes.

The tool is designed for institutional-scale evaluation with full researcher control over which rubric, which indicators, and which sessions are assessed.

---

## Tech Stack

- Frontend: Vanilla JS single-page app (frontend/index.html)
- Backend: FastAPI + Python (backend/main.py, backend/evaluator.py)
- AI Engine: Claude Haiku 4.5 via Anthropic API
- PDF Export: ReportLab

---

## Getting Started

Prerequisites
- Python 3.10+
- An Anthropic API key from console.anthropic.com

1. Clone the repository
git clone https://github.com/tanvisanjeev/rubricai-v2.git
cd rubricai-v2

2. Set up the backend
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

3. Create backend/.env
ANTHROPIC_API_KEY=your-key-here

4. Start the backend
cd backend && source venv/bin/activate && uvicorn main:app --reload --port 8000

5. Start the frontend
cd frontend && python3 -m http.server 3001

6. Open in browser
http://localhost:3001/index.html

---

## How to Use

Step 1 - Data Setup (recommended)
Go to Data Setup and fill in course name, cohort, simulation type, and researcher expectations.
This context is passed directly to the AI to improve scoring accuracy and relevance.

Step 2 - Rubric Framework
Upload your rubric file (.md or .txt).
The app automatically parses all domains, clusters, and indicators.

Expected rubric structure:
## Domain Name
### Cluster Name
#### Indicator 1: Name
| Level 1 | descriptor |
| Level 2 | descriptor |
| Level 3 | descriptor |
| Level 4 | descriptor |

The Session-Indicator Mapping table appears below the rubric, organised by Domain > Cluster > Indicator.
By default all indicators are assigned to all sessions.
Instructors can freely reassign any indicator to any session or deselect indicators they do not want evaluated.

Step 3 - Upload and Evaluate
Upload your transcript CSV. Column names are auto-detected.
Use Edit Mapping to verify or correct column assignments before running.
Click Run Evaluation — results stream in live as each participant is scored.

Supported CSV columns:
- Participant ID (required): participant_id, student_id, id
- Session 1 Transcript (required): transcript_user, user_transcript
- Session 2 Transcript (optional): transcript_client, client_transcript
- Simulation Name (optional): simulation, sim, course
- Completion Status (optional): completed, status, done
- Batch / Class (optional): batch, group, section

Step 4 - Review Results
- Class Overview: all participant scores across all indicators, filterable by batch or class
- Participant Modal: click any participant ID to see full evaluation with all domain scores, rationale, feedback, and transcript quotes
- Summary & Charts: cohort-level KPIs by domain, score distribution, indicator averages, AI cohort summary

Step 5 - Export
- Spreadsheet Export (Class Overview): full indicator scores per participant
- Formatted Report (Class Overview): per-student PDF with all scores and evidence
- Cohort Spreadsheet (Summary & Charts): cohort summary with all domain averages
- Cohort Report (Summary & Charts): cohort PDF with KPIs, charts, and AI summary

---

## Dynamic Domain System

Domains are auto-detected from ## headings in your rubric.
Any rubric with any number of domains will automatically populate:
- Domain KPI cards on Class Overview
- Domain KPI cards on all Summary & Charts tabs
- Domain scores in the participant modal
- Domain scores in student PDF reports
- Domain averages in cohort PDF and spreadsheet exports
- Domain scores in the AI cohort summary

No hardcoding. Upload any rubric and everything adapts.

---

## Session-Indicator Mapping

The Rubric Framework page shows a full mapping table organised by Domain > Cluster > Indicators.
Instructors can:
- Assign any indicator to any session (User Interview, Client Conversation, or both)
- Deselect indicators they do not want evaluated in this run
- Use All, None, or Reset buttons for bulk actions
Only selected indicators appear in evaluation results and reports.

---

## Scoring Scale

1 - Beginning: Minimal or no evidence of the skill
2 - Developing: Some evidence but below competency threshold
3 - Applying: Solid, competent performance
4 - Mastery: Advanced, exemplary performance

Each indicator score includes:
- Rationale citing specific rubric criteria and transcript evidence
- Actionable improvement feedback
- Up to 2 verbatim transcript quotes

---

## Ethical Use

AI-generated scores are intended for research and instructional support only, not as final grades.
All scores should be reviewed by a qualified instructor before being used in any formal assessment context.
The tool surfaces evidence and patterns to support human judgment, not replace it.

---

## Known Behaviours

- Participants with transcripts under 50 characters are automatically skipped
- If a participant only completed one session, that session is scored and the other shows N/A
- If Claude returns malformed JSON, the evaluator automatically retries once
- Results are held in memory for the duration of the session — no participant data is stored persistently
- Claude is non-deterministic across API calls even at temperature=0

---

## Troubleshooting

Rubric not parsing correctly:
Ensure your rubric uses ## for domain names, ### for cluster names, and #### for indicator headings.
Indicator headings must contain the word "Indicator".

CSV columns not detected:
Click Edit Mapping after uploading your CSV and manually assign each column.

N/A scores for some participants:
The transcript for that session is empty or under 50 characters. Check your column mapping.

Cohort PDF not downloading:
Restart the backend and try again. Check the backend terminal for the specific error.

Different results between machines:
Claude is non-deterministic across API calls even at temperature=0.
The retry logic handles most cases. Re-running the evaluation typically resolves the discrepancy.

A domain not showing in KPI cards:
Ensure the domain uses a ## heading in the rubric. Re-upload the rubric after fixing the structure.

---

## Project Structure

rubricai-v2/
├── frontend/
│   └── index.html          # Complete SPA — UI, rubric parsing, rendering, exports
├── backend/
│   ├── main.py             # FastAPI routes, PDF and CSV export
│   ├── evaluator.py        # Claude evaluation engine with retry logic
│   ├── rubric.md           # Last uploaded rubric (auto-saved by backend)
│   ├── requirements.txt
│   └── .env                # API key — not committed to version control
├── data/                   # Sample rubric and CSV files
└── README.md

---

## Changelog — v2 (April 2026)

- Dynamic domain system: all domains from rubric appear everywhere automatically
- Participant modal shows all domain scores for both sessions
- Incomplete students show which session was scored
- AI cohort summary includes all domain scores
- Cohort PDF and spreadsheet use fully dynamic domain averages
- Summary & Charts tabs show domain KPIs for each session
- Retry logic added to evaluator for malformed JSON responses
- Ethical AI disclaimer added to evaluation flow and PDF exports
- Session-Indicator Mapping redesigned with Domain > Cluster > Indicator hierarchy
- README updated with full setup and troubleshooting guide

---

RubricAI v2 · CPS LEARN Lab · Northeastern University · Confidential Research Tool
