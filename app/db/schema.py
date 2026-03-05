from app.db.connection import get_db_connection


def ensure_runtime_schema():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
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
            "CREATE TABLE IF NOT EXISTS proctor_sessions (id UUID PRIMARY KEY, student_name TEXT NOT NULL, exam_title TEXT NOT NULL, duration_min INTEGER NOT NULL, started_at TIMESTAMPTZ NOT NULL, ended_at TIMESTAMPTZ NULL, focus_score_final NUMERIC NULL, total_alerts INTEGER DEFAULT 0, high_alerts INTEGER DEFAULT 0, medium_alerts INTEGER DEFAULT 0, invalidated BOOLEAN DEFAULT false, invalidate_reason TEXT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), student_id INTEGER NULL REFERENCES users(id), exam_id INTEGER NULL REFERENCES exams(id), submission_id INTEGER NULL REFERENCES submissions(id))",
            "CREATE TABLE IF NOT EXISTS proctor_alerts (id UUID PRIMARY KEY, session_id UUID NOT NULL REFERENCES proctor_sessions(id), at TIMESTAMPTZ NOT NULL DEFAULT now(), type TEXT NOT NULL, message TEXT NOT NULL, severity TEXT NOT NULL)",
            "CREATE UNIQUE INDEX IF NOT EXISTS users_oauth_identity_uniq ON users(oauth_provider, oauth_subject)",
            "CREATE INDEX IF NOT EXISTS users_email_lower_idx ON users((lower(email)))",
            "CREATE INDEX IF NOT EXISTS exams_created_by_idx ON exams(created_by)",
            "CREATE INDEX IF NOT EXISTS exams_status_due_idx ON exams(status, due_at)",
            "CREATE INDEX IF NOT EXISTS submissions_exam_student_idx ON submissions(exam_id, student_id)",
            "CREATE INDEX IF NOT EXISTS audit_logs_user_event_idx ON audit_logs(user_id, event_type)",
            "CREATE INDEX IF NOT EXISTS proctor_sessions_exam_idx ON proctor_sessions(exam_id)",
            "CREATE INDEX IF NOT EXISTS proctor_sessions_submission_idx ON proctor_sessions(submission_id)",
            "CREATE INDEX IF NOT EXISTS proctor_alerts_session_at_idx ON proctor_alerts(session_id, at)",
        ]
        for command in commands:
            cur.execute(command)
        conn.commit()
    finally:
        cur.close()
        conn.close()


def db_health_ok() -> bool:
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.close()
        conn.close()
        return True
    except Exception:
        return False
