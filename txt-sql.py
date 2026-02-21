import os
from fastapi import HTTPException
from pydantic import BaseModel
from typing import Any, List, Optional
from groq import Groq
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()


# =========================
# CONFIGURATION
# =========================
CURRENT_MODEL = "openai/gpt-oss-120b"
GROQ_CLIENT = Groq(api_key=os.getenv("GROQ_API_KEY", ""))


# =========================
# Supabase Setup
# =========================
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# =========================
# Models
# =========================
class QuestionRequest(BaseModel):
    question: str

class SQLResponse(BaseModel):
    sql: str
    results: Optional[List[Any]]
    error: Optional[str] = None

# =========================
# Generate SQL
# =========================
def generate_sql(user_question: str) -> str:
    prompt = f"""
You are a SQL generator for PostgreSQL.
Database table: students(
    student_id SERIAL PRIMARY KEY,
    first_name VARCHAR(50),
    grade_level INT,
    subject VARCHAR(50),
    exam_score INT,
    attempts INT,
    last_exam_date DATE,
    weak_topic VARCHAR(50)
)

Sample data:
- Ali, grade 10, Math, score 75
- Sara, grade 11, Physics, score 62
- Omar, grade 12, Math, score 90

Generate a SELECT query ONLY for the following question:
Question: {user_question}

Rules:
- Respond ONLY with the SQL query, no explanations
- Use proper WHERE clauses for filtering
- Use ORDER BY when asking for top/bottom/best/worst
- Use COUNT, AVG, MAX, MIN for aggregations
- No markdown formatting, just plain SQL

Example queries:
- "Who scored above 80?" -> SELECT * FROM students WHERE exam_score > 80;
- "Average score in Math" -> SELECT AVG(exam_score) FROM students WHERE subject = 'Math';
"""
    try:
        chat_completion = GROQ_CLIENT.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=CURRENT_MODEL,
            temperature=0,
        )
        sql_query = chat_completion.choices[0].message.content.strip()
        
        # Clean up the SQL query
        sql_query = sql_query.replace("```sql", "").replace("```", "").strip()
        
        return sql_query
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating SQL: {str(e)}")

# =========================
# Execute SQL via Supabase
# =========================
def execute_sql(sql_query: str):
    try:
        # Remove semicolon - PostgreSQL EXECUTE doesn't expect it
        sql_query = sql_query.rstrip(';').strip()
        
        # Use Supabase RPC to execute raw SQL
        response = supabase.rpc('execute_sql', {'query': sql_query}).execute()
        
        # Handle empty results
        if response.data is None:
            return []
        
        return response.data
    except Exception as e:
        return {"error": str(e)}

#h        
