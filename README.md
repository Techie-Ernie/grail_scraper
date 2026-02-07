# Graili (grail_scraper)

Scrape exam PDFs from `grail.moe`, extract questions with `puter.ai.chat`, and store/search them in Postgres.

**What’s here**
- FastAPI backend (`backend/server.py`) + SQLAlchemy models (`db/models.py`)
- Playwright-based scraper/downloader (`backend/scraper.py`)
- React + Vite frontend (`frontend/`)

## Requirements
- Python 3.11+
- Node.js 18+
- Postgres (or set `DATABASE_URL` to your own DB)
- `wget` on PATH (used for downloads)

## Quickstart (local)
1. Backend
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium

export DATABASE_URL='postgresql+psycopg2://exam_user:password@localhost/exam_questions'
uvicorn backend.server:app --reload --port 8000
```

2. Frontend
```bash
npm -C frontend install
VITE_API_URL='http://localhost:8000' npm -C frontend run dev
```

Open `http://localhost:5173`.

## Usage Notes
- Pick a **Subject** before clicking **Scrape Documents** (the backend rejects scrapes without a subject selection).
- “Seed chapters from syllabus”: upload a syllabus PDF to extract and store subtopics for the selected subject.
- “Upload question documents”: upload your own PDFs; extracted questions are scoped to your browser session.
- Question search: use “Search questions” to filter by question text (space-separated terms, AND semantics).

## Config (env vars)
- `DATABASE_URL`: SQLAlchemy DB URL (default points at local Postgres).
- `CORS_ORIGINS`: comma-separated list for the frontend origin(s).
- `DOCUMENTS_ROOT`, `SYLLABI_DIR`, `TMP_DIR`: storage locations (default to `./documents`, `./syllabi`, `./tmp`).
- `SCRAPER_SUBJECT_PREFIX`: prefix used when deriving Grail subjects from canonical labels (default `H2`).
- `VITE_API_URL` (frontend): backend base URL.

## Data Layout
- Downloaded PDFs: `documents/<safe_subject>/{question_paper,answer_key}/`
- Temporary scrape runs: `tmp/scraped_docs/<run_id>/` (cleaned up after `/data` completes)
