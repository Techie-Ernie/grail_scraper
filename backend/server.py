from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pymupdf
from backend.scraper import HolyGrailScraper
import glob 
import asyncio
from collections import Counter
import re
from sqlalchemy.orm import Session
from sqlalchemy import select
from db.engine import engine
from db.models import Question, Subtopic
from backend.syllabus import extract_clean_body_text, save_syllabus_text
from pathlib import Path
from typing import Any, Dict, Optional
from threading import Lock
from fastapi import HTTPException

app = FastAPI()

# Enable CORS for frontend connection
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ScrapedData(BaseModel):
    text: str

class AIResult(BaseModel):
    result: str

class QuestionContext(BaseModel):
    year: int
    subject: str
    category: str
    question_type: str
    source_link: str
    document_name: str

class AIResultRequest(BaseModel):
    result: Dict[str, Any]
    context: Optional[QuestionContext] = None

class SubtopicCreate(BaseModel):
    subject: str
    code: str
    title: str

class SubtopicBulkCreate(BaseModel):
    subject: str
    subtopics: list[Dict[str, str]]

class ScraperConfig(BaseModel):
    category: str = "GCE 'A' Levels"
    subject: str = "H2 Economics"
    year: Optional[int] = None
    document_type: str = "Exam Papers"
    pages: int = 3
    subject_label: Optional[str] = None

_context_lock = Lock()
_current_context: Optional[QuestionContext] = None
_scraper_config_lock = Lock()
_scraper_config = ScraperConfig()

SUBJECT_CODE_MAP = {
    "Economics (Syllabus 9750)": "H2 Economics",
    "Economics (9750)": "H2 Economics",
    "Economics": "H2 Economics",
}

SUBJECT_LABEL_CANONICAL = {
    "Economics": "Economics (Syllabus 9750)",
    "Economics (9750)": "Economics (Syllabus 9750)",
    "Economics (Syllabus 9750)": "Economics (Syllabus 9750)",
}

def normalize_subject_label(subject: str) -> str:
    cleaned = " ".join(subject.split())
    canonical = SUBJECT_LABEL_CANONICAL.get(cleaned)
    if canonical:
        return canonical
    if "(" in cleaned and "Syllabus" not in cleaned:
        cleaned = cleaned.replace("(", "(Syllabus ")
    return cleaned

def derive_scraper_subject(subject: str) -> str:
    subject = normalize_subject_label(subject)
    mapped = SUBJECT_CODE_MAP.get(subject)
    if mapped:
        return mapped
    if "(Syllabus" in subject:
        base = subject.split(" (", 1)[0].strip()
        if base:
            return f"H2 {base}"
    return subject



def resolve_source_link(document_name: str, config: ScraperConfig) -> str:
    scraper_subject = derive_scraper_subject(config.subject)
    scraper = HolyGrailScraper(
        config.category,
        scraper_subject,
        config.year,
        config.document_type,
        pages=config.pages,
    )
    scraper._ensure_documents_cached()
    target = document_name.strip()
    for doc in scraper.documents:
        name = (doc.get("document_name") or "").strip()
        lowered = name.replace(" ", "").lower()
        if any(token in lowered for token in ("markscheme", "answerkey", "answersheet", "suggestedanswers", "examinersreport")):
            continue
        if name == target:
            return doc.get("source_link") or ""
    return ""

def normalize_year(year_value: Optional[str]) -> int:
    if year_value is None:
        return 0
    try:
        return int(year_value)
    except ValueError:
        return 0

def safe_subject_name(subject: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in subject.strip()) or "unknown"

def normalize_category(category: Optional[str]) -> Optional[str]:
    if not category:
        return category
    normalized = category.strip()
    if normalized == 'GCE "A" Levels':
        return "GCE 'A' Levels"
    return normalized

def find_question_papers(subject: str) -> list[str]:
    subject_dir = safe_subject_name(subject)
    base_dir = f"/home/ernie/grail_scraper/documents/{subject_dir}"
    files = glob.glob(f"{base_dir}/question_paper/*.pdf")
    if not files:
        files = glob.glob(f"{base_dir}/question_papers/*.pdf")
    if not files:
        files = glob.glob("/home/ernie/grail_scraper/documents/*/question_paper/*.pdf")
    if not files:
        files = glob.glob("/home/ernie/grail_scraper/documents/*/question_papers/*.pdf")
    return files

def ensure_question_papers(config: ScraperConfig) -> list[str]:
    subject_label = normalize_subject_label(config.subject_label or config.subject)
    files = find_question_papers(subject_label)
    if files:
        return files
    scraper_subject = derive_scraper_subject(config.subject)
    scraper = HolyGrailScraper(
        config.category,
        scraper_subject,
        config.year,
        config.document_type,
        pages=config.pages,
    )
    try:
        documents = asyncio.run(scraper.get_documents())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            documents = loop.run_until_complete(scraper.get_documents())
        finally:
            loop.close()
    except Exception as exc:
        print(f"Scraper error: {type(exc).__name__}: {exc}")
        return []
    if documents:
        scraper.download_documents(
            documents,
            download_root="/home/ernie/grail_scraper/documents",
            subject_label=subject_label,
        )
    return find_question_papers(subject_label)

def insert_question(data: dict):
    if "subject" in data and data.get("subject"):
        data["subject"] = normalize_subject_label(data.get("subject"))
    if "category" in data:
        data["category"] = normalize_category(data.get("category"))
    with Session(engine) as session:
        existing = (
            session.query(Question)
            .filter(
                Question.subject == data.get("subject"),
                Question.year == data.get("year"),
                Question.question_text == data.get("question_text"),
            )
            .first()
        )
        if existing:
            existing.question_type = data.get("question_type", existing.question_type)
            existing.category = data.get("category", existing.category)
            existing.chapter = data.get("chapter", existing.chapter)
            existing.marks = data.get("marks", existing.marks)
            existing.document_name = data.get("document_name", existing.document_name)
            existing.source_link = data.get("source_link", existing.source_link)
            existing.answer_link = data.get("answer_link", existing.answer_link)
        else:
            q = Question(**data)
            session.add(q)
        session.commit()

def list_subtopics(subject: Optional[str] = None):
    with Session(engine) as session:
        query = session.query(Subtopic)
        if subject:
            query = query.filter(Subtopic.subject == normalize_subject_label(subject))
        query = query.order_by(Subtopic.code.asc())
        return [
            {"id": s.id, "subject": s.subject, "code": s.code, "title": s.title}
            for s in query.all()
        ]

def create_subtopic(data: SubtopicCreate):
    payload = data.model_dump() if hasattr(data, "model_dump") else data.dict()
    if payload.get("subject"):
        payload["subject"] = normalize_subject_label(payload["subject"])
    with Session(engine) as session:
        subtopic = Subtopic(**payload)
        session.add(subtopic)
        session.commit()
        session.refresh(subtopic)
        return {"id": subtopic.id, "subject": subtopic.subject, "code": subtopic.code, "title": subtopic.title}

def create_subtopics_bulk(payload: SubtopicBulkCreate):
    subject = normalize_subject_label(payload.subject)
    with Session(engine) as session:
        existing = {
            row[0]
            for row in session.query(Subtopic.code).filter(Subtopic.subject == subject).all()
        }
        created = 0
        seen = set(existing)
        for item in payload.subtopics:
            code = item.get("code")
            title = item.get("title")
            if not code or not title or code in seen:
                continue
            session.add(Subtopic(subject=subject, code=code, title=title))
            created += 1
            seen.add(code)
        session.commit()
    return {"created": created}

def set_current_context(context: QuestionContext) -> None:
    global _current_context
    with _context_lock:
        _current_context = context

def get_current_context() -> Optional[QuestionContext]:
    with _context_lock:
        return _current_context

def refresh_context_from_scraper() -> QuestionContext:
    with _scraper_config_lock:
        config = _scraper_config
    scraper = HolyGrailScraper(
        config.category,
        config.subject,
        config.year,
        config.document_type,
        pages=config.pages,
    )
    raw_context = scraper.get_scraper_context()
    if not isinstance(raw_context, dict):
        raise HTTPException(status_code=500, detail="Scraper context must be a dict.")
    if "question_type" not in raw_context:
        raw_context["question_type"] = "exam"
    if raw_context.get("year") is None:
        raw_context["year"] = 0
    if not raw_context.get("document_name"):
        raise HTTPException(status_code=500, detail="Scraper context missing document_name.")
    try:
        context = QuestionContext(**raw_context)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Invalid scraper context: {exc}") from exc
    set_current_context(context)
    return context


@app.get("/test")
def test_connection():
    return {"status": "connected", "message": "FastAPI backend is running!"}

@app.get("/data")
def get_data():
    with _scraper_config_lock:
        config = _scraper_config
    files = ensure_question_papers(config)
    if not files:
        raise HTTPException(status_code=404, detail="No question papers found for this subject.")
    target_file = sorted(files)[0]
    syllabus = "/home/ernie/grail_scraper/syllabi/econs.txt"
    with open(syllabus, 'r') as f:
        syllabus_text = f.read()
    prompts = ["Syllabus: " + syllabus_text + "Text: \n"]
    model_prompt = ""
    doc = pymupdf.open(target_file)
    for page in doc:
        model_prompt += str(page.get_text()).replace('\n', ' ')
        model_prompt = re.sub(r'(\.\s*)\n\[(\d+)\]', r'\1 [\2]', model_prompt) # pre-merge lines with the marks
    print(model_prompt)
    prompts.append(model_prompt)
    document_name = Path(target_file).stem
    source_link = resolve_source_link(document_name, config)
    context = QuestionContext(
        year=normalize_year(config.year),
        subject=config.subject_label or config.subject,
        category=config.category,
        question_type="exam",
        source_link=source_link,
        document_name=document_name,
    )
    set_current_context(context)
    context_payload = context.model_dump() if hasattr(context, "model_dump") else context.dict()
    return {"text": str(prompts), "context": context_payload}

@app.post("/data")
def receive_data(data: ScrapedData):
    print("Received data:", data.text)
    return {"status": "ok"}

@app.post("/context")
def receive_context(context: QuestionContext):
    if context.category:
        context.category = normalize_category(context.category)  # type: ignore[assignment]
    if context.subject:
        context.subject = normalize_subject_label(context.subject)  # type: ignore[assignment]
    set_current_context(context)
    return {"status": "ok"}

@app.post("/scraper/config")
def set_scraper_config(config: ScraperConfig):
    global _scraper_config
    if config.subject:
        config.subject = normalize_subject_label(config.subject)  # type: ignore[assignment]
    if config.subject_label:
        config.subject_label = normalize_subject_label(config.subject_label)  # type: ignore[assignment]
    if config.category:
        config.category = normalize_category(config.category)  # type: ignore[assignment]
    with _scraper_config_lock:
        _scraper_config = config
    return {"status": "ok", "config": config}

@app.get("/scraper/config")
def get_scraper_config():
    with _scraper_config_lock:
        config = _scraper_config
    return {"config": config}

@app.get("/context")
def read_context():
    context = get_current_context()
    if not context:
        return {"status": "empty"}
    return {"status": "ok", "context": context}

@app.get("/subtopics")
def get_subtopics(subject: Optional[str] = None):
    return {"subtopics": list_subtopics(subject)}

@app.post("/subtopics")
def add_subtopic(subtopic: SubtopicCreate):
    return {"subtopic": create_subtopic(subtopic)}

@app.post("/subtopics/bulk")
def add_subtopics_bulk(subtopics: SubtopicBulkCreate):
    return create_subtopics_bulk(subtopics)

@app.get("/subjects")
def get_subjects():
    with Session(engine) as session:
        rows = session.execute(select(Subtopic.subject).distinct()).all()
    subjects = sorted({normalize_subject_label(row[0]) for row in rows if row[0]})
    return {"subjects": subjects}

@app.get("/questions")
def get_questions(
    subject: Optional[str] = None,
    year: Optional[str] = None,
    category: Optional[str] = None,
    subtopic: Optional[str] = None,
):
    def normalize_filter(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value or value.lower() in {"all", "any"}:
            return None
        return value

    subject = normalize_filter(subject)
    category = normalize_category(normalize_filter(category))
    subtopic = normalize_filter(subtopic)
    if subject:
        subject = normalize_subject_label(subject)
    year_value: Optional[int] = None
    if year is not None:
        year = year.strip()
        if year and year.lower() not in {"all", "any"}:
            try:
                year_value = int(year)
            except ValueError:
                year_value = None

    with Session(engine) as session:
        query = session.query(Question)
        if subject:
            query = query.filter(Question.subject == subject)
        if year_value is not None:
            query = query.filter(Question.year == year_value)
        if category:
            query = query.filter(Question.category == category)
        if subtopic:
            query = query.filter(Question.chapter.like(f"{subtopic} %"))
        query = query.order_by(Question.year.desc(), Question.id.desc()).limit(200)
        results = [
            {
                "id": q.id,
                "year": q.year,
                "subject": q.subject,
                "category": q.category,
                "question_type": q.question_type,
                "chapter": q.chapter,
                "question_text": q.question_text,
                "marks": q.marks,
                "source_link": q.source_link,
                "document_name": q.document_name
            }
            for q in query.all()
        ]
    return {"questions": results}

@app.get("/questions/filters")
def get_question_filters():
    with Session(engine) as session:
        subjects = sorted({
            row[0] for row in session.execute(select(Question.subject).distinct()).all() if row[0]
        })
        categories = sorted({
            row[0] for row in session.execute(select(Question.category).distinct()).all() if row[0]
        })
        years = sorted({
            row[0] for row in session.execute(select(Question.year).distinct()).all() if row[0]
        }, reverse=True)
    return {"subjects": subjects, "categories": categories, "years": years}

@app.post("/syllabus/extract")
async def extract_syllabus(
    subject: str = Form(...),
    file: UploadFile = File(...),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    data = await file.read()
    temp_dir = Path("/home/ernie/grail_scraper/tmp")
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / file.filename
    temp_path.write_bytes(data)

    text = extract_clean_body_text(str(temp_path))

    safe_name = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in subject.strip())
    output_path = Path(f"/home/ernie/grail_scraper/syllabi/{safe_name}.txt")
    save_syllabus_text(text, output_path)

    return {"subject": subject, "text": text, "path": str(output_path)}

@app.post("/ai-result")
def receive_ai_result(payload: AIResultRequest):
    try:
        context = payload.context or get_current_context()
        if not context:
            context = refresh_context_from_scraper()
        if not context or not context.document_name:
            raise HTTPException(status_code=400, detail="Missing QuestionContext")
        data = payload.result
        # parse the exam-style questions 
        print("AI payload keys:", list(data.keys()) if isinstance(data, dict) else type(data))
        print("Context:", context)
        for row in data.get("exam", []):
            print("Exam row:", row)
            data_json = {
                "year": context.year,
                "subject": context.subject,
                "category": context.category,
                "question_type": "exam",
                "source_link": context.source_link,
                "document_name": context.document_name,
                "chapter": row["chapter"],
                "question_text": row["question"],
                "marks": row["marks"],
            }
            insert_question(data_json)
        for row in data.get("understanding", []):
            print("Understanding row:", row)
            data_json = {
                "year": context.year,
                "subject": context.subject,
                "category": context.category,
                "question_type": "understanding",
                "source_link": context.source_link,
                "document_name": context.document_name,
                "chapter": row["chapter"],
                "question_text": row["question"],
                "marks": None,
            }
            insert_question(data_json)
        return {"status": "received"}
    except HTTPException:
        raise
    except Exception as exc:
        error_message = f"{type(exc).__name__}: {exc}"
        print("AI result error:", error_message)
        raise HTTPException(status_code=500, detail=error_message)
