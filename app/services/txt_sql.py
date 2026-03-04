import os
from fastapi import HTTPException
from pydantic import BaseModel
from typing import Any, List, Optional
from groq import Groq
from dotenv import load_dotenv
from supabase import create_client, Client
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv()


# =========================
# CONFIGURATION
# =========================
CURRENT_MODEL = "openai/gpt-oss-120b"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY not found in environment variables")
GROQ_CLIENT = Groq(api_key=GROQ_API_KEY)
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY not found in environment variables")
GROQ_CLIENT = Groq(api_key=GROQ_API_KEY)


from app.core.config import supabase

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
    math INT,
    physics INT,
    chemistry INT,
    biology INT,
    programming INT,
    english INT,
    total_percent NUMERIC
)

Generate a SELECT query ONLY for the following question:
Question: {user_question}

Rules:
- Respond ONLY with the SQL query, no explanations
- Use proper WHERE clauses for filtering (e.g. math, physics, total_percent)
- Use ORDER BY when asking for top/bottom/best/worst
- Use COUNT, AVG, MAX, MIN for aggregations on numeric columns (math, physics, chemistry, biology, programming, english, total_percent)
- No markdown formatting, just plain SQL

Example queries:
- "Who scored above 80 in math?" -> SELECT * FROM students WHERE math > 80;
- "Average total percentage?" -> SELECT AVG(total_percent) FROM students;
- "Top 5 by total_percent" -> SELECT * FROM students ORDER BY total_percent DESC NULLS LAST LIMIT 5;
- "Students in grade 10" -> SELECT * FROM students WHERE grade_level = 10;
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
# Execute SQL: try Supabase RPC first (like before), fallback to DATABASE_URL if set
# =========================
def _serialize_row(row):
    """Make row values JSON-serializable (e.g. Decimal, date)."""
    def _serialize(v):
        if v is None or isinstance(v, (bool, str, int)):
            return v
        if isinstance(v, float):
            return v
        if hasattr(v, "__float__") and not isinstance(v, bool):
            return float(v)
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return str(v)
    return {k: _serialize(v) for k, v in row.items()}

def execute_sql(sql_query: str):
    """Run SELECT only. Uses Supabase RPC if available, else DATABASE_URL."""
    sql_query = sql_query.rstrip(';').strip()
    normalized = sql_query.upper().strip()
    if not normalized.startswith("SELECT"):
        return {"error": "Only SELECT queries are allowed."}

    # 1) Try Supabase RPC first (how it used to work – no DATABASE_URL needed)
    try:
        response = supabase.rpc("execute_sql", {"query": sql_query}).execute()
        if response.data is None:
            return []
        return response.data
    except Exception as rpc_err:
        err_msg = str(rpc_err)

    # 2) Fallback: run via direct DB connection if DATABASE_URL is set
    database_url = os.getenv("DATABASE_URL")
    if database_url and database_url.strip():
        try:
            conn = psycopg2.connect(database_url, sslmode="require")
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(sql_query)
            rows = cur.fetchall()
            cur.close()
            conn.close()
            return [_serialize_row(dict(r)) for r in rows]
        except Exception as e:
            return {"error": str(e)}

    # RPC failed and no DATABASE_URL: return the RPC error (e.g. "column X does not exist" or "function execute_sql does not exist")
    return {"error": err_msg}
