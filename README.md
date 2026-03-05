# EduGen FastAPI Backend

This project now runs as a FastAPI backend for exam generation, exam delivery, submissions, and grading.

## What Changed

- Replaced interactive CLI `main.py` with a FastAPI runner.
- Refactored backend into a modular `app/` package for team development.
- `fastapi_backend.py` is now a compatibility shim that re-exports `app.main:app`.
- Keeps PostgreSQL/Supabase support and RAG-based generation/grading.

## Project Structure

```text
app/
  core/        # config/env
  db/          # db connection + schema bootstrap
  services/    # oauth, rag, grading, audit, helpers
  routers/     # endpoint groups (auth/exams/submissions/etc.)
  schemas.py   # pydantic request models
  main.py      # FastAPI app assembly
fastapi_backend.py  # compatibility shim
main.py             # uvicorn launcher
```

## Tech Stack

- FastAPI + Uvicorn
- PostgreSQL (`psycopg2-binary`)
- LangChain + FAISS + HuggingFace embeddings
- Groq API for exam generation/grading

## Environment Variables

Create `.env` with:

```env
GROQ_API_KEY=...
GROQ_MODEL=llama-3.3-70b-versatile

DATABASE_URL=postgresql://...
# OR use SUPABASE_* values:
SUPABASE_PROJECT_REF=
SUPABASE_DB_PASSWORD=
SUPABASE_DB_USER=postgres
SUPABASE_DB_NAME=postgres
SUPABASE_DB_HOST=
SUPABASE_DB_PORT=5432

HOST=0.0.0.0
PORT=8000
RELOAD=true

APP_BASE_URL=http://localhost:8000
OAUTH_STATE_SECRET=replace-with-a-long-random-secret
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
```

## Install

```bash
pip install -r requirements.txt
```

## Initialize Database

```bash
python setup_db.py
```

## Run API

```bash
python main.py
```

Or directly:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## API Docs

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Frontend UI: `http://localhost:8000/`

## OAuth Redirect URLs

- Google callback: `http://localhost:8000/auth/oauth/google/callback`
- GitHub callback: `http://localhost:8000/auth/oauth/github/callback`

## Core Endpoints

- `GET /health`
- `POST /auth/register`
- `POST /auth/login`
- `POST /rag/generate`
- `GET /rag/pdfs`
- `POST /rag/pdfs/upload` (instructor-only)
- `POST /exams`
- `GET /exams`
- `GET /exams/{exam_id}`
- `POST /submissions`
- `POST /submissions/grade`
- `GET /submissions/by-exam?exam_id=...&student_id=...`
- `GET /submissions/students/{student_id}`

## Notes

- The API starts even if DB startup checks fail, and exposes startup issues in `/health`.
- RAG initialization is lazy; it loads only when generation/grading endpoints are called.
- Instructors can upload PDFs from the frontend under `Generate Exam` to update the knowledge base.
