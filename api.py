# api.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from rag_pipeline import RAGPipeline
import psycopg2
import hashlib
import pandas as pd
from typing import List
from fastapi.middleware.cors import CORSMiddleware
# --- DB CONFIG ---
DB_PARAMS = {
    "dbname": "postgres",
    "user": "postgres",
    "password": "123",
    "host": "localhost",
    "port": "5432"
}

def get_db_connection():
    return psycopg2.connect(**DB_PARAMS)

def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

# --- FastAPI ---
app = FastAPI()
rag = RAGPipeline("pdfs")  # Load PDFs once


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------
# MODELS
# ---------------------------
class AuthRequest(BaseModel):
    username: str
    password: str

class SignupRequest(AuthRequest):
    role: str  # "student" or "instructor"

class ExamRequest(BaseModel):
    topic: str
    mcq_count: int = 3
    essay_count: int = 2
    difficulty: str = "Beginner"
    created_by: int

class SubmissionRequest(BaseModel):
    exam_id: int
    student_id: int
    student_answers: str

class GradeRequest(BaseModel):
    submission_id: int

# ---------------------------
# AUTH
# ---------------------------
@app.post("/signup")
def signup(req: SignupRequest):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                    (req.username, hash_password(req.password), req.role))
        conn.commit()
        return {"message": "User created successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cur.close()
        conn.close()

@app.post("/login")
def login(req: AuthRequest):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, username, role FROM users WHERE username=%s AND password=%s",
                (req.username, hash_password(req.password)))
    user = cur.fetchone()
    cur.close()
    conn.close()
    if user:
        return {"id": user[0], "username": user[1], "role": user[2]}
    else:
        raise HTTPException(status_code=401, detail="Invalid credentials")

# ---------------------------
# EXAM GENERATION
# ---------------------------
@app.post("/generate_exam")
def generate_exam(req: ExamRequest):
    try:
        exam_text, sources = rag.query(req.topic, req.mcq_count, req.essay_count, req.difficulty, "Instructor Mode")
        
        # Save exam
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO exams (topic, content, difficulty, created_by) VALUES (%s,%s,%s,%s) RETURNING id",
            (req.topic, exam_text, req.difficulty, req.created_by)
        )
        exam_id = cur.fetchone()[0]
        conn.commit()

        # Assign to all students
        cur.execute("SELECT id FROM users WHERE role='student'")
        students = cur.fetchall()
        for s_id, in students:
            cur.execute(
                "INSERT INTO exam_assignments (exam_id, student_id) VALUES (%s,%s)",
                (exam_id, s_id)
            )
        conn.commit()
        cur.close()
        conn.close()

        return {"exam_id": exam_id, "exam_content": exam_text, "sources": list(sources)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------
# STUDENT SUBMISSION
# ---------------------------
@app.get("/exams/{student_id}")
def get_exams(student_id: int):
    conn = get_db_connection()
    df = pd.read_sql("""
        SELECT e.id, e.topic, e.difficulty, ea.status
        FROM exams e
        JOIN exam_assignments ea ON e.id = ea.exam_id
        WHERE ea.student_id = %s
    """, conn, params=(student_id,))
    conn.close()
    return df.to_dict(orient="records")
@app.get("/submissions")
def get_submissions():
    conn = get_db_connection()
    try:
        query = """
        SELECT s.id, s.exam_id, s.student_id, 
               u.username, s.numerical_score, s.submitted_at
        FROM submissions s
        JOIN users u ON s.student_id = u.id
        ORDER BY s.submitted_at DESC
        """
        df = pd.read_sql(query, conn)
        return df.to_dict(orient="records")
    finally:
        conn.close()

# ---------------------------
# AUTO-GRADING
# ---------------------------
@app.post("/grade_submission")
def grade_submission(req: GradeRequest):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Fetch submission and exam content
        cur.execute("SELECT student_answers, exam_id FROM submissions WHERE id=%s", (req.submission_id,))
        result = cur.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="Submission not found")
        student_answers, exam_id = result
        cur.execute("SELECT content FROM exams WHERE id=%s", (exam_id,))
        exam_content = cur.fetchone()[0]

        # Call RAGPipeline grader
        res = rag.grade_submission(exam_content, student_answers)

        # Extract numeric score
        import re
        score_match = re.search(r"(\d+)/100", res) or re.search(r"Score:\s*(\d+)", res, re.I)
        numeric_score = int(score_match.group(1)) if score_match else 0

        # Update DB
        cur.execute("UPDATE submissions SET ai_feedback=%s, numerical_score=%s WHERE id=%s",
                    (res, numeric_score, req.submission_id))
        conn.commit()
        return {"feedback": res, "score": numeric_score}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); conn.close()
@app.post("/submit_exam")
def submit_exam(req: SubmissionRequest):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO submissions (exam_id, student_id, student_answers) VALUES (%s,%s,%s) RETURNING id",
            (req.exam_id, req.student_id, req.student_answers)
        )
        sub_id = cur.fetchone()[0]
        conn.commit()
        return {"submission_id": sub_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

# ---------------------------
# ANALYTICS (Instructor)
# ---------------------------
