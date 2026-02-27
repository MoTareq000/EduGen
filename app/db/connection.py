from typing import Any

import psycopg2


def build_db_params() -> dict[str, Any]:
    import os

    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return {"dsn": database_url, "sslmode": "require"}

    project_ref = os.getenv("SUPABASE_PROJECT_REF")
    db_password = os.getenv("SUPABASE_DB_PASSWORD")
    db_user = os.getenv("SUPABASE_DB_USER", "postgres")
    db_name = os.getenv("SUPABASE_DB_NAME", "postgres")
    db_host = os.getenv("SUPABASE_DB_HOST") or (
        f"db.{project_ref}.supabase.co" if project_ref else None
    )
    db_port = os.getenv("SUPABASE_DB_PORT", "5432")

    if db_host and db_password:
        return {
            "dbname": db_name,
            "user": db_user,
            "password": db_password,
            "host": db_host,
            "port": db_port,
            "sslmode": "require",
        }

    raise RuntimeError(
        "Database is not configured. Set DATABASE_URL or SUPABASE_PROJECT_REF + SUPABASE_DB_PASSWORD."
    )


def get_db_connection():
    params = build_db_params()
    if "dsn" in params:
        return psycopg2.connect(params["dsn"], sslmode=params.get("sslmode", "require"))
    return psycopg2.connect(**params)
