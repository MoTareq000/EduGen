from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from app.db.connection import get_db_connection


def ensure_student(student_id: int) -> tuple[int, str]:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, username, role FROM users WHERE id=%s", (student_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Student not found")
        if row[2] != "student":
            raise HTTPException(status_code=403, detail="User is not a student")
        return row[0], row[1]
    finally:
        cur.close()
        conn.close()


def ensure_instructor(instructor_id: int) -> None:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT role FROM users WHERE id=%s", (instructor_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Instructor not found")
        if row[0] != "instructor":
            raise HTTPException(status_code=403, detail="User is not an instructor")
    finally:
        cur.close()
        conn.close()


def ensure_exam_for_student(exam_id: int) -> tuple[int, str]:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, topic, status FROM exams WHERE id=%s", (exam_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Exam not found")
        if row[2] != "published":
            raise HTTPException(status_code=400, detail="Exam is not published")
        return row[0], row[1]
    finally:
        cur.close()
        conn.close()


def create_proctor_session(
    student_id: int,
    exam_id: int,
    student_name: str,
    exam_title: str,
    duration_min: int,
) -> dict[str, Any]:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        session_id = str(uuid4())
        cur.execute(
            """
            INSERT INTO proctor_sessions (id, student_name, exam_title, duration_min, started_at, student_id, exam_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, started_at
            """,
            (session_id, student_name, exam_title, duration_min, datetime.utcnow(), student_id, exam_id),
        )
        session_id, started_at = cur.fetchone()
        conn.commit()
        return {"id": str(session_id), "started_at": started_at}
    finally:
        cur.close()
        conn.close()


def insert_proctor_alert(session_id: str, alert: dict[str, Any]) -> None:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        alert_id = str(uuid4())
        severity = (alert.get("severity") or "").lower()
        cur.execute(
            """
            INSERT INTO proctor_alerts (id, session_id, type, message, severity)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (alert_id, session_id, alert["type"], alert["message"], alert["severity"]),
        )
        cur.execute(
            """
            UPDATE proctor_sessions
            SET total_alerts = COALESCE(total_alerts, 0) + 1,
                high_alerts = COALESCE(high_alerts, 0) + CASE WHEN %s = 'high' THEN 1 ELSE 0 END,
                medium_alerts = COALESCE(medium_alerts, 0) + CASE WHEN %s = 'medium' THEN 1 ELSE 0 END,
                invalidated = CASE
                    WHEN (COALESCE(high_alerts, 0) + CASE WHEN %s = 'high' THEN 1 ELSE 0 END) >= 3 THEN true
                    ELSE invalidated
                END,
                invalidate_reason = CASE
                    WHEN (COALESCE(high_alerts, 0) + CASE WHEN %s = 'high' THEN 1 ELSE 0 END) >= 3
                        THEN COALESCE(invalidate_reason, 'Exam auto-invalidated: 3 or more high-severity violations detected.')
                    ELSE invalidate_reason
                END
            WHERE id=%s
            """,
            (severity, severity, severity, severity, session_id),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def finalize_proctor_session(
    session_id: str,
    focus_score_final: float,
    total_alerts: int,
    high_alerts: int,
    medium_alerts: int,
    invalidated: bool,
    invalidate_reason: str | None = None,
) -> None:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE proctor_sessions
            SET ended_at=%s,
                focus_score_final=%s,
                total_alerts=%s,
                high_alerts=%s,
                medium_alerts=%s,
                invalidated=%s,
                invalidate_reason=%s
            WHERE id=%s
            """,
            (
                datetime.utcnow(),
                focus_score_final,
                total_alerts,
                high_alerts,
                medium_alerts,
                invalidated,
                invalidate_reason,
                session_id,
            ),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def get_proctor_session(session_id: str) -> dict[str, Any] | None:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, student_name, exam_title, duration_min, started_at, ended_at,
                   focus_score_final, total_alerts, high_alerts, medium_alerts,
                   invalidated, invalidate_reason, student_id, exam_id, submission_id
            FROM proctor_sessions
            WHERE id=%s
            """,
            (session_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": str(row[0]),
            "student_name": row[1],
            "exam_title": row[2],
            "duration_min": row[3],
            "started_at": row[4],
            "ended_at": row[5],
            "focus_score_final": float(row[6]) if row[6] is not None else None,
            "total_alerts": row[7],
            "high_alerts": row[8],
            "medium_alerts": row[9],
            "invalidated": row[10],
            "invalidate_reason": row[11],
            "student_id": row[12],
            "exam_id": row[13],
            "submission_id": row[14],
        }
    finally:
        cur.close()
        conn.close()


def get_proctor_alerts(session_id: str) -> list[dict[str, Any]]:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, at, type, message, severity
            FROM proctor_alerts
            WHERE session_id=%s
            ORDER BY at ASC
            """,
            (session_id,),
        )
        rows = cur.fetchall()
        return [
            {
                "id": str(r[0]),
                "at": r[1],
                "type": r[2],
                "message": r[3],
                "severity": r[4],
            }
            for r in rows
        ]
    finally:
        cur.close()
        conn.close()


def link_submission_to_session(session_id: str, submission_id: int) -> None:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE proctor_sessions SET submission_id=%s WHERE id=%s",
            (submission_id, session_id),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def list_instructor_proctor_sessions(instructor_id: int, limit: int = 200) -> list[dict[str, Any]]:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT ps.id, ps.student_name, ps.exam_title, ps.started_at, ps.ended_at,
                   ps.focus_score_final, ps.total_alerts, ps.high_alerts, ps.medium_alerts,
                   ps.invalidated, ps.invalidate_reason, ps.exam_id, ps.submission_id
            FROM proctor_sessions ps
            JOIN exams e ON e.id = ps.exam_id
            WHERE e.created_by = %s
            ORDER BY ps.started_at DESC
            LIMIT %s
            """,
            (instructor_id, limit),
        )
        rows = cur.fetchall()
        return [
            {
                "id": str(r[0]),
                "student_name": r[1],
                "exam_title": r[2],
                "started_at": r[3],
                "ended_at": r[4],
                "focus_score_final": float(r[5]) if r[5] is not None else None,
                "total_alerts": r[6],
                "high_alerts": r[7],
                "medium_alerts": r[8],
                "invalidated": r[9],
                "invalidate_reason": r[10],
                "exam_id": r[11],
                "submission_id": r[12],
            }
            for r in rows
        ]
    finally:
        cur.close()
        conn.close()


def invalidate_session(session_id: str, reason: str | None = None) -> None:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE proctor_sessions
            SET invalidated=true, invalidate_reason=COALESCE(%s, invalidate_reason, 'Exam manually invalidated by instructor.')
            WHERE id=%s
            """,
            (reason, session_id),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
