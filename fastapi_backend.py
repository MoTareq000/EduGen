import hashlib
import json
import os
import re
from datetime import datetime
from typing import Any, Literal

import psycopg2
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from rag_pipeline import RAGPipeline

load_dotenv()

app = FastAPI(title="Road Project Backend", version="1.0.0")

_rag: RAGPipeline | None = None


def get_rag() -> RAGPipeline:
    global _rag
    if _rag is None:
        try:
            _rag = RAGPipeline("pdfs")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"RAG initialization failed: {exc}")
    return _rag


def build_db_params() -> dict[str, Any]:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return {"dsn": database_url, "sslmode": "require"}

    project_ref = os.getenv("SUPABASE_PROJECT_REF")
    db_password = os.getenv("SUPABASE_DB_PASSWORD")
    db_user = os.getenv("SUPABASE_DB_USER", "postgres")
    db_name = os.getenv("SUPABASE_DB_NAME", "postgres")
    db_host = os.getenv("SUPABASE_DB_HOST") or (
        f"db.{project_ref}.supabase.co" if project_ref else None
    )
    db_port = os.getenv("SUPABASE_DB_PORT", "5432")

    if db_host and db_password:
        return {
            "dbname": db_name,
            "user": db_user,
            "password": db_password,
            "host": db_host,
            "port": db_port,
            "sslmode": "require",
        }

    raise RuntimeError(
        "Database is not configured. Set DATABASE_URL or SUPABASE_PROJECT_REF + SUPABASE_DB_PASSWORD."
    )


def get_db_connection():
    params = build_db_params()
    if "dsn" in params:
        return psycopg2.connect(params["dsn"], sslmode=params.get("sslmode", "require"))
    return psycopg2.connect(**params)


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def parse_json_blob(text: str | None):
    if not text:
        return None

    candidate = str(text).strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\s*```$", "", candidate)

    try:
        data = json.loads(candidate)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def parse_score_from_text(text: str | None) -> int:
    try:
        score_match = re.search(r"(\d+)/100", text or "") or re.search(
            r"Score:\s*(\d+)", text or "", re.I
        )
        score = int(score_match.group(1)) if score_match else 0
    except Exception:
        score = 0
    return max(0, min(100, score))


def ensure_runtime_schema():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        commands = [
            "CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, role TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS exams (id SERIAL PRIMARY KEY, topic TEXT NOT NULL, content TEXT NOT NULL, difficulty TEXT, created_by INTEGER REFERENCES users(id))",
            "CREATE TABLE IF NOT EXISTS submissions (id SERIAL PRIMARY KEY, exam_id INTEGER REFERENCES exams(id), student_id INTEGER REFERENCES users(id), student_answers TEXT, ai_feedback TEXT, numerical_score INTEGER, submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_provider TEXT",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_subject TEXT",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT",
            "ALTER TABLE exams ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'draft'",
            "ALTER TABLE exams ADD COLUMN IF NOT EXISTS due_at TIMESTAMP NULL",
            "ALTER TABLE exams ADD COLUMN IF NOT EXISTS published_at TIMESTAMP NULL",
            "ALTER TABLE exams ADD COLUMN IF NOT EXISTS rubric TEXT NULL",
            "ALTER TABLE exams ADD COLUMN IF NOT EXISTS source_refs TEXT NULL",
            "ALTER TABLE exams ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1",
            "ALTER TABLE submissions ADD COLUMN IF NOT EXISTS graded_by INTEGER NULL REFERENCES users(id)",
            "ALTER TABLE submissions ADD COLUMN IF NOT EXISTS graded_at TIMESTAMP NULL",
            "ALTER TABLE submissions ADD COLUMN IF NOT EXISTS grader_note TEXT NULL",
            "ALTER TABLE submissions ADD COLUMN IF NOT EXISTS score_breakdown TEXT NULL",
            "CREATE UNIQUE INDEX IF NOT EXISTS users_oauth_identity_uniq ON users(oauth_provider, oauth_subject)",
            "CREATE INDEX IF NOT EXISTS exams_created_by_idx ON exams(created_by)",
            "CREATE INDEX IF NOT EXISTS exams_status_due_idx ON exams(status, due_at)",
            "CREATE INDEX IF NOT EXISTS submissions_exam_student_idx ON submissions(exam_id, student_id)",
        ]
        for command in commands:
            cur.execute(command)
        conn.commit()
    finally:
        cur.close()
        conn.close()


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=6, max_length=200)
    role: Literal["student", "instructor"]


class LoginRequest(BaseModel):
    username: str
    password: str


class GenerateExamRequest(BaseModel):
    topic: str
    difficulty: str = "Beginner"
    mcq_count: int = Field(default=3, ge=1, le=20)
    essay_count: int = Field(default=2, ge=0, le=10)


class CreateExamRequest(BaseModel):
    instructor_id: int
    topic: str
    difficulty: str = "Beginner"
    content: str
    status: Literal["draft", "published", "archived"] = "draft"
    rubric: str | None = None
    due_at: datetime | None = None
    source_refs: list[str] = Field(default_factory=list)


class SubmitRequest(BaseModel):
    exam_id: int
    student_id: int
    answers: dict[str, Any] | str


class GradeRequest(BaseModel):
    submission_id: int
    instructor_id: int


@app.on_event("startup")
def on_startup():
    ensure_runtime_schema()


@app.get("/health")
def health():
    return {"status": "ok", "service": "fastapi-backend"}


@app.post("/auth/register")
def register(payload: RegisterRequest):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM users WHERE username=%s", (payload.username,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Username already exists")

        cur.execute(
            "INSERT INTO users (username, password, role) VALUES (%s, %s, %s) RETURNING id",
            (payload.username, hash_password(payload.password), payload.role),
        )
        user_id = cur.fetchone()[0]
        conn.commit()
        return {"id": user_id, "username": payload.username, "role": payload.role}
    finally:
        cur.close()
        conn.close()


@app.post("/auth/login")
def login(payload: LoginRequest):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, username, role FROM users WHERE username=%s AND password=%s",
            (payload.username, hash_password(payload.password)),
        )
        user = cur.fetchone()
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return {"id": user[0], "username": user[1], "role": user[2]}
    finally:
        cur.close()
        conn.close()


@app.post("/rag/generate")
def generate_exam(payload: GenerateExamRequest):
    rag = get_rag()
    text, sources = rag.query(
        payload.topic,
        mcq_count=payload.mcq_count,
        essay_count=payload.essay_count,
        difficulty=payload.difficulty,
        mode="Instructor Mode",
    )
    if isinstance(text, str) and text.startswith("Error calling AI:"):
        raise HTTPException(status_code=502, detail=text)
    return {"content": text, "sources": sorted(list(sources))}


@app.post("/exams")
def create_exam(payload: CreateExamRequest):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT role FROM users WHERE id=%s", (payload.instructor_id,))
        user_row = cur.fetchone()
        if not user_row:
            raise HTTPException(status_code=404, detail="Instructor not found")
        if user_row[0] != "instructor":
            raise HTTPException(status_code=403, detail="User is not an instructor")

        cur.execute(
            """
            INSERT INTO exams (topic, content, difficulty, created_by, status, due_at, published_at, rubric, source_refs, version)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                payload.topic,
                payload.content,
                payload.difficulty,
                payload.instructor_id,
                payload.status,
                payload.due_at,
                datetime.utcnow() if payload.status == "published" else None,
                payload.rubric,
                json.dumps(payload.source_refs, ensure_ascii=True),
                1,
            ),
        )
        exam_id = cur.fetchone()[0]
        conn.commit()
        return {"id": exam_id}
    finally:
        cur.close()
        conn.close()


@app.get("/exams")
def list_exams(status: Literal["draft", "published", "archived"] | None = None):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        if status:
            cur.execute(
                "SELECT id, topic, difficulty, status, due_at, created_by FROM exams WHERE status=%s ORDER BY id DESC",
                (status,),
            )
        else:
            cur.execute(
                "SELECT id, topic, difficulty, status, due_at, created_by FROM exams ORDER BY id DESC"
            )

        rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "topic": r[1],
                "difficulty": r[2],
                "status": r[3],
                "due_at": r[4],
                "created_by": r[5],
            }
            for r in rows
        ]
    finally:
        cur.close()
        conn.close()


@app.get("/exams/{exam_id}")
def get_exam(exam_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, topic, difficulty, content, status, due_at, rubric, source_refs FROM exams WHERE id=%s",
            (exam_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Exam not found")

        return {
            "id": row[0],
            "topic": row[1],
            "difficulty": row[2],
            "content": row[3],
            "parsed_content": parse_json_blob(row[3]),
            "status": row[4],
            "due_at": row[5],
            "rubric": row[6],
            "source_refs": json.loads(row[7]) if row[7] else [],
        }
    finally:
        cur.close()
        conn.close()


@app.post("/submissions")
def submit_exam(payload: SubmitRequest):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT due_at, status FROM exams WHERE id=%s", (payload.exam_id,))
        exam_row = cur.fetchone()
        if not exam_row:
            raise HTTPException(status_code=404, detail="Exam not found")
        due_at, status = exam_row
        if status != "published":
            raise HTTPException(status_code=400, detail="Exam is not published")
        if due_at and due_at <= datetime.utcnow():
            raise HTTPException(status_code=400, detail="Exam is closed")

        cur.execute(
            "SELECT id FROM submissions WHERE exam_id=%s AND student_id=%s",
            (payload.exam_id, payload.student_id),
        )
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Student already submitted this exam")

        answers_text = (
            payload.answers
            if isinstance(payload.answers, str)
            else json.dumps(payload.answers, ensure_ascii=True)
        )

        cur.execute(
            "INSERT INTO submissions (exam_id, student_id, student_answers) VALUES (%s,%s,%s) RETURNING id",
            (payload.exam_id, payload.student_id, answers_text),
        )
        submission_id = cur.fetchone()[0]
        conn.commit()
        return {"id": submission_id}
    finally:
        cur.close()
        conn.close()


@app.post("/submissions/grade")
def grade_submission(payload: GradeRequest):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT role FROM users WHERE id=%s", (payload.instructor_id,))
        instructor = cur.fetchone()
        if not instructor or instructor[0] != "instructor":
            raise HTTPException(status_code=403, detail="Only instructors can grade")

        cur.execute(
            """
            SELECT s.id, s.student_answers, e.content, e.rubric, e.created_by
            FROM submissions s
            JOIN exams e ON s.exam_id = e.id
            WHERE s.id = %s
            """,
            (payload.submission_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Submission not found")
        submission_id, student_answers, exam_content, rubric, exam_owner = row

        if exam_owner != payload.instructor_id:
            raise HTTPException(status_code=403, detail="Cannot grade submissions for another instructor")

        rag = get_rag()
        prompt_exam = f"RUBRIC:\n{rubric}\n\n{exam_content}" if rubric else exam_content
        ai_feedback = rag.grade_submission(prompt_exam, student_answers)
        if isinstance(ai_feedback, str) and ai_feedback.startswith("Grading Error:"):
            raise HTTPException(status_code=502, detail=ai_feedback)
        score = parse_score_from_text(ai_feedback)

        cur.execute(
            """
            UPDATE submissions
            SET ai_feedback=%s, numerical_score=%s, graded_by=%s, graded_at=CURRENT_TIMESTAMP
            WHERE id=%s
            """,
            (ai_feedback, score, payload.instructor_id, submission_id),
        )
        conn.commit()

        return {"submission_id": submission_id, "score": score, "feedback": ai_feedback}
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("fastapi_backend:app", host="0.0.0.0", port=8000, reload=True)
