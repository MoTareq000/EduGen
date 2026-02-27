import json

from fastapi import APIRouter, Query

from app.db.connection import get_db_connection

router = APIRouter(tags=["audit"])


@router.get("/audit-logs")
def list_audit_logs(limit: int = Query(default=200, ge=1, le=1000)):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, user_id, event_type, meta, created_at
            FROM audit_logs
            ORDER BY id DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "user_id": r[1],
                "event_type": r[2],
                "meta": json.loads(r[3]) if r[3] else {},
                "created_at": r[4],
            }
            for r in rows
        ]
    finally:
        cur.close()
        conn.close()
