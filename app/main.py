from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import FRONTEND_DIR, get_config_value
from app.db.schema import ensure_runtime_schema
from app.routers import audit, auth, exams, frontend, health, instructors, proctor, rag, stats, submissions, text_to_sql

app = FastAPI(title="Road Project Backend", version="2.0.0")
app.state.startup_errors = []

cors_origins_raw = get_config_value("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173")
allow_origins = [origin.strip() for origin in cors_origins_raw.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
app.include_router(text_to_sql.router)
app.include_router(stats.router)
app.include_router(proctor.router)
