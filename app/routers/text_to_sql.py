import json

from fastapi import APIRouter, HTTPException

from app.db.connection import get_db_connection
from app.services.txt_sql import supabase, generate_sql, execute_sql, QuestionRequest, SQLResponse

router = APIRouter(prefix="/instructors", tags=["instructors"])


@router.post("/ask", response_model=SQLResponse)
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
