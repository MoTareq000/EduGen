import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
from datetime import datetime
from urllib.parse import urlencode

import pandas as pd
import psycopg2
import requests
import streamlit as st
from dotenv import load_dotenv

from rag_pipeline import RAGPipeline

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("edu_portal")


# --------------------
# Config helpers
# --------------------
def get_config_value(key, default=""):
    value = os.getenv(key)
    if value:
        return value
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default


# --------------------
# Database
# --------------------
def build_db_params():
    database_url = get_config_value("DATABASE_URL", "")
    if database_url:
        return {"dsn": database_url, "sslmode": "require"}

    project_ref = get_config_value("SUPABASE_PROJECT_REF", "")
    db_password = get_config_value("SUPABASE_DB_PASSWORD", "")
    db_user = get_config_value("SUPABASE_DB_USER", "postgres")
    db_name = get_config_value("SUPABASE_DB_NAME", "postgres")
    db_host = get_config_value("SUPABASE_DB_HOST", "") or (
        f"db.{project_ref}.supabase.co" if project_ref else None
    )
    db_port = get_config_value("SUPABASE_DB_PORT", "5432")

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


def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()


def ensure_runtime_schema():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        commands = [
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
            """
            CREATE TABLE IF NOT EXISTS exam_versions (
                id SERIAL PRIMARY KEY,
                exam_id INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
                version INTEGER NOT NULL,
                content TEXT NOT NULL,
                rubric TEXT NULL,
                status TEXT NOT NULL,
                due_at TIMESTAMP NULL,
                changed_by INTEGER NULL REFERENCES users(id),
                changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id BIGSERIAL PRIMARY KEY,
                user_id INTEGER NULL REFERENCES users(id),
                event_type TEXT NOT NULL,
                meta TEXT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            "CREATE UNIQUE INDEX IF NOT EXISTS users_oauth_identity_uniq ON users(oauth_provider, oauth_subject)",
            "CREATE INDEX IF NOT EXISTS exams_created_by_idx ON exams(created_by)",
            "CREATE INDEX IF NOT EXISTS exams_status_due_idx ON exams(status, due_at)",
            "CREATE INDEX IF NOT EXISTS submissions_exam_id_idx ON submissions(exam_id)",
            "CREATE INDEX IF NOT EXISTS submissions_student_id_idx ON submissions(student_id)",
            "CREATE INDEX IF NOT EXISTS submissions_exam_student_idx ON submissions(exam_id, student_id)",
            "CREATE INDEX IF NOT EXISTS audit_logs_user_event_idx ON audit_logs(user_id, event_type)",
            "CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_uniq ON users((lower(email))) WHERE email IS NOT NULL",
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'users_role_check'
                ) THEN
                    ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ('student','instructor'));
                END IF;
            END
            $$;
            """,
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'exams_status_check'
                ) THEN
                    ALTER TABLE exams ADD CONSTRAINT exams_status_check CHECK (status IN ('draft','published','archived'));
                END IF;
            END
            $$;
            """,
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'submissions_score_range_check'
                ) THEN
                    ALTER TABLE submissions ADD CONSTRAINT submissions_score_range_check CHECK (numerical_score IS NULL OR (numerical_score >= 0 AND numerical_score <= 100));
                END IF;
            END
            $$;
            """,
        ]
        for command in commands:
            cur.execute(command)
        conn.commit()
    finally:
        cur.close()
        conn.close()


def audit_event(user_id, event_type, meta=None):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO audit_logs (user_id, event_type, meta) VALUES (%s, %s, %s)",
            (user_id, event_type, json.dumps(meta or {}, ensure_ascii=True)),
        )
        conn.commit()
    except Exception as e:
        logger.warning("Audit write failed: %s", e)
    finally:
        if "cur" in locals():
            cur.close()
        if "conn" in locals():
            conn.close()


def app_error(message, exc=None):
    err_id = secrets.token_hex(4)
    if exc:
        logger.exception("Error %s: %s", err_id, exc)
    st.error(f"{message} (Error ID: {err_id})")


def check_rate_limit(key, cooldown_seconds=8):
    if "rate_limits" not in st.session_state:
        st.session_state.rate_limits = {}
    now = time.time()
    last = st.session_state.rate_limits.get(key, 0)
    if now - last < cooldown_seconds:
        st.warning(f"Please wait {int(cooldown_seconds - (now - last))}s before retrying.")
        return False
    st.session_state.rate_limits[key] = now
    return True


def require_role(user, roles):
    if not user or user.get("role") not in roles:
        st.error("You do not have permission to access this area.")
        st.stop()


def parse_score_from_text(text):
    try:
        score_match = re.search(r"(\\d+)/100", text or "") or re.search(
            r"Score:\\s*(\\d+)", text or "", re.I
        )
        score = int(score_match.group(1)) if score_match else 0
    except Exception:
        score = 0
    return max(0, min(100, score))


def normalize_exam_weights(exam_data, mcq_weight, essay_weight):
    if not isinstance(exam_data, dict):
        return exam_data
    for mcq in exam_data.get("mcqs", []):
        if isinstance(mcq, dict):
            mcq["weight"] = int(mcq.get("weight") or mcq_weight)
    for essay in exam_data.get("essays", []):
        if isinstance(essay, dict):
            essay["weight"] = int(essay.get("weight") or essay_weight)
    return exam_data


def grade_structured_submission(exam_data, student_data, essay_feedback_text):
    mcqs = exam_data.get("mcqs", []) if isinstance(exam_data, dict) else []
    essays = exam_data.get("essays", []) if isinstance(exam_data, dict) else []
    by_id = {}
    for ans in student_data.get("mcq_answers", []) if isinstance(student_data, dict) else []:
        qid = str(ans.get("id", "")).strip()
        if qid:
            by_id[qid] = ans

    mcq_total = sum(max(1, int(q.get("weight", 1))) for q in mcqs if isinstance(q, dict))
    essay_total = sum(max(1, int(q.get("weight", 1))) for q in essays if isinstance(q, dict))

    mcq_scored = 0.0
    details = []
    for q in mcqs:
        if not isinstance(q, dict):
            continue
        qid = str(q.get("id", "")).strip()
        weight = max(1, int(q.get("weight", 1)))
        expected = int(q.get("correct_option_index", 0))
        selected = -1
        if qid in by_id:
            try:
                selected = int(by_id[qid].get("selected_option_index", -1))
            except Exception:
                selected = -1
        correct = selected == expected
        if correct:
            mcq_scored += weight
        details.append({"id": qid, "weight": weight, "selected": selected, "expected": expected, "correct": correct})

    essay_percent = parse_score_from_text(essay_feedback_text)
    essay_scored = (essay_total * essay_percent) / 100.0

    total = max(1.0, mcq_total + essay_total)
    final_score = int(round(((mcq_scored + essay_scored) / total) * 100.0))
    final_score = max(0, min(100, final_score))
    return {
        "final_score": final_score,
        "mcq": {"scored_weight": mcq_scored, "total_weight": mcq_total, "details": details},
        "essay": {"ai_percent": essay_percent, "scored_weight": essay_scored, "total_weight": essay_total},
    }

def ensure_users_oauth_schema():
    ensure_runtime_schema()


# --------------------
# Exam JSON helpers
# --------------------
def parse_json_blob(text):
    if not text:
        return None

    candidate = str(text).strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\\s*", "", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\\s*```$", "", candidate)

    try:
        data = json.loads(candidate)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def format_exam_for_instructor(exam_data):
    lines = [
        f"Topic: {exam_data.get('topic', '')}",
        f"Difficulty: {exam_data.get('difficulty', '')}",
        "",
    ]

    for i, mcq in enumerate(exam_data.get("mcqs", []), start=1):
        lines.append(f"MCQ {i}: {mcq.get('question', '')}")
        options = mcq.get("options", [])
        for j, opt in enumerate(options):
            lines.append(f"  {chr(65 + j)}. {opt}")
        idx = mcq.get("correct_option_index", 0)
        answer = options[idx] if options and isinstance(idx, int) and 0 <= idx < len(options) else ""
        lines.append(f"  Correct: {answer}")
        lines.append(f"  Weight: {mcq.get('weight', 1)}")
        explanation = mcq.get("explanation", "")
        if explanation:
            lines.append(f"  Explanation: {explanation}")
        lines.append("")

    for i, essay in enumerate(exam_data.get("essays", []), start=1):
        lines.append(f"Essay {i}: {essay.get('question', '')}")
        lines.append(f"  Weight: {essay.get('weight', 1)}")
        model_answer = essay.get("model_answer", "")
        if model_answer:
            lines.append(f"  Model Answer: {model_answer}")
        lines.append("")

    return "\n".join(lines)


def format_student_submission(student_data):
    lines = []

    mcq_answers = student_data.get("mcq_answers", []) if isinstance(student_data, dict) else []
    essay_answers = student_data.get("essay_answers", []) if isinstance(student_data, dict) else []

    if mcq_answers:
        lines.append("MCQ Answers:")
        for i, ans in enumerate(mcq_answers, start=1):
            question = ans.get("question", f"MCQ {i}")
            chosen = ans.get("selected_option", "")
            lines.append(f"  {i}. {question}")
            lines.append(f"     Selected: {chosen}")

    if essay_answers:
        lines.append("\nEssay Answers:")
        for i, ans in enumerate(essay_answers, start=1):
            question = ans.get("question", f"Essay {i}")
            answer = ans.get("answer", "")
            lines.append(f"  {i}. {question}")
            lines.append(f"     {answer}")

    if not lines:
        return "No structured answers found."

    return "\n".join(lines)


# --------------------
# OAuth helpers
# --------------------
def get_app_base_url():
    return get_config_value("APP_BASE_URL", "http://localhost:8501").rstrip("/")


def get_oauth_providers():
    return {
        "google": {
            "label": "Continue with Google",
            "client_id": get_config_value("GOOGLE_CLIENT_ID", ""),
            "client_secret": get_config_value("GOOGLE_CLIENT_SECRET", ""),
            "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
            "scope": "openid email profile",
        },
        "github": {
            "label": "Continue with GitHub",
            "client_id": get_config_value("GITHUB_CLIENT_ID", ""),
            "client_secret": get_config_value("GITHUB_CLIENT_SECRET", ""),
            "authorize_url": "https://github.com/login/oauth/authorize",
            "token_url": "https://github.com/login/oauth/access_token",
            "userinfo_url": "https://api.github.com/user",
            "scope": "read:user user:email",
        },
    }


def oauth_redirect_uri(provider):
    return f"{get_app_base_url()}/?provider={provider}"


def _oauth_state_secret():
    explicit = get_config_value("OAUTH_STATE_SECRET", "")
    if explicit:
        return explicit
    fallback = "|".join(
        [
            get_config_value("GOOGLE_CLIENT_SECRET", ""),
            get_config_value("GITHUB_CLIENT_SECRET", ""),
            get_config_value("DATABASE_URL", ""),
        ]
    )
    return fallback or "dev-oauth-state-secret"


def build_oauth_state(provider, role):
    safe_role = role if role in ("student", "instructor") else "student"
    payload = {
        "provider": provider,
        "role": safe_role,
        "nonce": secrets.token_urlsafe(8),
        "iat": int(time.time()),
    }
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    sig = hmac.new(
        _oauth_state_secret().encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{body}.{sig}"


def verify_oauth_state(provider, token, max_age_seconds=900):
    if not token or "." not in token:
        return None

    body, sig = token.rsplit(".", 1)
    expected_sig = hmac.new(
        _oauth_state_secret().encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return None

    try:
        payload = json.loads(body)
    except Exception:
        return None

    issued_at = int(payload.get("iat", 0))
    if issued_at <= 0 or (int(time.time()) - issued_at) > max_age_seconds:
        return None
    if payload.get("provider") != provider:
        return None
    role = payload.get("role", "student")
    payload["role"] = role if role in ("student", "instructor") else "student"
    return payload


def build_authorize_url(provider, cfg, role):
    state = build_oauth_state(provider, role)
    params = {
        "client_id": cfg["client_id"],
        "redirect_uri": oauth_redirect_uri(provider),
        "response_type": "code",
        "scope": cfg["scope"],
        "state": state,
    }
    return f"{cfg['authorize_url']}?{urlencode(params)}"


def exchange_code_for_token(provider, cfg, code):
    redirect_uri = oauth_redirect_uri(provider)

    if provider == "github":
        resp = requests.post(
            cfg["token_url"],
            headers={"Accept": "application/json"},
            data={
                "client_id": cfg["client_id"],
                "client_secret": cfg["client_secret"],
                "code": code,
                "redirect_uri": redirect_uri,
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise RuntimeError(f"GitHub token error: {data}")
        return token

    if provider == "google":
        resp = requests.post(
            cfg["token_url"],
            data={
                "client_id": cfg["client_id"],
                "client_secret": cfg["client_secret"],
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise RuntimeError(f"Google token error: {data}")
        return token

    raise RuntimeError("Unsupported provider")


def get_oauth_profile(provider, cfg, access_token):
    if provider == "google":
        resp = requests.get(
            cfg["userinfo_url"],
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "provider": "google",
            "subject": str(data.get("sub", "")),
            "email": data.get("email", ""),
            "display_name": data.get("name", "") or data.get("email", ""),
        }

    if provider == "github":
        resp = requests.get(
            cfg["userinfo_url"],
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=20,
        )
        resp.raise_for_status()
        user = resp.json()

        email = user.get("email")
        if not email:
            email_resp = requests.get(
                "https://api.github.com/user/emails",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=20,
            )
            email_resp.raise_for_status()
            emails = email_resp.json()
            primary = next((e for e in emails if e.get("primary") and e.get("verified")), None)
            if primary:
                email = primary.get("email")

        return {
            "provider": "github",
            "subject": str(user.get("id", "")),
            "email": email or "",
            "display_name": user.get("name") or user.get("login") or email or "github_user",
        }

    raise RuntimeError("Unsupported provider")


def login_or_create_oauth_user(profile, fallback_role="student"):
    ensure_users_oauth_schema()

    provider = profile.get("provider", "")
    subject = profile.get("subject", "")
    email = (profile.get("email", "") or "").strip()
    display_name = profile.get("display_name", "")

    if not provider or not subject:
        raise RuntimeError("Invalid OAuth profile")

    username_base = (email or display_name or f"{provider}_user").strip()
    username_base = re.sub(r"\s+", "_", username_base)

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT id, username, role, email FROM users WHERE oauth_provider=%s AND oauth_subject=%s",
        (provider, subject),
    )
    user = cur.fetchone()
    if user:
        if email and (not user[3] or user[3].lower() != email.lower()):
            cur.execute("UPDATE users SET email=%s WHERE id=%s", (email, user[0]))
            conn.commit()
        cur.close()
        conn.close()
        return user[0], user[1], user[2]

    if email:
        cur.execute(
            "SELECT id, username, role, oauth_provider, oauth_subject FROM users WHERE lower(email)=lower(%s)",
            (email,),
        )
        existing = cur.fetchone()
        if existing:
            existing_provider = existing[3]
            existing_subject = existing[4]
            if (not existing_provider and not existing_subject) or (
                existing_provider == provider and existing_subject == subject
            ):
                cur.execute(
                    """
                    UPDATE users
                    SET oauth_provider=%s, oauth_subject=%s, email=%s
                    WHERE id=%s
                    RETURNING id, username, role
                    """,
                    (provider, subject, email, existing[0]),
                )
                linked = cur.fetchone()
                conn.commit()
                cur.close()
                conn.close()
                audit_event(linked[0], "oauth_account_linked", {"provider": provider})
                return linked
            cur.close()
            conn.close()
            raise RuntimeError("Email already linked to a different social account")

    role = fallback_role if fallback_role in ("student", "instructor") else "student"

    username = username_base
    suffix = 1
    while True:
        cur.execute("SELECT 1 FROM users WHERE username=%s", (username,))
        if not cur.fetchone():
            break
        suffix += 1
        username = f"{username_base}_{suffix}"

    random_pw = hash_password(secrets.token_hex(24))

    cur.execute(
        """
        INSERT INTO users (username, password, role, oauth_provider, oauth_subject, email)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id, username, role
        """,
        (username, random_pw, role, provider, subject, email or None),
    )
    created = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    audit_event(created[0], "oauth_account_created", {"provider": provider, "role": role})
    return created


def handle_oauth_callback_if_present():
    qp = st.query_params
    provider = qp.get("provider")
    code = qp.get("code")
    state = qp.get("state")

    if not provider or not code:
        return

    providers = get_oauth_providers()
    cfg = providers.get(provider)
    if not cfg:
        st.error("Unknown OAuth provider in callback.")
        st.query_params.clear()
        return

    state_payload = verify_oauth_state(provider, state)
    if not state_payload:
        st.error("OAuth state mismatch. Please retry login.")
        st.query_params.clear()
        return

    if not cfg["client_id"] or not cfg["client_secret"]:
        st.error(f"{provider.title()} OAuth is not configured in environment/secrets.")
        st.query_params.clear()
        return

    try:
        access_token = exchange_code_for_token(provider, cfg, code)
        profile = get_oauth_profile(provider, cfg, access_token)
        selected_role = state_payload.get("role", "student")
        user = login_or_create_oauth_user(profile, fallback_role=selected_role)

        st.session_state.logged_in = True
        st.session_state.user = {"id": user[0], "username": user[1], "role": user[2]}
        audit_event(user[0], "login_oauth_success", {"provider": provider})
        st.query_params.clear()
        st.rerun()
    except Exception as e:
        app_error("OAuth login failed", e)
        st.query_params.clear()


# --------------------
# Password auth helpers (kept as fallback)
# --------------------
def login_user(username, password):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, username, role FROM users WHERE username=%s AND password=%s",
        (username, hash_password(password)),
    )
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user


def get_health_status():
    if "health_status" in st.session_state:
        return st.session_state.health_status

    status = {
        "db_ok": False,
        "groq_key_ok": bool(get_config_value("GROQ_API_KEY", "")),
        "google_oauth_ok": bool(get_config_value("GOOGLE_CLIENT_ID", "")) and bool(get_config_value("GOOGLE_CLIENT_SECRET", "")),
        "github_oauth_ok": bool(get_config_value("GITHUB_CLIENT_ID", "")) and bool(get_config_value("GITHUB_CLIENT_SECRET", "")),
    }
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        status["db_ok"] = True
        cur.close()
        conn.close()
    except Exception:
        status["db_ok"] = False
    st.session_state.health_status = status
    return status


# --------------------
# Session bootstrap
# --------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user = None
if "runtime_ready" not in st.session_state:
    try:
        ensure_runtime_schema()
        st.session_state.runtime_ready = True
    except Exception as e:
        app_error("Database migration/bootstrap failed", e)
        st.stop()
if "rag" not in st.session_state:
    st.session_state.rag = RAGPipeline("pdfs")

handle_oauth_callback_if_present()


# --------------------
# UI
# --------------------
if not st.session_state.logged_in:
    st.title("AI University Portal")
    with st.expander("System Health", expanded=False):
        health = get_health_status()
        st.write(
            {
                "database": "ok" if health["db_ok"] else "error",
                "groq_api": "ok" if health["groq_key_ok"] else "missing",
                "google_oauth": "ok" if health["google_oauth_ok"] else "missing",
                "github_oauth": "ok" if health["github_oauth_ok"] else "missing",
            }
        )

    st.subheader("Social Sign In / Sign Up")
    selected_role = st.selectbox(
        "Role for first-time social account",
        ["student", "instructor"],
        index=0,
    )

    providers = get_oauth_providers()
    for provider in ["google", "github"]:
        cfg = providers[provider]
        if cfg["client_id"] and cfg["client_secret"]:
            auth_url = build_authorize_url(provider, cfg, selected_role)
            st.link_button(cfg["label"], auth_url)
        else:
            st.caption(f"{provider.title()} OAuth not configured in environment/secrets")

    st.divider()
    st.subheader("Local Login (Fallback)")
    choice = st.selectbox("Action", ["Login", "Sign Up"])
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if choice == "Sign Up":
        role = st.selectbox("Role", ["student", "instructor"])
        email = st.text_input("Email (optional, for OAuth account linking)")
        if st.button("Register"):
            try:
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO users (username, password, role, email) VALUES (%s, %s, %s, %s)",
                    (username, hash_password(password), role, email or None),
                )
                conn.commit()
                audit_event(None, "local_signup", {"username": username, "role": role})
                st.success("Created. Please login.")
            except Exception as e:
                app_error("Registration error", e)
            finally:
                if "cur" in locals():
                    cur.close()
                if "conn" in locals():
                    conn.close()
    else:
        if st.button("Login"):
            u = login_user(username, password)
            if u:
                st.session_state.logged_in = True
                st.session_state.user = {"id": u[0], "username": u[1], "role": u[2]}
                audit_event(u[0], "login_local_success", {"username": u[1]})
                st.rerun()
            else:
                st.error("Invalid username or password")

else:
    user = st.session_state.user
    st.sidebar.title(f"Welcome, {user['username']}")
    if st.sidebar.button("Logout"):
        audit_event(user["id"], "logout", {})
        st.session_state.logged_in = False
        st.session_state.user = None
        st.rerun()

    if user["role"] == "instructor":
        require_role(user, ["instructor"])
        tab1, tab2, tab3, tab4 = st.tabs(["Generate Exam", "Manage Exams", "Grade Submissions", "Analytics Dashboard"])

        with tab1:
            topic = st.text_input("Topic")
            m, e = st.columns(2)
            mcq_n = m.slider("MCQs", 1, 10, 5)
            ess_n = e.slider("Essays", 1, 5, 2)
            diff = st.select_slider("Level", ["Beginner", "Intermediate", "Expert"])
            w1, w2 = st.columns(2)
            mcq_weight = w1.number_input("Default MCQ weight", 1, 20, 2)
            essay_weight = w2.number_input("Default Essay weight", 1, 30, 10)
            exam_status = st.selectbox("Initial Status", ["draft", "published"], index=0)
            rubric = st.text_area("Rubric (used during grading)", placeholder="Optional grading rubric")
            set_due = st.checkbox("Set due date/time", value=False)
            due_at = None
            if set_due:
                due_date = st.date_input("Due date")
                due_time = st.time_input("Due time")
                due_at = datetime.combine(due_date, due_time)
            if st.button("Save Exam"):
                if not check_rate_limit("generate_exam", cooldown_seconds=8):
                    st.stop()
                text, sources = st.session_state.rag.query(topic, mcq_n, ess_n, diff, "Instructor Mode")
                exam_data = parse_json_blob(text)

                if exam_data and (exam_data.get("mcqs") or exam_data.get("essays")):
                    exam_data = normalize_exam_weights(exam_data, mcq_weight, essay_weight)
                    stored_content = json.dumps(exam_data, ensure_ascii=True)
                    st.text_area(
                        "Instructor Preview (includes answer key)",
                        format_exam_for_instructor(exam_data),
                        height=300,
                    )
                else:
                    stored_content = text
                    st.warning(
                        "Generated content is not structured JSON; student form mode may not work for this exam."
                    )
                    st.text_area("Preview", text, height=300)

                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO exams (topic, content, difficulty, created_by, status, due_at, published_at, rubric, source_refs, version)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING id, version
                    """,
                    (
                        topic,
                        stored_content,
                        diff,
                        user["id"],
                        exam_status,
                        due_at,
                        datetime.now() if exam_status == "published" else None,
                        rubric or None,
                        json.dumps(sorted(list(sources)), ensure_ascii=True),
                        1,
                    ),
                )
                exam_row = cur.fetchone()
                cur.execute(
                    """
                    INSERT INTO exam_versions (exam_id, version, content, rubric, status, due_at, changed_by)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        exam_row[0],
                        exam_row[1],
                        stored_content,
                        rubric or None,
                        exam_status,
                        due_at,
                        user["id"],
                    ),
                )
                conn.commit()
                cur.close()
                conn.close()
                audit_event(user["id"], "exam_created", {"exam_id": exam_row[0], "status": exam_status})
                st.success("Exam Saved")

        with tab2:
            st.subheader("Manage Exams")
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, topic, difficulty, status, due_at, version, rubric, content
                FROM exams
                WHERE created_by=%s
                ORDER BY id DESC
                """,
                (user["id"],),
            )
            own_exams = cur.fetchall()
            cur.close()
            conn.close()

            if own_exams:
                selected_exam = st.selectbox(
                    "Select exam",
                    own_exams,
                    format_func=lambda x: f"#{x[0]} {x[1]} [{x[3]}] v{x[5]}",
                )
                ex_id, ex_topic, ex_diff, ex_status, ex_due, ex_ver, ex_rubric, ex_content = selected_exam
                new_status = st.selectbox(
                    "Status",
                    ["draft", "published", "archived"],
                    index=["draft", "published", "archived"].index(ex_status),
                )
                keep_due = st.checkbox("Set/Update due date", value=bool(ex_due))
                new_due = None
                if keep_due:
                    d = st.date_input("Due date", value=ex_due.date() if ex_due else datetime.now().date(), key=f"due_date_{ex_id}")
                    t = st.time_input("Due time", value=ex_due.time() if ex_due else datetime.now().time(), key=f"due_time_{ex_id}")
                    new_due = datetime.combine(d, t)
                new_rubric = st.text_area("Rubric", value=ex_rubric or "", key=f"rubric_{ex_id}")

                c1, c2 = st.columns(2)
                if c1.button("Save Exam Settings"):
                    conn = get_db_connection()
                    cur = conn.cursor()
                    cur.execute(
                        """
                        UPDATE exams
                        SET status=%s,
                            due_at=%s,
                            rubric=%s,
                            published_at=CASE
                                WHEN %s='published' AND published_at IS NULL THEN CURRENT_TIMESTAMP
                                ELSE published_at
                            END,
                            version=version+1
                        WHERE id=%s
                        RETURNING version, content
                        """,
                        (new_status, new_due, new_rubric or None, new_status, ex_id),
                    )
                    new_ver, content_snapshot = cur.fetchone()
                    cur.execute(
                        """
                        INSERT INTO exam_versions (exam_id, version, content, rubric, status, due_at, changed_by)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (ex_id, new_ver, content_snapshot, new_rubric or None, new_status, new_due, user["id"]),
                    )
                    conn.commit()
                    cur.close()
                    conn.close()
                    audit_event(user["id"], "exam_updated", {"exam_id": ex_id, "status": new_status, "version": new_ver})
                    st.success("Exam settings updated")
                    st.rerun()

                if c2.button("Show Version History"):
                    conn = get_db_connection()
                    cur = conn.cursor()
                    cur.execute(
                        """
                        SELECT version, status, due_at, changed_at
                        FROM exam_versions
                        WHERE exam_id=%s
                        ORDER BY version DESC
                        """,
                        (ex_id,),
                    )
                    versions = cur.fetchall()
                    cur.close()
                    conn.close()
                    st.table(pd.DataFrame(versions, columns=["version", "status", "due_at", "changed_at"]))
            else:
                st.info("No exams found.")

        with tab3:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                """
                SELECT s.id, u.username, e.id, e.topic, s.student_answers, e.content, e.rubric,
                       s.ai_feedback, s.numerical_score, s.score_breakdown, s.grader_note
                FROM submissions s
                JOIN users u ON s.student_id = u.id
                JOIN exams e ON s.exam_id = e.id
                WHERE e.created_by = %s
                ORDER BY s.id DESC
                """,
                (user["id"],),
            )
            subs = cur.fetchall()
            cur.close()
            conn.close()

            for s_id, u_name, exam_id, topic, s_ans, e_cont, rubric, feedback, current_score, breakdown_json, grader_note in subs:
                exam_data = parse_json_blob(e_cont)
                student_data = parse_json_blob(s_ans)

                with st.expander(f"{u_name} - {topic}"):
                    c1, c2 = st.columns(2)

                    if exam_data:
                        c1.text_area(
                            "Exam + Key",
                            format_exam_for_instructor(exam_data),
                            height=260,
                            key=f"k{s_id}",
                        )
                    else:
                        c1.text_area("Exam + Key", e_cont, height=260, key=f"k{s_id}")

                    if student_data:
                        c2.text_area(
                            "Student Submission",
                            format_student_submission(student_data),
                            height=260,
                            key=f"s{s_id}",
                        )
                    else:
                        c2.text_area("Student Submission", s_ans, height=260, key=f"s{s_id}")

                    if feedback:
                        st.info(feedback)
                    if current_score is not None:
                        st.success(f"Current score: {current_score}/100")
                    if grader_note:
                        st.caption(f"Instructor note: {grader_note}")
                    if breakdown_json:
                        parsed_breakdown = parse_json_blob(breakdown_json)
                        if parsed_breakdown:
                            st.json(parsed_breakdown)
                    if st.button("Auto-Grade", key=f"b{s_id}"):
                        if not check_rate_limit(f"autograde_{s_id}", cooldown_seconds=5):
                            st.stop()
                        rubric_prefix = f"RUBRIC:\\n{rubric}\\n\\n" if rubric else ""
                        res = st.session_state.rag.grade_submission(rubric_prefix + e_cont, s_ans)
                        if exam_data and student_data:
                            grading = grade_structured_submission(exam_data, student_data, res)
                            val = grading["final_score"]
                            breakdown_text = json.dumps(grading, ensure_ascii=True)
                        else:
                            val = parse_score_from_text(res)
                            breakdown_text = json.dumps({"legacy_mode": True, "parsed_score": val}, ensure_ascii=True)

                        conn = get_db_connection()
                        cur = conn.cursor()
                        cur.execute(
                            """
                            UPDATE submissions
                            SET ai_feedback = %s, numerical_score = %s, score_breakdown = %s,
                                graded_by = %s, graded_at = CURRENT_TIMESTAMP
                            WHERE id = %s
                            """,
                            (res, val, breakdown_text, user["id"], s_id),
                        )
                        conn.commit()
                        cur.close()
                        conn.close()
                        audit_event(user["id"], "submission_graded", {"submission_id": s_id, "exam_id": exam_id, "score": val})
                        st.rerun()

                    override_score = st.number_input(
                        "Manual override score",
                        min_value=0,
                        max_value=100,
                        value=int(current_score) if current_score is not None else 0,
                        step=1,
                        key=f"ovr_score_{s_id}",
                    )
                    override_note = st.text_input(
                        "Override note",
                        value=grader_note or "",
                        key=f"ovr_note_{s_id}",
                    )
                    if st.button("Save Override", key=f"ovr_btn_{s_id}"):
                        conn = get_db_connection()
                        cur = conn.cursor()
                        cur.execute(
                            """
                            UPDATE submissions
                            SET numerical_score = %s, grader_note = %s,
                                graded_by = %s, graded_at = CURRENT_TIMESTAMP,
                                ai_feedback = COALESCE(ai_feedback, %s)
                            WHERE id = %s
                            """,
                            (int(override_score), override_note or None, user["id"], "Manually graded by instructor.", s_id),
                        )
                        conn.commit()
                        cur.close()
                        conn.close()
                        audit_event(user["id"], "submission_override", {"submission_id": s_id, "score": int(override_score)})
                        st.rerun()

        with tab4:
            st.header("Class Performance Analytics")

            conn = get_db_connection()
            query = """
                SELECT e.topic, s.numerical_score, u.username, s.submitted_at
                FROM submissions s
                JOIN exams e ON s.exam_id = e.id
                JOIN users u ON s.student_id = u.id
                WHERE e.created_by = %s AND s.numerical_score IS NOT NULL
            """
            df = pd.read_sql(query, conn, params=(user["id"],))
            conn.close()

            if not df.empty:
                col1, col2 = st.columns(2)

                with col1:
                    st.subheader("Average Score per Topic")
                    avg_scores = df.groupby("topic")["numerical_score"].mean()
                    st.bar_chart(avg_scores)

                with col2:
                    st.subheader("Score Distribution")
                    st.line_chart(df["numerical_score"])

                st.subheader("Student Leaderboard")
                leaderboard = (
                    df.groupby("username")["numerical_score"].mean().sort_values(ascending=False)
                )
                st.table(leaderboard)
                st.download_button(
                    "Download analytics CSV",
                    data=df.to_csv(index=False),
                    file_name="analytics_export.csv",
                    mime="text/csv",
                )
            else:
                st.info("No graded data available for analytics yet.")

    else:
        require_role(user, ["student"])
        st.title("Student Portal")
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, topic, difficulty, content, due_at, rubric, source_refs
            FROM exams
            WHERE status='published' AND (due_at IS NULL OR due_at > CURRENT_TIMESTAMP)
            ORDER BY id DESC
            """
        )
        exams = cur.fetchall()
        cur.close()
        conn.close()

        if exams:
            ex = st.selectbox("Choose Exam", exams, format_func=lambda x: f"{x[1]} ({x[2]})")
            exam_id, exam_topic, exam_difficulty, exam_content, due_at, rubric, source_refs = ex
            if due_at:
                st.caption(f"Due: {due_at}")
            if rubric:
                st.caption("Rubric available for grading.")
            if source_refs:
                try:
                    st.caption("Sources: " + ", ".join(json.loads(source_refs)))
                except Exception:
                    pass

            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT student_answers, ai_feedback FROM submissions WHERE exam_id=%s AND student_id=%s",
                (exam_id, user["id"]),
            )
            done = cur.fetchone()
            cur.close()
            conn.close()

            exam_data = parse_json_blob(exam_content)

            if done:
                st.warning("Already submitted")
                submitted_answers = done[0] if done else ""
                feedback = done[1] if done else None

                submitted_structured = parse_json_blob(submitted_answers)
                if submitted_structured:
                    st.text_area(
                        "Your Submission",
                        format_student_submission(submitted_structured),
                        height=260,
                    )
                else:
                    st.text_area("Your Submission", submitted_answers or "", height=260)

                if feedback:
                    st.success(f"Feedback: {feedback}")
            else:
                if exam_data and (exam_data.get("mcqs") or exam_data.get("essays")):
                    st.subheader(f"{exam_topic} ({exam_difficulty})")

                    with st.form(f"exam_form_{exam_id}"):
                        mcq_answers = []
                        for i, mcq in enumerate(exam_data.get("mcqs", []), start=1):
                            st.markdown(f"**MCQ {i}. {mcq.get('question', '')}**")
                            options = mcq.get("options", [])
                            selected = st.radio(
                                label=f"Choose one option for MCQ {i}",
                                options=list(range(len(options))),
                                format_func=lambda idx, opts=options: opts[idx],
                                key=f"mcq_{exam_id}_{i}",
                            )
                            mcq_answers.append(
                                {
                                    "id": mcq.get("id", f"MCQ-{i}"),
                                    "question": mcq.get("question", ""),
                                    "selected_option_index": int(selected),
                                    "selected_option": options[int(selected)] if options else "",
                                }
                            )

                        essay_answers = []
                        for i, essay in enumerate(exam_data.get("essays", []), start=1):
                            st.markdown(f"**Essay {i}. {essay.get('question', '')}**")
                            answer_text = st.text_area(
                                label=f"Your answer for Essay {i}",
                                key=f"essay_{exam_id}_{i}",
                            )
                            essay_answers.append(
                                {
                                    "id": essay.get("id", f"ESSAY-{i}"),
                                    "question": essay.get("question", ""),
                                    "answer": answer_text,
                                }
                            )

                        submit_exam = st.form_submit_button("Submit Exam")

                    if submit_exam:
                        conn = get_db_connection()
                        cur = conn.cursor()
                        cur.execute("SELECT due_at FROM exams WHERE id=%s", (exam_id,))
                        due_row = cur.fetchone()
                        if due_row and due_row[0] and due_row[0] <= datetime.now():
                            cur.close()
                            conn.close()
                            st.error("This exam is closed.")
                            st.stop()
                        payload = {
                            "mcq_answers": mcq_answers,
                            "essay_answers": essay_answers,
                        }
                        cur.execute(
                            "INSERT INTO submissions (exam_id, student_id, student_answers) VALUES (%s,%s,%s)",
                            (exam_id, user["id"], json.dumps(payload, ensure_ascii=True)),
                        )
                        conn.commit()
                        cur.close()
                        conn.close()
                        audit_event(user["id"], "submission_created", {"exam_id": exam_id})
                        st.success("Exam submitted")
                        st.rerun()
                else:
                    st.warning("This exam is in legacy text format. Ask instructor to regenerate it for form mode.")
                    st.text_area("Exam", exam_content, height=280)
                    ans = st.text_area("Answers")
                    if st.button("Submit"):
                        conn = get_db_connection()
                        cur = conn.cursor()
                        cur.execute(
                            "INSERT INTO submissions (exam_id, student_id, student_answers) VALUES (%s,%s,%s)",
                            (exam_id, user["id"], ans),
                        )
                        conn.commit()
                        cur.close()
                        conn.close()
                        audit_event(user["id"], "submission_created_legacy", {"exam_id": exam_id})
                        st.rerun()
        else:
            st.info("No published exams available right now.")
