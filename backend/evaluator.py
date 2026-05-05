import os
import json
import time
import re
import asyncio
from concurrent.futures import ThreadPoolExecutor
import anthropic
from dotenv import load_dotenv

load_dotenv()

CLAUDE_MODEL = "claude-haiku-4-5-20251001"  # fast + cheap for bulk evaluation
MAX_CONCURRENT = 10  # parallel participants; each runs 2 sessions in parallel → up to 20 concurrent API calls

# Haiku 4.5 pricing (per million tokens)
PRICE_INPUT_PER_M  = 0.80
PRICE_OUTPUT_PER_M = 4.00

executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT * 2)

# ── CLAUDE CLIENT (singleton — reuses connection pool across all threads) ──────
_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def get_claude_client():
    return _client

# ── GLOBAL TOKEN COUNTER (thread-safe via GIL on int ops) ────
_token_stats = {"input": 0, "output": 0, "calls": 0}

def get_cost_summary():
    t = _token_stats
    cost = (t["input"] / 1_000_000 * PRICE_INPUT_PER_M) + (t["output"] / 1_000_000 * PRICE_OUTPUT_PER_M)
    return {
        "calls": t["calls"],
        "input_tokens": t["input"],
        "output_tokens": t["output"],
        "estimated_cost_usd": round(cost, 4)
    }

def reset_cost_counter():
    _token_stats["input"] = 0
    _token_stats["output"] = 0
    _token_stats["calls"] = 0

# ── RATE-LIMIT-AWARE CALL ─────────────────────────────────────
def call_claude(prompt, max_retries=3):
    client = get_claude_client()
    for attempt in range(max_retries):
        try:
            response = client.messages.create(
    model=CLAUDE_MODEL,
    max_tokens=8192,
    temperature=0.0,
                messages=[{"role": "user", "content": prompt}]
            )
            # track token usage
            _token_stats["input"]  += response.usage.input_tokens
            _token_stats["output"] += response.usage.output_tokens
            _token_stats["calls"]  += 1
            return response.content[0].text
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "rate" in err or "overloaded" in err:
                wait = 20 * (attempt + 1)
                print(f"    Rate limited — waiting {wait}s (retry {attempt+1}/{max_retries})")
                time.sleep(wait)
            elif attempt < max_retries - 1:
                print(f"    API error (attempt {attempt+1}): {e} — retrying in 5s")
                time.sleep(5)
            else:
                raise
    return None


# ── LOAD RUBRIC ───────────────────────────────────────────────
def load_rubric(rubric_text=None):
    if rubric_text:
        return rubric_text
    rubric_path = os.path.join(os.path.dirname(__file__), "rubric.md")
    if os.path.exists(rubric_path):
        with open(rubric_path, "r") as f:
            return f.read()
    return ""


# ── RUBRIC SECTION EXTRACTOR ──────────────────────────────────
def extract_indicator_sections(rubric_text, indicator_ids):
    if not indicator_ids or not rubric_text:
        return rubric_text

    lines = rubric_text.split('\n')

    # Auto-detect indicator heading level (same logic as frontend)
    ind_head_level = 5
    for line in lines:
        m = re.match(r'^(#{2,6})\s+.*indicator', line, re.I)
        if m:
            ind_head_level = len(m.group(1))
            break
    cluster_head_level = ind_head_level - 1
    ind_prefix = '#' * ind_head_level + ' '
    cluster_prefix = '#' * cluster_head_level + ' '

    cluster_idx = 0
    ind_idx = 0
    current_id = None
    current_lines = []
    sections = {}

    for line in lines:
        is_ind = line.startswith(ind_prefix)
        is_cluster = line.startswith(cluster_prefix) and not is_ind

        if is_cluster:
            if current_id and current_lines:
                sections[current_id] = '\n'.join(current_lines)
            current_id = None
            current_lines = []
            cluster_idx += 1
            ind_idx = 0
            continue

        if is_ind:
            if current_id and current_lines:
                sections[current_id] = '\n'.join(current_lines)
            current_id = None
            current_lines = []
            header = re.sub(r'^#+\s+', '', line).replace('**', '').strip()
            if re.search(r'indicator', header, re.I):
                ind_idx += 1
                current_id = f"C{cluster_idx}_I{ind_idx}"
                current_lines = [line]
            continue

        if current_id:
            current_lines.append(line)

    if current_id and current_lines:
        sections[current_id] = '\n'.join(current_lines)

    parts = []
    for ind_id in indicator_ids:
        if ind_id in sections:
            parts.append(f"[{ind_id}]\n{sections[ind_id]}")

    if not parts:
        print(f"  Warning: Could not extract rubric sections for {indicator_ids} — using full rubric")
        return rubric_text

    return '\n\n'.join(parts)

# ── CONTEXT BUILDER ───────────────────────────────────────────
def build_context(setup_data=None):
    if not setup_data:
        return ""
    fields = [
        ("course", "Course/Program"),
        ("academic_level", "Academic Level"),
        ("institution", "Institution"),
        ("cohort", "Cohort/Semester"),
        ("simulation_type", "Simulation Type"),
        ("participant_role", "Participant Role"),
        ("session_number", "Session"),
        ("eval_purpose", "Evaluation Purpose"),
        ("language_expectation", "Language/Tone Expectation"),
        ("researcher_looking_for", "Researcher is looking for"),
        ("strong_performance", "Strong performance looks like"),
        ("red_flags", "Red flags to watch for"),
        ("cohort_notes", "Additional cohort context"),
    ]
    parts = [f"{label}: {setup_data[key]}" for key, label in fields if setup_data.get(key)]
    return "\n".join(parts)


# ── SERVER-SIDE SCORE CALCULATION ─────────────────────────────
def calculate_scores(scores_dict, indicator_ids):
    """
    Calculate aggregate scores using the two-step method Harry specified:
      1. Average indicator scores within each cluster → cluster average
      2. Average cluster averages within the domain → domain average
    comm = average of ALL cluster averages (all clusters).
    ct   = average of cluster averages for the SECOND HALF of clusters.
    """
    if not scores_dict or not indicator_ids:
        return 0.0, 0.0

    def cluster_num(ind_id):
        m = re.match(r'C(\d+)_', ind_id)
        return int(m.group(1)) if m else 0

    # Step 1: compute per-cluster averages
    cluster_buckets = {}
    for ind in indicator_ids:
        c = cluster_num(ind)
        if ind in scores_dict and isinstance(scores_dict[ind].get("score"), (int, float)):
            cluster_buckets.setdefault(c, []).append(scores_dict[ind]["score"])

    cluster_avgs = {c: sum(v) / len(v) for c, v in cluster_buckets.items() if v}
    if not cluster_avgs:
        return 0.0, 0.0

    # Step 2: average cluster averages → domain averages
    cluster_nums = sorted(cluster_avgs.keys())
    total_clusters = len(cluster_nums)
    ct_threshold = cluster_nums[total_clusters // 2] if total_clusters >= 2 else 999

    all_avgs = list(cluster_avgs.values())
    ct_avgs = [cluster_avgs[c] for c in cluster_nums if c >= ct_threshold]

    comm = round(sum(all_avgs) / len(all_avgs), 2) if all_avgs else 0.0
    ct = round(sum(ct_avgs) / len(ct_avgs), 2) if ct_avgs else 0.0
    return comm, ct


# ── FLAG LOGIC ────────────────────────────────────────────────
def determine_flags(scores_dict):
    if not scores_dict:
        return True, "No scores recorded — session may be incomplete or transcript too short."
    score_values = [v.get("score", 0) for v in scores_dict.values() if v.get("score")]
    if not score_values:
        return True, "No valid scores found."
    level1_count = sum(1 for s in score_values if s == 1)
    avg = sum(score_values) / len(score_values)
    reasons = []
    if level1_count >= 2:
        reasons.append(f"{level1_count} indicators at Beginning (Level 1)")
    if avg < 2.0:
        reasons.append(f"Average {avg:.2f} below developing threshold")
    return (True, "; ".join(reasons)) if reasons else (False, "")


# ── EVALUATE SESSION ──────────────────────────────────────────
def evaluate_session(
    transcript, participant_id, session_type,
    duration=0, rubric_text=None,
    selected_indicators=None, setup_data=None, rubric_desc_map=None
):
    if not rubric_text:
        rubric_text = load_rubric()

    if not selected_indicators:
        print(f"  No indicators for [{session_type}] — skipping")
        return None

    rubric_section = extract_indicator_sections(rubric_text, selected_indicators)
    transcript_section = str(transcript)
    context_block = build_context(setup_data)
    session_label = "User Interview" if session_type == "user_interview" else "Client Conversation"

    # Build indicator list with names for clarity
    ind_lines = []
    for ind in selected_indicators:
        name = (rubric_desc_map or {}).get(ind, ind)
        ind_lines.append(f"  {ind}: {name}")
    ind_list_text = "\n".join(ind_lines)

    print(f"  [{session_label}] {participant_id} — {len(selected_indicators)} indicators")

    prompt = f"""You are an expert educational assessor for a university research lab.
Evaluate this student's {session_label} transcript against the rubric below.

PARTICIPANT: {participant_id}
SESSION: {session_label}
DURATION: {duration} seconds
{f"CONTEXT:{chr(10)}{context_block}{chr(10)}" if context_block else ""}
INDICATORS TO SCORE:
{ind_list_text}

RUBRIC LEVEL DESCRIPTORS (score STRICTLY against these — not general impression):
{rubric_section}

STUDENT TRANSCRIPT:
{transcript_section}

SCORING RULES:
- Score: 1=Beginning, 2=Developing, 3=Applying, 4=Mastery
- rationale: 1-2 concise sentences citing rubric criteria and transcript evidence
- feedback: 1 actionable sentence for reaching the next level
- quotes: 1 short verbatim quote ([] if none found)
- If transcript lacks sufficient evidence, score 1 and state why briefly
- summary: 1-2 sentence overview of overall performance

Return ONLY valid JSON:
{{
  "scores": {{
    "INDICATOR_ID": {{
      "score": 2,
      "rationale": "rubric criteria + transcript evidence",
      "feedback": "one actionable step",
      "quotes": ["short verbatim quote"]
    }}
  }},
  "summary": "brief overall narrative"
}}"""

    def strip_markdown(t):
        if "```json" in t:
            return t.split("```json")[1].split("```")[0].strip()
        if "```" in t:
            return t.split("```")[1].split("```")[0].strip()
        return t

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            text = call_claude(prompt)
            if not text:
                print(f"    ✗ No response — {participant_id} [{session_label}] attempt {attempt}/{max_attempts}")
                continue
            text = strip_markdown(text)
            parsed = json.loads(text)
            score_count = len(parsed.get("scores", {}))
            if attempt > 1:
                print(f"    ✓ Succeeded on attempt {attempt} — {participant_id} [{session_label}]")
            else:
                print(f"    ✓ {score_count}/{len(selected_indicators)} scored — {participant_id} [{session_label}]")
            return parsed
        except json.JSONDecodeError as e:
            print(f"    ✗ JSON error attempt {attempt}/{max_attempts} — {participant_id} [{session_label}]: {e}")
        except Exception as e:
            print(f"    ✗ Error attempt {attempt}/{max_attempts} — {participant_id} [{session_label}]: {e}")

    print(f"    ✗ All {max_attempts} attempts failed — {participant_id} [{session_label}]")
    return None


# ── FLEXIBLE COLUMN EXTRACTION ────────────────────────────────
def get_col(row, *keys, default=""):
    for k in keys:
        if k in row and row[k]:
            return row[k]
    row_lower = {str(k).lower().strip(): v for k, v in row.items()}
    for k in keys:
        if str(k).lower() in row_lower and row_lower[str(k).lower()]:
            return row_lower[str(k).lower()]
    return default


# ── EVALUATE PARTICIPANT (sync, runs in thread pool) ──────────
def evaluate_participant(
    row, rubric_text=None,
    selected_u_indicators=None, selected_c_indicators=None,
    setup_data=None, rubric_desc_map=None
):
    pid = get_col(row, "participant_id", "student_id", "id", "student", "name", "participant")
    simulation = get_col(row, "simulation", "sim", "course", "assignment", "session_name", "scenario")
    transcript_user = get_col(
        row, "transcript_user", "user_transcript", "interview_transcript",
        "transcript_a", "script_a", "user_session", "interview"
    )
    transcript_client = get_col(
        row, "transcript_client", "client_transcript", "client_conversation",
        "transcript_b", "script_b", "client_session", "client"
    )
    duration_user = get_col(row, "duration_seconds_user", "duration_user", "user_duration", default=0)
    duration_client = get_col(row, "duration_seconds_client", "duration_client", "client_duration", default=0)
    completed_user = get_col(row, "completed_user", "completed", "status", default="Complete")
    batch = get_col(row, "batch", "group", "cohort_group", "section", "class_group", default="")

    print(f"\n{'='*50}")
    print(f"Participant: {pid} | Sim: {simulation}")
    print(f"  User transcript: {len(str(transcript_user))} chars")
    print(f"  Client transcript: {len(str(transcript_client))} chars")

    result = {
        "participant_id": str(pid) if pid else "unknown",
        "simulation": str(simulation) if simulation else "unknown",
        "batch": str(batch) if batch else "",
        "completed": 1 if str(completed_user).lower() in ["complete", "yes", "1", "true", "y"] else 0,
        "comm_user": None, "ct_user": None,
        "comm_client": None, "ct_client": None,
        "_detail": {}
    }

    # ── USER INTERVIEW ──
    has_user = transcript_user and len(str(transcript_user).strip()) > 50
    has_u_inds = selected_u_indicators and len(selected_u_indicators) > 0

    if has_user and has_u_inds:
        user_result = evaluate_session(
            transcript_user, pid, "user_interview",
            duration=duration_user,
            rubric_text=rubric_text,
            selected_indicators=selected_u_indicators,
            setup_data=setup_data,
            rubric_desc_map=rubric_desc_map
        )
        if user_result:
            comm, ct = calculate_scores(user_result.get("scores", {}), selected_u_indicators)
            result["comm_user"] = comm
            result["ct_user"] = ct
            result["_detail"]["user"] = user_result
            for ind, data in user_result.get("scores", {}).items():
                result[f"{ind}_user_score"] = data.get("score", 0)
    elif not has_user:
        print(f"  Skipping user interview — transcript too short or missing")
    elif not has_u_inds:
        print(f"  Skipping user interview — no indicators selected")

    # ── CLIENT CONVERSATION ──
    has_client = transcript_client and len(str(transcript_client).strip()) > 50
    has_c_inds = selected_c_indicators and len(selected_c_indicators) > 0

    if has_client and has_c_inds:
        client_result = evaluate_session(
            transcript_client, pid, "client_conversation",
            duration=duration_client,
            rubric_text=rubric_text,
            selected_indicators=selected_c_indicators,
            setup_data=setup_data,
            rubric_desc_map=rubric_desc_map
        )
        if client_result:
            comm, ct = calculate_scores(client_result.get("scores", {}), selected_c_indicators)
            result["comm_client"] = comm
            result["ct_client"] = ct
            result["_detail"]["client"] = client_result
            for ind, data in client_result.get("scores", {}).items():
                result[f"{ind}_client_score"] = data.get("score", 0)
    elif not has_client:
        print(f"  Skipping client conversation — transcript too short or missing")
    elif not has_c_inds:
        print(f"  Skipping client conversation — no indicators selected")

    return result


# ── ASYNC WRAPPER — parallel sessions per participant ─────────
async def evaluate_participant_async(
    row, rubric_text, sel_u, sel_c,
    setup_data, rubric_desc_map, semaphore
):
    async with semaphore:
        loop = asyncio.get_event_loop()

        # Extract row fields (sync, no I/O)
        pid = get_col(row, "participant_id", "student_id", "id", "student", "name", "participant")
        simulation = get_col(row, "simulation", "sim", "course", "assignment", "session_name", "scenario")
        transcript_user = get_col(
            row, "transcript_user", "user_transcript", "interview_transcript",
            "transcript_a", "script_a", "user_session", "interview"
        )
        transcript_client = get_col(
            row, "transcript_client", "client_transcript", "client_conversation",
            "transcript_b", "script_b", "client_session", "client"
        )
        duration_user  = get_col(row, "duration_seconds_user",   "duration_user",   "user_duration",   default=0)
        duration_client = get_col(row, "duration_seconds_client", "duration_client", "client_duration", default=0)
        completed_user  = get_col(row, "completed_user", "completed", "status", default="Complete")
        batch           = get_col(row, "batch", "group", "cohort_group", "section", "class_group", default="")

        print(f"\n{'='*50}")
        print(f"Participant: {pid} | Sim: {simulation}")
        print(f"  User transcript: {len(str(transcript_user))} chars")
        print(f"  Client transcript: {len(str(transcript_client))} chars")

        result = {
            "participant_id": str(pid) if pid else "unknown",
            "simulation":     str(simulation) if simulation else "unknown",
            "batch":          str(batch) if batch else "",
            "completed": 1 if str(completed_user).lower() in ["complete", "yes", "1", "true", "y"] else 0,
            "comm_user": None, "ct_user": None,
            "comm_client": None, "ct_client": None,
            "_detail": {}
        }

        has_user   = transcript_user   and len(str(transcript_user).strip())   > 50
        has_client = transcript_client and len(str(transcript_client).strip()) > 50
        has_u_inds = sel_u and len(sel_u) > 0
        has_c_inds = sel_c and len(sel_c) > 0

        # ── Run both sessions in parallel ──────────────────────
        async def run_user():
            if not has_user:
                print(f"  Skipping user interview — transcript too short or missing")
                return None
            if not has_u_inds:
                print(f"  Skipping user interview — no indicators selected")
                return None
            return await loop.run_in_executor(
                executor,
                lambda: evaluate_session(
                    transcript_user, pid, "user_interview",
                    duration_user, rubric_text, sel_u, setup_data, rubric_desc_map
                )
            )

        async def run_client():
            if not has_client:
                print(f"  Skipping client conversation — transcript too short or missing")
                return None
            if not has_c_inds:
                print(f"  Skipping client conversation — no indicators selected")
                return None
            return await loop.run_in_executor(
                executor,
                lambda: evaluate_session(
                    transcript_client, pid, "client_conversation",
                    duration_client, rubric_text, sel_c, setup_data, rubric_desc_map
                )
            )

        try:
            user_result, client_result = await asyncio.gather(run_user(), run_client())
        except Exception as e:
            print(f"  !! Session evaluation error for {pid}: {e} — returning partial result")
            user_result, client_result = None, None

        if user_result:
            comm, ct = calculate_scores(user_result.get("scores", {}), sel_u)
            result["comm_user"] = comm
            result["ct_user"]   = ct
            result["_detail"]["user"] = user_result
            for ind, data in user_result.get("scores", {}).items():
                result[f"{ind}_user_score"] = data.get("score", 0)
            # Per-cluster averages (handles any number of domains dynamically)
            cluster_scores = {}
            for ind, data in user_result.get("scores", {}).items():
                m = re.match(r'C(\d+)_', ind)
                if m:
                    c = int(m.group(1))
                    cluster_scores.setdefault(c, []).append(data.get("score", 0))
            for c, vals in cluster_scores.items():
                result[f"cluster_{c}_user_avg"] = round(sum(vals)/len(vals), 2)

        if client_result:
            comm, ct = calculate_scores(client_result.get("scores", {}), sel_c)
            result["comm_client"] = comm
            result["ct_client"]   = ct
            result["_detail"]["client"] = client_result
            for ind, data in client_result.get("scores", {}).items():
                result[f"{ind}_client_score"] = data.get("score", 0)
            # Per-cluster averages (handles any number of domains dynamically)
            cluster_scores = {}
            for ind, data in client_result.get("scores", {}).items():
                m = re.match(r'C(\d+)_', ind)
                if m:
                    c = int(m.group(1))
                    cluster_scores.setdefault(c, []).append(data.get("score", 0))
            for c, vals in cluster_scores.items():
                result[f"cluster_{c}_client_avg"] = round(sum(vals)/len(vals), 2)

        return result