# RubricAI v2 — CPS LEARN Lab · Northeastern University

AI-powered rubric-based transcript evaluation at institutional scale.

---

## What It Does

RubricAI v2 evaluates student simulation transcripts against a structured rubric using Claude AI. Upload any rubric and any CSV of transcripts — the system scores every participant on every indicator with rationale, actionable feedback, and direct transcript quotes.

---

## Stack

- Frontend: Vanilla JS single-page app (frontend/index.html)
- Backend: FastAPI + Python (backend/main.py, backend/evaluator.py)
- AI: Claude Haiku 4.5 via Anthropic API
- PDFs: ReportLab

---

## Setup

### 1. Clone the repo

git clone https://github.com/tanvisanjeev/rubricai-v2.git
cd rubricai-v2

### 2. Backend setup

cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

Create backend/.env:
ANTHROPIC_API_KEY=your-key-here

Get your API key from console.anthropic.com

### 3. Run the backend

cd backend && source venv/bin/activate && uvicorn main:app --reload --port 8000

### 4. Run the frontend

cd frontend && python3 -m http.server 3001

### 5. Open in browser

http://localhost:3001/index.html

---

## How to Use

### Step 1 - Data Setup (recommended)
Fill in course name, cohort, simulation type, and researcher expectations. This context is sent directly to Claude to improve scoring accuracy.

### Step 2 - Rubric Framework
Upload your rubric file (.md or .txt). The app auto-parses all domains, clusters, and indicators.

Rubric format:
## Domain Name
### Cluster 1: Name
#### Indicator 1: Name
| Level 1 | descriptor |
| Level 2 | descriptor |
| Level 3 | descriptor |
| Level 4 | descriptor |

Use the Session-Indicator Mapping table to assign indicators to sessions. All assigned to all sessions by default.

### Step 3 - Upload and Evaluate
Upload your transcript CSV. Columns are auto-detected — use Edit Mapping to verify or fix assignments. Click Run Evaluation.

Required CSV columns:
- Participant ID (required): participant_id, student_id, id
- Session 1 Transcript (required): transcript_user, user_transcript
- Session 2 Transcript (optional): transcript_client, client_transcript
- Simulation (optional): simulation, sim, course
- Completion Status (optional): completed, status, done
- Batch / Class (optional): batch, group, section

### Step 4 - Review Results
- Class Overview: all participant scores, all indicators, filter by class/batch
- Summary & Charts: cohort KPIs, score distribution, indicator averages, AI summary
- Click any Participant ID to see full evaluation with rationale, feedback, and transcript quotes

### Step 5 - Export
- Spreadsheet Export: full scores CSV from Class Overview
- Formatted Report: per-student PDF with all indicator scores
- Cohort Spreadsheet: cohort summary CSV from Summary & Charts
- Cohort Report: cohort PDF with KPIs, charts, and AI summary

---

## Dynamic Domain System

Domains are auto-detected from your rubric ## headings. Any rubric with any number of domains will automatically show:
- Domain KPI cards on Class Overview
- Domain KPI cards on Summary & Charts tabs
- Domain scores in participant modal
- Domain scores in student PDF reports
- Domain averages in cohort PDF and spreadsheet exports
- All domain scores in AI cohort summary

No hardcoding. Upload any rubric and everything adapts.

---

## Scoring Scale

- 1 Beginning: Minimal or no evidence of the skill
- 2 Developing: Some evidence but below competency threshold
- 3 Applying: Solid, competent performance
- 4 Mastery: Advanced, exemplary performance

Each score includes rationale, actionable feedback, and up to 2 verbatim transcript quotes.

ETHICAL NOTE: AI-generated scores are for research and instructional support only, not final grades. All scores should be reviewed by a qualified instructor before being used in any formal assessment context.

---

## Cost

A typical run with 16 participants and 29 indicators costs approximately $1.00 using Claude Haiku 4.5. Cost breakdown is shown in the backend terminal after each run.

---

## Known Behaviors

- Participants with transcripts under 50 characters are automatically skipped
- Participants with only one session transcript will be scored for that session only
- If Claude returns malformed JSON, the evaluator automatically retries once
- Results are held in memory for the session only — no data is stored persistently

---

## Troubleshooting

Rubric not parsing correctly:
Check that your rubric uses consistent heading levels (## for domains, ### for clusters, #### for indicators containing the word Indicator).

CSV columns not detected:
Click Edit Mapping after uploading and manually assign transcript columns.

N/A scores for some participants:
The transcript for that session is empty or too short. Check your CSV column mapping.

Cohort PDF failing:
Restart the backend and try again. Check the backend terminal for the error.

Different results between machines:
Claude is non-deterministic across API calls even at temperature=0. The retry logic handles most cases. Run the evaluation again if results differ significantly.

---

## Project Structure

rubricai-v2/
├── frontend/
│   └── index.html          # Full SPA — all UI, parsing, rendering
├── backend/
│   ├── main.py             # FastAPI routes, PDF/CSV export
│   ├── evaluator.py        # Claude evaluation engine
│   ├── rubric.md           # Last uploaded rubric (auto-saved)
│   ├── requirements.txt
│   └── .env                # ANTHROPIC_API_KEY (not committed)
├── data/                   # Sample data files
└── README.md

---

## Built By

Tanvi Kadam — Graduate Student, MPS Analytics + Applied Machine Intelligence
Northeastern University · CPS LEARN Lab
Supervised by Harry Son · hy.son@northeastern.edu

RubricAI v2 · April 2026 · Confidential Research Tool
