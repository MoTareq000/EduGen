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
                   s.score_breakdown, s.grader_note
            FROM submissions s
            JOIN exams e ON s.exam_id = e.id
            JOIN users u ON s.student_id = u.id
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
            }
            for r in rows
        ]
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
