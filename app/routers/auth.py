from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.schemas import LoginRequest, RegisterRequest
from app.db.connection import get_db_connection
from app.services.audit_service import audit_event
from app.services.oauth_service import (
    build_authorize_url,
    exchange_code_for_token,
    get_oauth_profile,
    get_oauth_providers,
    login_or_create_oauth_user,
    verify_oauth_state,
)
from app.services.security_service import hash_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/oauth/providers")
def oauth_providers():
    providers = get_oauth_providers()
    return {
        "providers": {
            k: {"label": v["label"], "configured": bool(v["client_id"] and v["client_secret"])}
            for k, v in providers.items()
        }
    }


@router.get("/oauth/{provider}/start")
def oauth_start(provider: str, role: str = Query(default="student")):
    if role not in ("student", "instructor"):
        raise HTTPException(status_code=400, detail="Invalid role")
    providers = get_oauth_providers()
    cfg = providers.get(provider)
    if not cfg:
        raise HTTPException(status_code=404, detail="Unknown OAuth provider")
    if not cfg["client_id"] or not cfg["client_secret"]:
        raise HTTPException(status_code=400, detail=f"{provider} OAuth is not configured")
    return {"authorize_url": build_authorize_url(provider, cfg, role)}


@router.get("/oauth/{provider}/callback")
def oauth_callback(
    provider: str,
    code: str,
    state: str,
    exchange: bool = Query(default=False),
):
    if not exchange:
        # Browser callback path from OAuth provider.
        # Redirect to frontend and let JS perform the token exchange request.
        return RedirectResponse(
            url=f"/?provider={provider}&code={code}&state={state}",
            status_code=307,
        )

    providers = get_oauth_providers()
    cfg = providers.get(provider)
    if not cfg:
        raise HTTPException(status_code=404, detail="Unknown OAuth provider")
    if not cfg["client_id"] or not cfg["client_secret"]:
        raise HTTPException(status_code=400, detail=f"{provider} OAuth is not configured")

    state_payload = verify_oauth_state(provider, state)
    if not state_payload:
        raise HTTPException(status_code=400, detail="OAuth state mismatch")

    try:
        access_token = exchange_code_for_token(provider, cfg, code)
        profile = get_oauth_profile(provider, cfg, access_token)
        user = login_or_create_oauth_user(profile, fallback_role=state_payload.get("role", "student"))
        audit_event(user["id"], "login_oauth_success", {"provider": provider})
        return {"message": "OAuth login successful", "provider": provider, "user": user}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OAuth login failed: {exc}")


@router.post("/register")
def register(payload: RegisterRequest):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM users WHERE username=%s", (payload.username,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Username already exists")

        cur.execute(
            "INSERT INTO users (username, password, role, email) VALUES (%s, %s, %s, %s) RETURNING id",
            (payload.username, hash_password(payload.password), payload.role, payload.email),
        )
        user_id = cur.fetchone()[0]
        conn.commit()
        audit_event(user_id, "local_signup", {"username": payload.username, "role": payload.role})
        return {"id": user_id, "username": payload.username, "role": payload.role}
    finally:
        cur.close()
        conn.close()


@router.post("/login")
def login(payload: LoginRequest):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, username, role FROM users WHERE username=%s AND password=%s",
            (payload.username, hash_password(payload.password)),
        )
        user = cur.fetchone()
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        audit_event(user[0], "login_local_success", {"username": user[1]})
        return {"id": user[0], "username": user[1], "role": user[2]}
    finally:
        cur.close()
        conn.close()
