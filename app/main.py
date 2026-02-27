from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import FRONTEND_DIR
from app.db.schema import ensure_runtime_schema
from app.routers import audit, auth, exams, frontend, health, instructors, rag, submissions

app = FastAPI(title="Road Project Backend", version="2.0.0")
app.state.startup_errors = []


@app.on_event("startup")
def on_startup():
    try:
        ensure_runtime_schema()
    except Exception as exc:
        app.state.startup_errors.append(f"Database startup failed: {exc}")


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


app.include_router(frontend.router)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(rag.router)
app.include_router(exams.router)
app.include_router(submissions.router)
app.include_router(instructors.router)
app.include_router(audit.router)
