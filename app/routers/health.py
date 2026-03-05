from fastapi import APIRouter, Request

from app.core.config import get_config_value
from app.db.schema import db_health_ok
from app.services.oauth_service import get_oauth_providers

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request):
    providers = get_oauth_providers()
    startup_errors = getattr(request.app.state, "startup_errors", [])
    return {
        "status": "ok" if not startup_errors else "degraded",
        "service": "fastapi-backend",
        "startup_errors": startup_errors,
        "checks": {
            "database": "ok" if db_health_ok() else "error",
            "groq_api": "ok" if bool(get_config_value("GROQ_API_KEY", "")) else "missing",
            "google_oauth": "ok"
            if providers["google"]["client_id"] and providers["google"]["client_secret"]
            else "missing",
            "github_oauth": "ok"
            if providers["github"]["client_id"] and providers["github"]["client_secret"]
            else "missing",
        },
    }
