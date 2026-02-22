import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()


def build_db_params():
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


def create_tables():
    try:
        params = build_db_params()
        if "dsn" in params:
            conn = psycopg2.connect(params["dsn"], sslmode=params.get("sslmode", "require"))
        else:
            conn = psycopg2.connect(**params)
        cur = conn.cursor()

        commands = [
            "CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, role TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS exams (id SERIAL PRIMARY KEY, topic TEXT NOT NULL, content TEXT NOT NULL, difficulty TEXT, created_by INTEGER REFERENCES users(id))",
            "CREATE TABLE IF NOT EXISTS submissions (id SERIAL PRIMARY KEY, exam_id INTEGER REFERENCES exams(id), student_id INTEGER REFERENCES users(id), student_answers TEXT, ai_feedback TEXT, numerical_score INTEGER, submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_provider TEXT",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_subject TEXT",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT",
            "ALTER TABLE exams ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'draft'",
            "ALTER TABLE exams ADD COLUMN IF NOT EXISTS due_at TIMESTAMP NULL",
            "ALTER TABLE exams ADD COLUMN IF NOT EXISTS published_at TIMESTAMP NULL",
            "ALTER TABLE exams ADD COLUMN IF NOT EXISTS rubric TEXT NULL",
            "ALTER TABLE exams ADD COLUMN IF NOT EXISTS source_refs TEXT NULL",
            "ALTER TABLE exams ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1",
            "ALTER TABLE submissions ADD COLUMN IF NOT EXISTS graded_by INTEGER NULL REFERENCES users(id)",
            "ALTER TABLE submissions ADD COLUMN IF NOT EXISTS graded_at TIMESTAMP NULL",
            "ALTER TABLE submissions ADD COLUMN IF NOT EXISTS grader_note TEXT NULL",
            "ALTER TABLE submissions ADD COLUMN IF NOT EXISTS score_breakdown TEXT NULL",
            "CREATE TABLE IF NOT EXISTS exam_versions (id SERIAL PRIMARY KEY, exam_id INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE, version INTEGER NOT NULL, content TEXT NOT NULL, rubric TEXT NULL, status TEXT NOT NULL, due_at TIMESTAMP NULL, changed_by INTEGER NULL REFERENCES users(id), changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
            "CREATE TABLE IF NOT EXISTS audit_logs (id BIGSERIAL PRIMARY KEY, user_id INTEGER NULL REFERENCES users(id), event_type TEXT NOT NULL, meta TEXT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
            "CREATE UNIQUE INDEX IF NOT EXISTS users_oauth_identity_uniq ON users(oauth_provider, oauth_subject)",
            "CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_uniq ON users((lower(email))) WHERE email IS NOT NULL",
            "CREATE INDEX IF NOT EXISTS exams_created_by_idx ON exams(created_by)",
            "CREATE INDEX IF NOT EXISTS exams_status_due_idx ON exams(status, due_at)",
            "CREATE INDEX IF NOT EXISTS submissions_exam_id_idx ON submissions(exam_id)",
            "CREATE INDEX IF NOT EXISTS submissions_student_id_idx ON submissions(student_id)",
            "CREATE INDEX IF NOT EXISTS submissions_exam_student_idx ON submissions(exam_id, student_id)",
            "CREATE INDEX IF NOT EXISTS audit_logs_user_event_idx ON audit_logs(user_id, event_type)",
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'users_role_check') THEN
                    ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ('student','instructor'));
                END IF;
            END
            $$;
            """,
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'exams_status_check') THEN
                    ALTER TABLE exams ADD CONSTRAINT exams_status_check CHECK (status IN ('draft','published','archived'));
                END IF;
            END
            $$;
            """,
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'submissions_score_range_check') THEN
                    ALTER TABLE submissions ADD CONSTRAINT submissions_score_range_check CHECK (numerical_score IS NULL OR (numerical_score >= 0 AND numerical_score <= 100));
                END IF;
            END
            $$;
            """,
        ]

        for command in commands:
            cur.execute(command)

        conn.commit()
        print("Tables created/updated successfully.")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    create_tables()
