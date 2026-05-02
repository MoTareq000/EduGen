import json

from fastapi import APIRouter, HTTPException

from app.db.connection import get_db_connection

router = APIRouter(prefix="/instructors", tags=["instructors"])


@router.get("/{instructor_id}/submissions")
def list_instructor_submissions(instructor_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT role FROM users WHERE id=%s", (instructor_id,))
        instructor = cur.fetchone()
        if not instructor:
            raise HTTPException(status_code=404, detail="Instructor not found")
        if instructor[0] != "instructor":
            raise HTTPException(status_code=403, detail="User is not an instructor")

        cur.execute(
            """
            SELECT s.id, s.exam_id, e.topic, s.student_id, u.username, s.student_answers,
                   e.content, e.rubric, s.submitted_at, s.numerical_score, s.ai_feedback,
                   s.score_breakdown, s.grader_note,
                   ps.id, ps.focus_score_final, ps.total_alerts, ps.high_alerts, ps.medium_alerts,
                   ps.invalidated, ps.invalidate_reason
            FROM submissions s
            JOIN exams e ON s.exam_id = e.id
            JOIN users u ON s.student_id = u.id
            LEFT JOIN proctor_sessions ps ON ps.submission_id = s.id
            WHERE e.created_by = %s
            ORDER BY s.id DESC
            """,
            (instructor_id,),
        )
        rows = cur.fetchall()
        return [
            {
                "submission_id": r[0],
                "exam_id": r[1],
                "exam_topic": r[2],
                "student_id": r[3],
                "student_username": r[4],
                "student_answers": r[5],
                "exam_content": r[6],
                "rubric": r[7],
                "submitted_at": r[8],
                "numerical_score": r[9],
                "ai_feedback": r[10],
                "score_breakdown": json.loads(r[11]) if r[11] else None,
                "grader_note": r[12],
                "proctor_session_id": str(r[13]) if r[13] else None,
                "proctor_focus_score_final": float(r[14]) if r[14] is not None else None,
                "proctor_total_alerts": r[15],
                "proctor_high_alerts": r[16],
                "proctor_medium_alerts": r[17],
                "proctor_invalidated": r[18],
                "proctor_invalidate_reason": r[19],
            }
            for r in rows
        ]
    finally:
        cur.close()
        conn.close()


@router.get("/{instructor_id}/submissions/{submission_id}")
def get_instructor_submission_detail(instructor_id: int, submission_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT role FROM users WHERE id=%s", (instructor_id,))
        instructor = cur.fetchone()
        if not instructor:
            raise HTTPException(status_code=404, detail="Instructor not found")
        if instructor[0] != "instructor":
            raise HTTPException(status_code=403, detail="User is not an instructor")

        cur.execute(
            """
            SELECT s.id, s.exam_id, e.topic, s.student_id, u.username, s.student_answers,
                   e.content, e.rubric, s.submitted_at, s.numerical_score, s.ai_feedback,
                   s.score_breakdown, s.grader_note,
                   ps.id, ps.focus_score_final, ps.total_alerts, ps.high_alerts, ps.medium_alerts,
                   ps.invalidated, ps.invalidate_reason
            FROM submissions s
            JOIN exams e ON s.exam_id = e.id
            JOIN users u ON s.student_id = u.id
            LEFT JOIN proctor_sessions ps ON ps.submission_id = s.id
            WHERE e.created_by = %s AND s.id = %s
            """,
            (instructor_id, submission_id),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Submission not found")

        return {
            "submission_id": row[0],
            "exam_id": row[1],
            "exam_topic": row[2],
            "student_id": row[3],
            "student_username": row[4],
            "student_answers": row[5],
            "exam_content": row[6],
            "rubric": row[7],
            "submitted_at": row[8],
            "numerical_score": row[9],
            "ai_feedback": row[10],
            "score_breakdown": json.loads(row[11]) if row[11] else None,
            "grader_note": row[12],
            "proctor_session_id": str(row[13]) if row[13] else None,
            "proctor_focus_score_final": float(row[14]) if row[14] is not None else None,
            "proctor_total_alerts": row[15],
            "proctor_high_alerts": row[16],
            "proctor_medium_alerts": row[17],
            "proctor_invalidated": row[18],
            "proctor_invalidate_reason": row[19],
        }
    finally:
        cur.close()
        conn.close()


@router.get("/{instructor_id}/analytics")
def instructor_analytics(instructor_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT role FROM users WHERE id=%s", (instructor_id,))
        instructor = cur.fetchone()
        if not instructor:
            raise HTTPException(status_code=404, detail="Instructor not found")
        if instructor[0] != "instructor":
            raise HTTPException(status_code=403, detail="User is not an instructor")

        cur.execute(
            """
            SELECT e.topic, s.numerical_score, u.username, s.submitted_at
            FROM submissions s
            JOIN exams e ON s.exam_id = e.id
            JOIN users u ON s.student_id = u.id
            WHERE e.created_by = %s AND s.numerical_score IS NOT NULL
            ORDER BY s.submitted_at DESC
            """,
            (instructor_id,),
        )
        rows = cur.fetchall()
        records = [{"topic": r[0], "numerical_score": int(r[1]), "username": r[2], "submitted_at": r[3]} for r in rows]

        by_topic: dict[str, list[int]] = {}
        by_user: dict[str, list[int]] = {}
        for rec in records:
            by_topic.setdefault(rec["topic"], []).append(rec["numerical_score"])
            by_user.setdefault(rec["username"], []).append(rec["numerical_score"])

        avg_by_topic = {topic: round(sum(scores) / len(scores), 2) for topic, scores in by_topic.items()}
        leaderboard = sorted(
            [{"username": u, "avg_score": round(sum(scores) / len(scores), 2)} for u, scores in by_user.items()],
            key=lambda x: x["avg_score"],
            reverse=True,
        )

        return {
            "total_graded_submissions": len(records),
            "average_score_by_topic": avg_by_topic,
            "score_distribution": [rec["numerical_score"] for rec in records],
            "leaderboard": leaderboard,
            "records": records,
        }
    finally:
        cur.close()
        conn.close()
