import os
import csv
import json
import io
import asyncio
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from typing import Optional
from dotenv import load_dotenv
load_dotenv()
from evaluator import evaluate_participant_async, load_rubric, MAX_CONCURRENT
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

app = FastAPI()

def parse_upload_to_rows(contents: bytes, filename: str) -> list:
    """Return a list of row dicts from a CSV, XLSX, or XLS upload."""
    fname = (filename or "").lower()
    if fname.endswith(".xlsx"):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(contents), read_only=True, data_only=True)
        ws = wb.active
        rows_iter = iter(ws.rows)
        headers = [cell.value for cell in next(rows_iter)]
        rows = [
            {headers[i]: ("" if cell.value is None else str(cell.value))
             for i, cell in enumerate(row)}
            for row in rows_iter
        ]
        wb.close()
        return rows
    elif fname.endswith(".xls"):
        import xlrd
        wb = xlrd.open_workbook(file_contents=contents)
        ws = wb.sheet_by_index(0)
        headers = [str(ws.cell_value(0, c)) for c in range(ws.ncols)]
        return [
            {headers[c]: str(ws.cell_value(r, c)) for c in range(ws.ncols)}
            for r in range(1, ws.nrows)
        ]
    else:
        text = contents.decode("utf-8-sig")
        return list(csv.DictReader(io.StringIO(text)))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"status": "RubricAI v2 backend running"}

# ── DETECT COLUMNS ────────────────────────────────────────────
@app.post("/api/detect-columns")
async def detect_columns(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        rows = parse_upload_to_rows(contents, file.filename)
        if not rows:
            return JSONResponse({"status": "error", "message": "File is empty"})
        columns = [c.strip() for c in rows[0].keys()]
        sample_row = {k.strip(): str(v)[:150] for k, v in rows[0].items()}
        mapping = {}
        for col in columns:
            c = col.lower().strip()
            if any(k in c for k in ["participant_id", "participant", "student_id", "student", "id"]):
                if "participant_id" not in mapping:
                    mapping["participant_id"] = col
            elif any(k in c for k in ["simulation", "sim", "course", "scenario", "assignment"]):
                if "simulation" not in mapping:
                    mapping["simulation"] = col
            elif any(k in c for k in ["completed", "status", "done", "finish"]):
                if "completed_user" not in mapping:
                    mapping["completed_user"] = col
            elif any(k in c for k in ["transcript_user", "user_transcript", "interview", "script_a", "transcript_a"]):
                mapping["transcript_user"] = col
            elif any(k in c for k in ["transcript_client", "client_transcript", "client", "script_b", "transcript_b"]):
                mapping["transcript_client"] = col
            elif any(k in c for k in ["duration_user", "duration_seconds_user"]):
                mapping["duration_seconds_user"] = col
            elif any(k in c for k in ["duration_client", "duration_seconds_client"]):
                mapping["duration_seconds_client"] = col
            elif any(k in c for k in ["batch", "group", "section", "cohort_group", "class_group"]):
                if "batch" not in mapping:
                    mapping["batch"] = col
        # Fallback: long text columns are likely transcripts
        for col in columns:
            if col not in mapping.values():
                avg_len = sum(len(str(r.get(col, ""))) for r in rows[:3]) / 3
                if avg_len > 300:
                    if "transcript_user" not in mapping:
                        mapping["transcript_user"] = col
                    elif "transcript_client" not in mapping:
                        mapping["transcript_client"] = col
        return JSONResponse({
            "status": "success",
            "columns": columns,
            "suggested_mapping": mapping,
            "total_rows": len(rows),
            "sample": sample_row
        })
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)})

# ── EVALUATE ──────────────────────────────────────────────────
@app.post("/api/evaluate")
async def evaluate(
    file: UploadFile = File(...),
    rubric: Optional[UploadFile] = File(None),
    column_mapping: Optional[str] = Form(None),
    selected_indicators: Optional[str] = Form(None),
    selected_u_indicators: Optional[str] = Form(None),
    selected_c_indicators: Optional[str] = Form(None),
    rubric_desc_map: Optional[str] = Form(None),
    setup_data: Optional[str] = Form(None)
):
    try:
        # Load rubric
        rubric_text = None
        if rubric and rubric.filename:
            rubric_contents = await rubric.read()
            rubric_text = rubric_contents.decode("utf-8")
            rubric_path = os.path.join(os.path.dirname(__file__), "rubric.md")
            with open(rubric_path, "w") as f:
                f.write(rubric_text)
        else:
            rubric_text = load_rubric()

        # Parse indicators — prefer split U/C, fall back to legacy combined
        def parse_json_field(s):
            try:
                return json.loads(s) if s else None
            except Exception:
                return None

        sel_u = parse_json_field(selected_u_indicators)
        sel_c = parse_json_field(selected_c_indicators)
        desc_map = parse_json_field(rubric_desc_map) or {}

        # Legacy fallback: if old single-list sent, use for both sessions
        if not sel_u and not sel_c:
            legacy = parse_json_field(selected_indicators)
            if legacy:
                sel_u = legacy
                sel_c = legacy

        col_map = parse_json_field(column_mapping)
        setup = parse_json_field(setup_data)

        # Read file (CSV or Excel)
        contents = await file.read()
        rows = parse_upload_to_rows(contents, file.filename)

        if not rows:
            return JSONResponse({"status": "error", "message": "No data found in file"})

        # Apply column mapping
        if col_map:
            inv_map = {v: k for k, v in col_map.items()}
            mapped_rows = []
            for row in rows:
                new_row = {}
                for col, val in row.items():
                    standard = inv_map.get(col.strip(), col.strip())
                    new_row[standard] = val
                mapped_rows.append(new_row)
            rows = mapped_rows

        print(f"\nEvaluating {len(rows)} participants — {MAX_CONCURRENT} parallel")
        print(f"  User indicators: {sel_u}")
        print(f"  Client indicators: {sel_c}")

        # Parallel evaluation using asyncio.gather + semaphore
        semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        tasks = [
            evaluate_participant_async(
                row, rubric_text, sel_u, sel_c,
                setup, desc_map, semaphore
            )
            for row in rows
        ]
        results = await asyncio.gather(*tasks)
        students = [r for r in results if r]

        return JSONResponse({
            "status": "success",
            "students": students,
            "total": len(students)
        })

    except Exception as e:
        import traceback
        print(f"Evaluation error: {e}")
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(e)})


# ── EVALUATE (STREAMING) ──────────────────────────────────────
@app.post("/api/evaluate-stream")
async def evaluate_stream(
    file: UploadFile = File(...),
    rubric: Optional[UploadFile] = File(None),
    column_mapping: Optional[str] = Form(None),
    selected_indicators: Optional[str] = Form(None),
    selected_u_indicators: Optional[str] = Form(None),
    selected_c_indicators: Optional[str] = Form(None),
    rubric_desc_map: Optional[str] = Form(None),
    setup_data: Optional[str] = Form(None)
):
    # ── Parse inputs (same as /api/evaluate) ──────────────────
    rubric_text = None
    if rubric and rubric.filename:
        rubric_contents = await rubric.read()
        rubric_text = rubric_contents.decode("utf-8")
        rubric_path = os.path.join(os.path.dirname(__file__), "rubric.md")
        with open(rubric_path, "w") as f:
            f.write(rubric_text)
    else:
        rubric_text = load_rubric()

    def parse_json_field(s):
        try:
            return json.loads(s) if s else None
        except Exception:
            return None

    sel_u    = parse_json_field(selected_u_indicators)
    sel_c    = parse_json_field(selected_c_indicators)
    desc_map = parse_json_field(rubric_desc_map) or {}
    if not sel_u and not sel_c:
        legacy = parse_json_field(selected_indicators)
        if legacy:
            sel_u = legacy
            sel_c = legacy

    col_map = parse_json_field(column_mapping)
    setup   = parse_json_field(setup_data)

    contents = await file.read()
    rows = parse_upload_to_rows(contents, file.filename)
    if not rows:
        async def err_gen():
            yield f"data: {json.dumps({'type':'error','message':'No data found in file'})}\n\n"
        return StreamingResponse(err_gen(), media_type="text/event-stream")

    if col_map:
        inv_map = {v: k for k, v in col_map.items()}
        mapped = []
        for row in rows:
            new_row = {inv_map.get(col.strip(), col.strip()): val for col, val in row.items()}
            mapped.append(new_row)
        rows = mapped

    total = len(rows)
    print(f"\nStreaming evaluation — {total} participants — {MAX_CONCURRENT} parallel")

    # ── Stream results as each participant finishes ────────────
    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue()
        semaphore = asyncio.Semaphore(MAX_CONCURRENT)

        async def wrapped(row):
            result = await evaluate_participant_async(
                row, rubric_text, sel_u, sel_c, setup, desc_map, semaphore
            )
            await queue.put(result)

        # Fire all tasks concurrently — results land in queue as they finish
        for row in rows:
            asyncio.create_task(wrapped(row))

        # Emit start event
        yield f"data: {json.dumps({'type':'start','total':total})}\n\n"

        completed = 0
        while completed < total:
            result = await queue.get()
            completed += 1
            if result:
                yield f"data: {json.dumps({'type':'student','done':completed,'total':total,'student':result})}\n\n"
            else:
                yield f"data: {json.dumps({'type':'skip','done':completed,'total':total})}\n\n"

        yield f"data: {json.dumps({'type':'done','total':total})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disables nginx buffering if behind proxy
        }
    )

# ── CHAT ──────────────────────────────────────────────────────
@app.post("/api/chat")
async def chat(request: dict):
    try:
        import anthropic
        system = request.get("system", "You are a helpful educational assessment assistant.")
        messages = request.get("messages", [])
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            system=system,
            messages=[{"role": m["role"], "content": m["content"]} for m in messages]
        )
        return JSONResponse({"status": "success", "reply": response.content[0].text})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)})

# ── EXPORT CSV ────────────────────────────────────────────────
@app.post("/api/export/csv")
async def export_csv(request: dict):
    students = request.get("students", [])
    if not students:
        return JSONResponse({"status": "error", "message": "No data to export"})

    output = io.StringIO()
    score_keys = sorted(set(k for s in students for k in s.keys() if k.endswith("_score")))
    fieldnames = ["participant_id", "simulation", "completed",
                  "comm_user", "ct_user", "comm_client", "ct_client"] + score_keys

    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for s in students:
        writer.writerow({k: s.get(k, "") for k in fieldnames})

    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=rubricai_scores.csv"}
    )

# ── EXPORT PDF (Professional) ─────────────────────────────────
@app.post("/api/export/pdf")
async def export_pdf(request: dict):
    students = request.get("students", [])
    setup = request.get("setup_data", {})
    if not students:
        return JSONResponse({"status": "error", "message": "No data to export"})

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.75*inch,
        leftMargin=0.75*inch,
        topMargin=0.75*inch,
        bottomMargin=0.75*inch
    )

    styles = getSampleStyleSheet()
    story = []

    # ── Title Page ──
    title_style = ParagraphStyle('Title', parent=styles['Title'],
        fontSize=22, textColor=colors.HexColor('#0f172a'),
        spaceAfter=6, alignment=TA_LEFT)
    sub_style = ParagraphStyle('Sub', parent=styles['Normal'],
        fontSize=10, textColor=colors.HexColor('#64748b'),
        spaceAfter=4)
    head_style = ParagraphStyle('Head', parent=styles['Heading2'],
        fontSize=13, textColor=colors.HexColor('#1e3a5f'),
        spaceBefore=14, spaceAfter=4)
    body_style = ParagraphStyle('Body', parent=styles['Normal'],
        fontSize=9.5, textColor=colors.HexColor('#334155'),
        leading=14, spaceAfter=4)
    label_style = ParagraphStyle('Label', parent=styles['Normal'],
        fontSize=8, textColor=colors.HexColor('#64748b'),
        spaceAfter=2, fontName='Helvetica-Bold')
    score_style = ParagraphStyle('Score', parent=styles['Normal'],
        fontSize=9.5, textColor=colors.HexColor('#0f172a'),
        leading=13, spaceAfter=3)

    from datetime import datetime
    story.append(Paragraph("RubricAI v2", title_style))
    story.append(Paragraph("Class Evaluation Report", ParagraphStyle('Sub2',
        parent=styles['Normal'], fontSize=14, textColor=colors.HexColor('#3b82f6'),
        spaceAfter=4)))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", sub_style))
    if setup.get("course"):
        story.append(Paragraph(f"Course: {setup['course']}", sub_style))
    if setup.get("cohort"):
        story.append(Paragraph(f"Cohort: {setup['cohort']}", sub_style))
    story.append(Paragraph("CPS LEARN Lab · Northeastern University", sub_style))
    story.append(HRFlowable(width="100%", thickness=1.5,
        color=colors.HexColor('#3b82f6'), spaceAfter=16))

    # ── Summary Table ──
    story.append(Paragraph("Cohort Summary", head_style))
    tot = len(students)
    comp = sum(1 for s in students if s.get("completed") == 1)
    comm_vals = [s["comm_user"] for s in students if s.get("comm_user") is not None]
    ct_vals = [s["ct_user"] for s in students if s.get("ct_user") is not None]
    avg_comm = f"{sum(comm_vals)/len(comm_vals):.2f}" if comm_vals else "N/A"
    avg_ct = f"{sum(ct_vals)/len(ct_vals):.2f}" if ct_vals else "N/A"

    summary_data = [
        ["Total Participants", "Completed", "Avg Comm Score", "Avg CT Score"],
        [str(tot), str(comp), avg_comm, avg_ct]
    ]
    summary_table = Table(summary_data, colWidths=[1.5*inch]*4)
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f1f5f9')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor('#64748b')),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('FONTNAME', (0,1), (-1,1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,1), (-1,1), 13),
        ('TEXTCOLOR', (0,1), (-1,1), colors.HexColor('#0f172a')),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0,1), (-1,1), [colors.white]),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 20))

    # ── Per Student ──
    story.append(Paragraph("Individual Evaluation Reports", head_style))
    story.append(HRFlowable(width="100%", thickness=0.5,
        color=colors.HexColor('#e2e8f0'), spaceAfter=12))

    level_map = {1: "Beginning", 2: "Developing", 3: "Applying", 4: "Mastery"}
    score_colors = {1: '#ef4444', 2: '#f97316', 3: '#f59e0b', 4: '#10b981'}

    for s in students:
        pid = s.get("participant_id", "N/A")
        sim = s.get("simulation", "N/A")
        completed = "Completed" if s.get("completed") == 1 else "Incomplete"

        # Student header
        story.append(Paragraph(
            f"<b>{pid}</b> &nbsp;·&nbsp; {sim} &nbsp;·&nbsp; {completed}",
            ParagraphStyle('SHead', parent=styles['Normal'],
                fontSize=11, textColor=colors.HexColor('#0f172a'),
                backColor=colors.HexColor('#f8fafc'),
                borderPad=6, spaceBefore=10, spaceAfter=6,
                borderColor=colors.HexColor('#e2e8f0'), borderWidth=0.5)
        ))

        # Score summary
        score_row = [
            ["User Interview Comm", "User Interview CT", "Client Conv Comm", "Client Conv CT"],
            [
                str(s.get("comm_user") or "N/A"),
                str(s.get("ct_user") or "N/A"),
                str(s.get("comm_client") or "N/A"),
                str(s.get("ct_client") or "N/A")
            ]
        ]
        score_table = Table(score_row, colWidths=[1.5*inch]*4)
        score_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f1f5f9')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor('#64748b')),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica'),
            ('FONTSIZE', (0,0), (-1,-1), 8.5),
            ('FONTNAME', (0,1), (-1,1), 'Helvetica-Bold'),
            ('FONTSIZE', (0,1), (-1,1), 12),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(score_table)
        story.append(Spacer(1, 8))

        # Indicator details
        detail = s.get("_detail", {})
        for sess_key, sess_label in [("user", "User Interview"), ("client", "Client Conversation")]:
            sess_data = detail.get(sess_key, {})
            if not sess_data:
                continue
            story.append(Paragraph(sess_label, ParagraphStyle('SessLabel',
                parent=styles['Normal'], fontSize=9,
                textColor=colors.HexColor('#3b82f6'),
                fontName='Helvetica-Bold', spaceBefore=8, spaceAfter=4)))

            # Summary
            if sess_data.get("summary"):
                story.append(Paragraph(sess_data["summary"], body_style))

            # Indicator table
            ind_table_data = [["Indicator", "Score", "Level", "Rationale", "Feedback", "Evidence"]]
            for ind, data in sess_data.get("scores", {}).items():
                sc = data.get("score", 0)
                lvl = level_map.get(sc, "N/A")
                rat = data.get("rationale", "")
                fb = data.get("feedback", "")
                quotes = data.get("quotes", [])
                ev = quotes[0] if quotes else ""
                ind_table_data.append([
                    Paragraph(f"<b>{ind}</b>", score_style),
                    Paragraph(f"<b>{sc}</b>", score_style),
                    Paragraph(lvl, score_style),
                    Paragraph(rat, body_style),
                    Paragraph(fb, body_style),
                    Paragraph(f'"{ev}"' if ev else "", body_style)
                ])

            if len(ind_table_data) > 1:
                ind_table = Table(ind_table_data,
                    colWidths=[0.7*inch, 0.45*inch, 0.7*inch, 1.8*inch, 1.8*inch, 1.5*inch])
                ind_table.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f1f5f9')),
                    ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor('#64748b')),
                    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0,0), (-1,-1), 8),
                    ('ALIGN', (0,0), (2,-1), 'CENTER'),
                    ('ALIGN', (3,0), (-1,-1), 'LEFT'),
                    ('VALIGN', (0,0), (-1,-1), 'TOP'),
                    ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
                    ('INNERGRID', (0,0), (-1,-1), 0.3, colors.HexColor('#e2e8f0')),
                    ('ROWBACKGROUNDS', (0,1), (-1,-1),
                        [colors.white, colors.HexColor('#f8fafc')]),
                    ('TOPPADDING', (0,0), (-1,-1), 5),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 5),
                    ('LEFTPADDING', (0,0), (-1,-1), 4),
                    ('RIGHTPADDING', (0,0), (-1,-1), 4),
                ]))
                story.append(ind_table)
                story.append(Spacer(1, 6))

        story.append(HRFlowable(width="100%", thickness=0.5,
            color=colors.HexColor('#e2e8f0'), spaceAfter=10))

    # ── Footer ──
    def add_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(colors.HexColor('#94a3b8'))
        canvas.drawString(0.75*inch, 0.4*inch,
            "RubricAI v2 · CPS LEARN Lab · Northeastern University · Confidential Research Record")
        canvas.drawRightString(letter[0] - 0.75*inch, 0.4*inch,
            f"Page {doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=add_footer, onLaterPages=add_footer)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=rubricai_report.pdf"}
    )

# ── EXPORT COHORT PDF ─────────────────────────────────────────
@app.post("/api/export/cohort-pdf")
async def export_cohort_pdf(request: dict):
    from datetime import datetime
    setup = request.get("setup_data", {})
    kpis = request.get("kpis", {})
    distribution = request.get("distribution", [])
    indicator_averages = request.get("indicator_averages", [])
    cohort_summary = request.get("cohort_summary", "")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        rightMargin=0.75*inch, leftMargin=0.75*inch,
        topMargin=0.75*inch, bottomMargin=0.75*inch
    )
    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle('Title', parent=styles['Title'],
        fontSize=22, textColor=colors.HexColor('#0f172a'), spaceAfter=6, alignment=TA_LEFT)
    sub_style = ParagraphStyle('Sub', parent=styles['Normal'],
        fontSize=10, textColor=colors.HexColor('#64748b'), spaceAfter=4)
    head_style = ParagraphStyle('Head', parent=styles['Heading2'],
        fontSize=13, textColor=colors.HexColor('#1e3a5f'), spaceBefore=16, spaceAfter=6)
    body_style = ParagraphStyle('Body', parent=styles['Normal'],
        fontSize=9.5, textColor=colors.HexColor('#334155'), leading=14, spaceAfter=4)

    # ── Title Block ──
    story.append(Paragraph("RubricAI v2", title_style))
    story.append(Paragraph("Cohort Summary Report", ParagraphStyle('Sub2',
        parent=styles['Normal'], fontSize=14, textColor=colors.HexColor('#3b82f6'), spaceAfter=4)))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", sub_style))
    if setup.get("course"):
        story.append(Paragraph(f"Course: {setup['course']}", sub_style))
    if setup.get("cohort"):
        story.append(Paragraph(f"Cohort: {setup['cohort']}", sub_style))
    story.append(Paragraph("CPS LEARN Lab · Northeastern University", sub_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#3b82f6'), spaceAfter=16))

    # ── KPI Table ──
    story.append(Paragraph("Cohort KPIs", head_style))
    kpi_headers = ["Total Participants", "Completed", "Avg Comm (User)", "Avg CT (User)"]
    kpi_vals = [
        str(kpis.get("total", "N/A")),
        str(kpis.get("completed", "N/A")),
        str(kpis.get("avg_comm_user") or "N/A"),
        str(kpis.get("avg_ct_user") or "N/A"),
    ]
    if kpis.get("avg_comm_client") is not None:
        kpi_headers += ["Avg Comm (Client)", "Avg CT (Client)"]
        kpi_vals += [str(kpis.get("avg_comm_client") or "N/A"), str(kpis.get("avg_ct_client") or "N/A")]
    n = len(kpi_headers)
    col_w = 7.0 / n * inch
    kpi_table = Table([kpi_headers, kpi_vals], colWidths=[col_w]*n)
    kpi_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f1f5f9')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor('#64748b')),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('FONTNAME', (0,1), (-1,1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,1), (-1,1), 13),
        ('TEXTCOLOR', (0,1), (-1,1), colors.HexColor('#0f172a')),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 16))

    # ── Score Distribution ──
    if distribution:
        story.append(Paragraph("Score Distribution", head_style))
        dist_data = [["Level", "Label", "Count", "Percentage"]]
        for d in distribution:
            dist_data.append([str(d.get("level","")), d.get("label",""), str(d.get("count",0)), f"{d.get('pct',0)}%"])
        dist_table = Table(dist_data, colWidths=[0.6*inch, 1.2*inch, 0.8*inch, 1.2*inch])
        dist_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f1f5f9')),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8fafc')]),
            ('TOPPADDING', (0,0), (-1,-1), 6), ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(dist_table)
        story.append(Spacer(1, 16))

    # ── Indicator Averages ──
    if indicator_averages:
        story.append(Paragraph("Indicator Averages", head_style))
        ind_data = [["Indicator ID", "Session", "Avg Score", "Indicator Name"]]
        for row in indicator_averages:
            avg_val = f"{row['avg']:.2f}" if row.get("avg") is not None else "N/A"
            ind_data.append([row.get("id",""), row.get("session",""), avg_val, row.get("name","")])
        ind_table = Table(ind_data, colWidths=[0.9*inch, 1.6*inch, 0.9*inch, 3.6*inch])
        ind_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f1f5f9')),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8.5),
            ('ALIGN', (0,0), (2,-1), 'CENTER'),
            ('ALIGN', (3,0), (-1,-1), 'LEFT'),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
            ('INNERGRID', (0,0), (-1,-1), 0.3, colors.HexColor('#e2e8f0')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8fafc')]),
            ('TOPPADDING', (0,0), (-1,-1), 5), ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('LEFTPADDING', (0,0), (-1,-1), 4), ('RIGHTPADDING', (0,0), (-1,-1), 4),
        ]))
        story.append(ind_table)
        story.append(Spacer(1, 16))

    # ── AI Cohort Summary ──
    if cohort_summary:
        story.append(Paragraph("AI Cohort Summary", head_style))
        story.append(Paragraph(cohort_summary, body_style))
        story.append(Spacer(1, 16))


    def add_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(colors.HexColor('#94a3b8'))
        canvas.drawString(0.75*inch, 0.4*inch,
            "RubricAI v2 · CPS LEARN Lab · Northeastern University · Confidential Research Record")
        canvas.drawRightString(letter[0] - 0.75*inch, 0.4*inch, f"Page {doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=add_footer, onLaterPages=add_footer)
    buffer.seek(0)
    return StreamingResponse(
        buffer, media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=rubricai_cohort_report.pdf"}
    )
