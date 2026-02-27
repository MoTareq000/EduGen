import json
from typing import Any

from app.db.connection import get_db_connection


def audit_event(user_id: int | None, event_type: str, meta: dict[str, Any] | None = None):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO audit_logs (user_id, event_type, meta) VALUES (%s, %s, %s)",
            (user_id, event_type, json.dumps(meta or {}, ensure_ascii=True)),
        )
        conn.commit()
    except Exception:
        pass
    finally:
        if "cur" in locals():
            cur.close()
        if "conn" in locals():
            conn.close()
