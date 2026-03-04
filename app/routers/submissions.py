import json
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from app.db.connection import get_db_connection
from app.schemas import GradeRequest, ManualOverrideRequest, SubmitRequest
from app.services.audit_service import audit_event
from app.services.common_service import parse_json_blob, parse_score_from_text
from app.services.grading_service import grade_structured_submission
from app.services.proctor_service import get_proctor_session
from app.services.rag_service import get_rag

router = APIRouter(prefix="/submissions", tags=["submissions"])


@router.post("")
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

        cur.execute("SELECT id FROM submissions WHERE exam_id=%s AND student_id=%s", (payload.exam_id, payload.student_id))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Student already submitted this exam")

        if payload.proctor_session_id:
            session = get_proctor_session(payload.proctor_session_id)
            if not session:
                raise HTTPException(status_code=404, detail="Proctor session not found")
            if session.get("student_id") != payload.student_id or session.get("exam_id") != payload.exam_id:
                raise HTTPException(status_code=400, detail="Proctor session does not match this student/exam")

        answers_text = payload.answers if isinstance(payload.answers, str) else json.dumps(payload.answers, ensure_ascii=True)
        cur.execute(
            "INSERT INTO submissions (exam_id, student_id, student_answers) VALUES (%s,%s,%s) RETURNING id",
            (payload.exam_id, payload.student_id, answers_text),
        )
        submission_id = cur.fetchone()[0]

        if payload.proctor_session_id:
            # Keep link update in the same DB transaction as submission insert
            # to avoid FK visibility issues across separate connections.
            cur.execute(
                "UPDATE proctor_sessions SET submission_id=%s WHERE id=%s",
                (submission_id, payload.proctor_session_id),
            )

        conn.commit()

        audit_event(
            payload.student_id,
            "submission_created" if isinstance(payload.answers, dict) else "submission_created_legacy",
            {"exam_id": payload.exam_id, "submission_id": submission_id},
        )
        return {"id": submission_id}
    finally:
        cur.close()
        conn.close()


@router.post("/grade")
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
            SELECT s.id, s.student_answers, e.content, e.rubric, e.created_by, s.exam_id
            FROM submissions s JOIN exams e ON s.exam_id = e.id
            WHERE s.id = %s
            """,
            (payload.submission_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Submission not found")

        submission_id, student_answers, exam_content, rubric, exam_owner, exam_id = row
        if exam_owner != payload.instructor_id:
            raise HTTPException(status_code=403, detail="Cannot grade submissions for another instructor")

        rag = get_rag()
        prompt_exam = f"RUBRIC:\n{rubric}\n\n{exam_content}" if rubric else exam_content
        ai_feedback = rag.grade_submission(prompt_exam, student_answers)
        if isinstance(ai_feedback, str) and ai_feedback.startswith("Grading Error:"):
            raise HTTPException(status_code=502, detail=ai_feedback)

        exam_data = parse_json_blob(exam_content)
        student_data = parse_json_blob(student_answers)
        if exam_data and student_data:
            grading = grade_structured_submission(exam_data, student_data, ai_feedback)
            score = int(grading["final_score"])
            score_breakdown = json.dumps(grading, ensure_ascii=True)
        else:
            score = parse_score_from_text(ai_feedback)
            score_breakdown = json.dumps({"legacy_mode": True, "parsed_score": score}, ensure_ascii=True)

        cur.execute(
            """
            UPDATE submissions
            SET ai_feedback=%s, numerical_score=%s, score_breakdown=%s, graded_by=%s, graded_at=CURRENT_TIMESTAMP
            WHERE id=%s
            """,
            (ai_feedback, score, score_breakdown, payload.instructor_id, submission_id),
        )
        conn.commit()
        audit_event(payload.instructor_id, "submission_graded", {"submission_id": submission_id, "exam_id": exam_id, "score": score})
        return {
            "submission_id": submission_id,
            "score": score,
            "feedback": ai_feedback,
            "score_breakdown": json.loads(score_breakdown),
        }
    finally:
        cur.close()
        conn.close()


@router.put("/{submission_id}/override")
def override_submission(submission_id: int, payload: ManualOverrideRequest):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT role FROM users WHERE id=%s", (payload.instructor_id,))
        instructor = cur.fetchone()
        if not instructor or instructor[0] != "instructor":
            raise HTTPException(status_code=403, detail="Only instructors can override grades")

        cur.execute(
            """
            SELECT s.exam_id, e.created_by
            FROM submissions s JOIN exams e ON s.exam_id = e.id
            WHERE s.id=%s
            """,
            (submission_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Submission not found")

        exam_id, exam_owner = row
        if exam_owner != payload.instructor_id:
            raise HTTPException(status_code=403, detail="Cannot override another instructor's submission")

        cur.execute(
            """
            UPDATE submissions
            SET numerical_score = %s, grader_note = %s,
                graded_by = %s, graded_at = CURRENT_TIMESTAMP,
                ai_feedback = COALESCE(ai_feedback, %s)
            WHERE id = %s
            """,
            (payload.score, payload.note, payload.instructor_id, "Manually graded by instructor.", submission_id),
        )
        conn.commit()
        audit_event(payload.instructor_id, "submission_override", {"submission_id": submission_id, "exam_id": exam_id, "score": payload.score})
        return {"submission_id": submission_id, "score": payload.score, "note": payload.note}
    finally:
        cur.close()
        conn.close()


@router.get("/by-exam")
def get_student_submission_for_exam(exam_id: int = Query(...), student_id: int = Query(...)):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT role FROM users WHERE id=%s", (student_id,))
        user = cur.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Student not found")

        cur.execute(
            """
            SELECT id, exam_id, student_id, student_answers, ai_feedback, numerical_score, score_breakdown, grader_note, submitted_at
            FROM submissions
            WHERE exam_id=%s AND student_id=%s
            ORDER BY id DESC
            LIMIT 1
            """,
            (exam_id, student_id),
        )
        row = cur.fetchone()
        if not row:
            return {"exists": False}
        return {
            "exists": True,
            "submission_id": row[0],
            "exam_id": row[1],
            "student_id": row[2],
            "student_answers": row[3],
            "ai_feedback": row[4],
            "numerical_score": row[5],
            "score_breakdown": json.loads(row[6]) if row[6] else None,
            "grader_note": row[7],
            "submitted_at": row[8],
        }
    finally:
        cur.close()
        conn.close()


@router.get("/students/{student_id}")
def list_student_submissions(student_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT role FROM users WHERE id=%s", (student_id,))
        user = cur.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Student not found")

        cur.execute(
            """
            SELECT s.id, s.exam_id, e.topic, s.student_answers, s.ai_feedback, s.numerical_score, s.score_breakdown, s.grader_note, s.submitted_at
            FROM submissions s
            JOIN exams e ON e.id = s.exam_id
            WHERE s.student_id=%s
            ORDER BY s.id DESC
            """,
            (student_id,),
        )
        rows = cur.fetchall()
        return [
            {
                "submission_id": r[0],
                "exam_id": r[1],
                "exam_topic": r[2],
                "student_answers": r[3],
                "ai_feedback": r[4],
                "numerical_score": r[5],
                "score_breakdown": json.loads(r[6]) if r[6] else None,
                "grader_note": r[7],
                "submitted_at": r[8],
            }
            for r in rows
        ]
    finally:
        cur.close()
        conn.close()
