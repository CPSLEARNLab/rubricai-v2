# RubricAI v2

AI-powered rubric-based transcript evaluation for academic simulation assessments.  
Built at the **CPS LEARN Lab · Northeastern University**

**Live:** https://rubricai-v2.vercel.app/

---

## What It Does

RubricAI evaluates student simulation transcripts against a researcher-defined rubric using Claude AI. Upload a rubric and a CSV of transcripts — the system scores every participant on every indicator and returns:

- **Score (1–4)** per indicator, per session
- **Rationale** citing specific rubric criteria and transcript evidence
- **Actionable feedback** for improvement
- **Verbatim transcript quotes** as evidence
- **Domain-level averages** (Communication, Critical Thinking, Professional Agency, or any domains in your rubric)
- **Cohort analytics** — KPI cards, indicator bar charts, score distribution, participant rankings
- **Exports** — per-student and full-cohort CSV and PDF reports

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Vanilla JS SPA (`frontend/index.html`) |
| Backend | FastAPI + Python (`backend/main.py`, `evaluator.py`) |
| AI Engine | Claude Haiku 4.5 (Anthropic API) |
| PDF Export | ReportLab |
| Deployment | Render (backend) + Vercel (frontend) |

---

## Local Setup

**Prerequisites:** Python 3.11+, Anthropic API key

```bash
# 1. Clone
git clone https://github.com/tanvisanjeev/rubricai-v2.git
cd rubricai-v2

# 2. Backend
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Create .env
echo "ANTHROPIC_API_KEY=your-key-here" > .env

# 4. Run backend
uvicorn main:app --reload --port 8000

# 5. Run frontend (new terminal)
cd frontend && python3 -m http.server 3001

# 6. Open
open http://localhost:3001/index.html
```

---

## How to Use

### Step 1 — Data Setup *(recommended)*
Set course name, cohort, simulation type, and researcher expectations. This context is passed directly to the AI for every evaluation call — more detail = more accurate scores.

### Step 2 — Rubric Framework
Upload your rubric (`.md` or `.txt`). The parser auto-detects all domains, clusters, indicators, and 4-level descriptors.

**Expected structure:**
```markdown
## Domain Name
### Cluster Name
#### Indicator 1: Name
| Level 1 | descriptor |
| Level 2 | descriptor |
| Level 3 | descriptor |
| Level 4 | descriptor |
```

The **Session–Indicator Mapping** table at the bottom lets you assign indicators to specific sessions (User Interview, Client Conversation, or both). All indicators are assigned to all sessions by default.

### Step 3 — Upload & Evaluate
Upload a transcript CSV (or `.xlsx`). Columns are auto-detected. Click **Edit Mapping** to verify before running. Click **Run Evaluation** — results stream in live.

**CSV columns:**

| Column | Required | Example names |
|---|---|---|
| Participant ID | ✅ Required | `participant_id`, `student_id`, `id` |
| Session 1 Transcript | ✅ Required | `transcript_user`, `user_transcript` |
| Session 2 Transcript | Optional | `transcript_client`, `client_transcript` |
| Simulation Name | Optional | `simulation`, `sim`, `course` |
| Completion Status | Optional | `completed`, `status`, `done` |
| Batch / Class | Optional | `batch`, `group`, `section` |

### Step 4 — Review Results
- **Class Overview** — all participant scores, filterable by batch/class
- **Participant modal** — click any ID for full evaluation with rationale, feedback, and quotes
- **Analytics** — cohort KPIs, indicator bar charts, score distribution, AI cohort summary

### Step 5 — Export
| Export | Where |
|---|---|
| Participant CSV | Class Overview → each row |
| Participant PDF | Class Overview → each row |
| Cohort Spreadsheet | Analytics → top-right |
| Cohort Report PDF | Analytics → top-right |

---

## Scoring Scale

| Score | Level | Description |
|---|---|---|
| 1 | Beginning | Minimal or no evidence of the skill |
| 2 | Developing | Some evidence but below competency threshold |
| 3 | Applying | Solid, competent performance |
| 4 | Mastery | Advanced, exemplary performance |

---

## Dynamic Domain System

Domains are auto-detected from `##` headings in your rubric. Any rubric with any number of domains will automatically populate domain KPI cards, domain scores in participant modals, domain averages in exports, and domain breakdowns in the AI cohort summary. No hardcoding required.

---

## Project Structure

```
rubricai-v2/
├── frontend/
│   └── index.html          # Complete SPA — UI, rubric parsing, rendering, exports
├── backend/
│   ├── main.py             # FastAPI routes, PDF and CSV export endpoints
│   ├── evaluator.py        # Claude evaluation engine with retry logic
│   ├── requirements.txt
│   └── .env                # API key — not committed
├── data/                   # Sample rubric and CSV files
├── render.yaml             # Render backend deployment config
├── vercel.json             # Vercel frontend deployment config
└── README.md
```

---

## Known Behaviours

- Participants with transcripts under 50 characters are skipped (score = N/A)
- If a participant only completed one session, only that session is scored
- If Claude returns malformed JSON, the evaluator retries once automatically
- No participant data is stored persistently — results live in session memory only
- `temperature=0` is set for determinism, though minor variation across API calls is possible

---

## Troubleshooting

**Rubric not parsing correctly**  
→ Ensure `##` = domain, `###` = cluster, `####` = indicator (must include the word "Indicator")

**CSV columns not detected**  
→ Click "Edit Mapping" after upload and manually assign each column

**N/A scores for some participants**  
→ Transcript for that session is empty or under 50 chars — check column mapping

**A domain missing from KPI cards**  
→ Check the rubric uses `##` for that domain name; re-upload after fixing

**Evaluation times out**  
→ 16 participants × 29 indicators ≈ 3–5 min. Check backend is running and API key has credits

---

## Ethical Use

AI-generated scores are intended for research and instructional support only — not as final grades. All scores should be reviewed by a qualified instructor. The tool surfaces evidence and patterns to support human judgment, not replace it.

---

*RubricAI v2 · CPS LEARN Lab · Northeastern University · Internal Research Tool*
