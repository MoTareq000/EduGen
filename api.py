
# api.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from rag_pipeline import RAGPipeline
import psycopg2
import hashlib
import pandas as pd
from typing import List
from fastapi.middleware.cors import CORSMiddleware
from txt_sql import supabase, generate_sql, execute_sql, QuestionRequest, SQLResponse
# --- Auth Helpers ---
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
    try:
        data = {
            "username": req.username,
            "password": hash_password(req.password),
            "role": req.role
        }
        supabase.table("users").insert(data).execute()
        return {"message": "User created successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/login")
def login(req: AuthRequest):
    try:
        response = supabase.table("users").select("id, username, role").eq("username", req.username).eq("password", hash_password(req.password)).execute()
        user = response.data[0] if response.data else None
        if user:
            return {"id": user['id'], "username": user['username'], "role": user['role']}
        else:
            raise HTTPException(status_code=401, detail="Invalid credentials")
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------
# EXAM GENERATION
# ---------------------------
@app.post("/generate_exam")
def generate_exam(req: ExamRequest):
    try:
        exam_text, sources = rag.query(req.topic, req.mcq_count, req.essay_count, req.difficulty, "Instructor Mode")
        
        # Save exam
        exam_data = {
            "topic": req.topic,
            "content": exam_text,
            "difficulty": req.difficulty,
            "created_by": req.created_by
        }
        response = supabase.table("exams").insert(exam_data).execute()
        exam_id = response.data[0]['id']

        # Assign to all students
        students_response = supabase.table("users").select("id").eq("role", "student").execute()
        students = students_response.data
        
        assignments = [{"exam_id": exam_id, "student_id": s['id']} for s in students]
        if assignments:
            supabase.table("exam_assignments").insert(assignments).execute()

        return {"exam_id": exam_id, "exam_content": exam_text, "sources": list(sources)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------
# STUDENT SUBMISSION
# ---------------------------
@app.get("/exams/{student_id}")
def get_exams(student_id: int):
    try:
        # Using a join-like logic via Supabase or separate queries
        # If the schema has foreign keys, we can use select("*, exams(*)")
        response = supabase.table("exam_assignments").select("status, exams(id, topic, difficulty)").eq("student_id", student_id).execute()
        
        exams_list = []
        for item in response.data:
            exam = item['exams']
            exams_list.append({
                "id": exam['id'],
                "topic": exam['topic'],
                "difficulty": exam['difficulty'],
                "status": item['status']
            })
        return exams_list
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/submissions")
def get_submissions():
    try:
        # Fetching submissions with student username
        response = supabase.table("submissions").select("id, exam_id, student_id, numerical_score, submitted_at, users(username)").order("submitted_at", desc=True).execute()
        
        results = []
        for s in response.data:
            results.append({
                "id": s['id'],
                "exam_id": s['exam_id'],
                "student_id": s['student_id'],
                "username": s['users']['username'] if s.get('users') else "Unknown",
                "numerical_score": s['numerical_score'],
                "submitted_at": s['submitted_at']
            })
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------
# AUTO-GRADING
# ---------------------------
@app.post("/grade_submission")
def grade_submission(req: GradeRequest):
    try:
        # Fetch submission
        sub_response = supabase.table("submissions").select("student_answers, exam_id").eq("id", req.submission_id).execute()
        if not sub_response.data:
            raise HTTPException(status_code=404, detail="Submission not found")
        student_answers = sub_response.data[0]['student_answers']
        exam_id = sub_response.data[0]['exam_id']

        # Fetch exam
        exam_response = supabase.table("exams").select("content").eq("id", exam_id).execute()
        exam_content = exam_response.data[0]['content']

        # Call RAGPipeline grader
        res = rag.grade_submission(exam_content, student_answers)

        # Extract numeric score
        import re
        score_match = re.search(r"(\d+)/100", res) or re.search(r"Score:\s*(\d+)", res, re.I)
        numeric_score = int(score_match.group(1)) if score_match else 0

        # Update DB
        supabase.table("submissions").update({
            "ai_feedback": res,
            "numerical_score": numeric_score
        }).eq("id", req.submission_id).execute()
        
        return {"feedback": res, "score": numeric_score}

    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/submit_exam")
def submit_exam(req: SubmissionRequest):
    try:
        data = {
            "exam_id": req.exam_id,
            "student_id": req.student_id,
            "student_answers": req.student_answers
        }
        response = supabase.table("submissions").insert(data).execute()
        sub_id = response.data[0]['id']
        return {"submission_id": sub_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------
# ANALYTICS (Instructor)
# ---------------------------


@app.get("/")
def home():
    return {
        "message": "Student Analytics LLM API",
        "endpoints": {
            "/ask": "POST - Ask questions about student data",
            "/students": "GET - Get all students",
            "/test": "GET - Test Supabase connection"
        }
    }

@app.get("/students")
def get_all_students():
    """Get all students from Supabase"""
    try:
        response = supabase.table('students').select("*").execute()
        return {"count": len(response.data), "students": response.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/test")
def test_connection():
    """Test Supabase connection"""
    try:
        supabase.table('students').select("count").execute()
        return {"status": "connected", "message": "Supabase connection successful"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Connection failed: {str(e)}")

@app.post("/ask", response_model=SQLResponse)
def ask_question(req: QuestionRequest):
    """
    Ask a question about student data in natural language.

    Example questions:
    - "Who scored above 80?"
    - "What is the average score in Math?"
    - "Show me students who failed (below 60)"
    - "Who has the most attempts?"
    - "List students in grade 10"
    """
    try:
        sql = generate_sql(req.question)
        results = execute_sql(sql)
        if isinstance(results, dict) and "error" in results:
            return {"sql": sql, "results": None, "error": results["error"]}
        return {"sql": sql, "results": results, "error": None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
# open api.py and add a temporary comment
# updated on 21 Feb 2026