# EduGen FastAPI Backend

This project now runs as a FastAPI backend for exam generation, exam delivery, submissions, and grading.

## What Changed

- Replaced interactive CLI `main.py` with a FastAPI runner.
- Uses `fastapi_backend.py` as the backend API.
- Keeps PostgreSQL/Supabase support and RAG-based generation/grading.

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
uvicorn fastapi_backend:app --host 0.0.0.0 --port 8000 --reload
```

## API Docs

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Frontend UI: `http://localhost:8000/`

## Core Endpoints

- `GET /health`
- `POST /auth/register`
- `POST /auth/login`
- `POST /rag/generate`
- `POST /exams`
- `GET /exams`
- `GET /exams/{exam_id}`
- `POST /submissions`
- `POST /submissions/grade`

## Notes

- The API starts even if DB startup checks fail, and exposes startup issues in `/health`.
- RAG initialization is lazy; it loads only when generation/grading endpoints are called.
