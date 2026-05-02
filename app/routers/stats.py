import json

from fastapi import APIRouter, HTTPException
from app.core.config import supabase

from app.db.connection import get_db_connection

router = APIRouter(prefix="/instructors", tags=["instructors"])
STUDENT_SUBJECTS = ["math", "physics", "chemistry", "biology", "programming", "english"]

def _fetch_students_via_supabase():
    response = supabase.table("students").select("*").execute()
    err = getattr(response, "error", None)
    if err:
        # supabase-py can return error objects instead of raising
        raise RuntimeError(getattr(err, "message", None) or str(err))
    return response.data or []

def _fetch_students_via_db():
    # Fallback when Supabase REST is unreachable; uses direct DB connection.
    from psycopg2.extras import RealDictCursor

    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    student_id,
                    first_name,
                    grade_level,
                    math,
                    physics,
                    chemistry,
                    biology,
                    programming,
                    english,
                    total_percent
                FROM students
                """
            )
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

@router.get("/instructor/students/analytics")
def get_students_analytics():
    """Aggregated stats for the Students management page: averages, min, max per subject, top/bottom by total_percent."""
    try:
        # Try Supabase REST first, fallback to direct DB if it fails.
        try:
            rows = _fetch_students_via_supabase()
        except Exception as supa_err:
            try:
                rows = _fetch_students_via_db()
            except Exception as db_err:
                raise HTTPException(
                    status_code=500,
                    detail=f"Analytics fetch failed. Supabase error: {supa_err}. DB error: {db_err}",
                )
        if not rows:
            return {
                "total_students": 0,
                "averages": {s: None for s in STUDENT_SUBJECTS},
                "averages_total": None,
                "min_max": {s: {"min": None, "max": None} for s in STUDENT_SUBJECTS},
                "total_percent_min_max": {"min": None, "max": None},
                "top_5": [],
                "bottom_5": [],
                "by_grade": {},
                "subject_details": {s: {"top_5": [], "bottom_5": []} for s in STUDENT_SUBJECTS},
            }

        def safe_float(v):
            if v is None: return None
            try: return float(v)
            except (TypeError, ValueError): return None

        averages = {}
        min_max = {}
        subject_details = {}
        for subj in STUDENT_SUBJECTS:
            vals = [
                {"student_id": r.get("student_id"), "first_name": r.get("first_name"), "score": safe_float(r.get(subj))}
                for r in rows if safe_float(r.get(subj)) is not None
            ]
            scores = [v["score"] for v in vals]
            averages[subj] = round(sum(scores) / len(scores), 2) if scores else None
            min_max[subj] = {"min": min(scores) if scores else None, "max": max(scores) if scores else None}
            
            # Subject specific top/bottom
            sorted_subj = sorted(vals, key=lambda x: x["score"], reverse=True)
            subject_details[subj] = {
                "top_5": sorted_subj[:5],
                "bottom_5": sorted_subj[-5:][::-1]
            }

        total_vals = [safe_float(r.get("total_percent")) for r in rows if safe_float(r.get("total_percent")) is not None]
        averages_total = round(sum(total_vals) / len(total_vals), 2) if total_vals else None
        total_percent_min_max = {"min": min(total_vals) if total_vals else None, "max": max(total_vals) if total_vals else None}

        sorted_by_total = sorted(
            [r for r in rows if safe_float(r.get("total_percent")) is not None],
            key=lambda r: safe_float(r.get("total_percent")) or 0,
            reverse=True,
        )
        top_5 = [{"student_id": r.get("student_id"), "first_name": r.get("first_name"), "total_percent": safe_float(r.get("total_percent"))} for r in sorted_by_total[:5]]
        bottom_5 = [{"student_id": r.get("student_id"), "first_name": r.get("first_name"), "total_percent": safe_float(r.get("total_percent"))} for r in sorted_by_total[-5:][::-1]]

        by_grade = {}
        for r in rows:
            g = r.get("grade_level")
            if g is not None:
                g = str(g)
                if g not in by_grade:
                    by_grade[g] = {"count": 0, "avg_total": [], "student_ids": []}
                by_grade[g]["count"] += 1
                t = safe_float(r.get("total_percent"))
                if t is not None:
                    by_grade[g]["avg_total"].append(t)
                by_grade[g]["student_ids"].append(r.get("student_id"))
        for g in by_grade:
            arr = by_grade[g]["avg_total"]
            by_grade[g]["avg_total"] = round(sum(arr) / len(arr), 2) if arr else None
            del by_grade[g]["student_ids"]

        return {
            "total_students": len(rows),
            "averages": averages,
            "averages_total": averages_total,
            "min_max": min_max,
            "total_percent_min_max": total_percent_min_max,
            "top_5": top_5,
            "bottom_5": bottom_5,
            "by_grade": by_grade,
            "subject_details": subject_details,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
