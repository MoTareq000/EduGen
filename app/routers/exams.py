import json
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException

from app.db.connection import get_db_connection
from app.schemas import CreateExamRequest, UpdateExamRequest
from app.services.audit_service import audit_event
from app.services.common_service import parse_json_blob

router = APIRouter(prefix="/exams", tags=["exams"])


@router.post("")
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
            RETURNING id, version
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
        exam_id, version = cur.fetchone()

        cur.execute(
            """
            INSERT INTO exam_versions (exam_id, version, content, rubric, status, due_at, changed_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                exam_id,
                version,
                payload.content,
                payload.rubric,
                payload.status,
                payload.due_at,
                payload.instructor_id,
            ),
        )
        conn.commit()
        audit_event(payload.instructor_id, "exam_created", {"exam_id": exam_id, "status": payload.status})
        return {"id": exam_id, "version": version}
    finally:
        cur.close()
        conn.close()


@router.put("/{exam_id}")
def update_exam(exam_id: int, payload: UpdateExamRequest):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT created_by FROM exams WHERE id=%s", (exam_id,))
        exam_row = cur.fetchone()
        if not exam_row:
            raise HTTPException(status_code=404, detail="Exam not found")
        if exam_row[0] != payload.instructor_id:
            raise HTTPException(status_code=403, detail="Cannot update another instructor's exam")

        cur.execute(
            """
            UPDATE exams
            SET status=%s,due_at=%s,rubric=%s,
                published_at=CASE WHEN %s='published' AND published_at IS NULL THEN CURRENT_TIMESTAMP ELSE published_at END,
                version=version+1
            WHERE id=%s
            RETURNING version, content
            """,
            (payload.status, payload.due_at, payload.rubric, payload.status, exam_id),
        )
        version, content = cur.fetchone()

        cur.execute(
            """
            INSERT INTO exam_versions (exam_id, version, content, rubric, status, due_at, changed_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,
            (exam_id, version, content, payload.rubric, payload.status, payload.due_at, payload.instructor_id),
        )
        conn.commit()
        audit_event(
            payload.instructor_id,
            "exam_updated",
            {"exam_id": exam_id, "status": payload.status, "version": version},
        )
        return {"id": exam_id, "version": version}
    finally:
        cur.close()
        conn.close()


@router.get("")
def list_exams(
    status: Literal["draft", "published", "archived"] | None = None,
    created_by: int | None = None,
):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        clauses = []
        args: list[Any] = []
        if status:
            clauses.append("status=%s")
            args.append(status)
        if created_by is not None:
            clauses.append("created_by=%s")
            args.append(created_by)

        sql = "SELECT id, topic, difficulty, status, due_at, created_by, version, rubric FROM exams"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY id DESC"
        cur.execute(sql, tuple(args))

        rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "topic": r[1],
                "difficulty": r[2],
                "status": r[3],
                "due_at": r[4],
                "created_by": r[5],
                "version": r[6],
                "rubric": r[7],
            }
            for r in rows
        ]
    finally:
        cur.close()
        conn.close()


@router.get("/{exam_id}")
def get_exam(exam_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, topic, difficulty, content, status, due_at, rubric, source_refs, version FROM exams WHERE id=%s",
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
            "version": row[8],
        }
    finally:
        cur.close()
        conn.close()


@router.get("/{exam_id}/versions")
def get_exam_versions(exam_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 FROM exams WHERE id=%s", (exam_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Exam not found")

        cur.execute(
            """
            SELECT version, status, due_at, changed_at, changed_by
            FROM exam_versions
            WHERE exam_id=%s
            ORDER BY version DESC
            """,
            (exam_id,),
        )
        rows = cur.fetchall()
        return [
            {"version": r[0], "status": r[1], "due_at": r[2], "changed_at": r[3], "changed_by": r[4]}
            for r in rows
        ]
    finally:
        cur.close()
        conn.close()
