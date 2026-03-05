import hashlib
import hmac
import json
import re
import secrets
import time
from urllib.parse import urlencode

import requests

from app.core.config import get_config_value
from app.db.connection import get_db_connection
from app.services.audit_service import audit_event
from app.services.security_service import hash_password


def get_app_base_url() -> str:
    return get_config_value("APP_BASE_URL", "http://localhost:8000").rstrip("/")


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


def oauth_redirect_uri(provider: str) -> str:
    return f"{get_app_base_url()}/auth/oauth/{provider}/callback"


def oauth_state_secret() -> str:
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


def build_oauth_state(provider: str, role: str) -> str:
    safe_role = role if role in ("student", "instructor") else "student"
    payload = {
        "provider": provider,
        "role": safe_role,
        "nonce": secrets.token_urlsafe(8),
        "iat": int(time.time()),
    }
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    sig = hmac.new(
        oauth_state_secret().encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{body}.{sig}"


def verify_oauth_state(provider: str, token: str, max_age_seconds: int = 900):
    if not token or "." not in token:
        return None

    body, sig = token.rsplit(".", 1)
    expected_sig = hmac.new(
        oauth_state_secret().encode("utf-8"),
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


def build_authorize_url(provider: str, cfg: dict[str, str], role: str) -> str:
    state = build_oauth_state(provider, role)
    params = {
        "client_id": cfg["client_id"],
        "redirect_uri": oauth_redirect_uri(provider),
        "response_type": "code",
        "scope": cfg["scope"],
        "state": state,
    }
    return f"{cfg['authorize_url']}?{urlencode(params)}"


def exchange_code_for_token(provider: str, cfg: dict[str, str], code: str) -> str:
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


def get_oauth_profile(provider: str, cfg: dict[str, str], access_token: str):
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


def login_or_create_oauth_user(profile: dict[str, str], fallback_role: str = "student"):
    provider = profile.get("provider", "")
    subject = profile.get("subject", "")
    email = (profile.get("email", "") or "").strip()
    display_name = profile.get("display_name", "")

    if not provider or not subject:
        raise RuntimeError("Invalid OAuth profile")

    username_base = (email or display_name or f"{provider}_user").strip()
    username_base = re.sub(r"\s+", "_", username_base)
    if not username_base:
        username_base = f"{provider}_user"

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            "SELECT id, username, role, email FROM users WHERE oauth_provider=%s AND oauth_subject=%s",
            (provider, subject),
        )
        user = cur.fetchone()
        if user:
            if email and (not user[3] or user[3].lower() != email.lower()):
                cur.execute("UPDATE users SET email=%s WHERE id=%s", (email, user[0]))
                conn.commit()
            return {"id": user[0], "username": user[1], "role": user[2], "email": email or user[3]}

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
                    audit_event(linked[0], "oauth_account_linked", {"provider": provider})
                    return {"id": linked[0], "username": linked[1], "role": linked[2], "email": email}
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
        audit_event(created[0], "oauth_account_created", {"provider": provider, "role": role})
        return {"id": created[0], "username": created[1], "role": created[2], "email": email}
    finally:
        cur.close()
        conn.close()
