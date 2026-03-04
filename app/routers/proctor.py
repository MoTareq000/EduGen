from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas import (
    ProctorEndRequest,
    ProctorFrameRequest,
    ProctorInvalidateRequest,
    ProctorStartRequest,
)
from app.services.audit_service import audit_event
from app.services.proctor_cv_service import decode_frame, process_frame_and_update_state
from app.services.proctor_runtime import runtime_store
from app.services.proctor_service import (
    create_proctor_session,
    ensure_exam_for_student,
    ensure_instructor,
    ensure_student,
    finalize_proctor_session,
    get_proctor_alerts,
    get_proctor_session,
    insert_proctor_alert,
    invalidate_session,
    list_instructor_proctor_sessions,
)

router = APIRouter(prefix="/proctor", tags=["proctor"])


@router.post("/sessions/start")
def start_session(payload: ProctorStartRequest):
    ensure_student(payload.student_id)
    ensure_exam_for_student(payload.exam_id)
    created = create_proctor_session(
        student_id=payload.student_id,
        exam_id=payload.exam_id,
        student_name=payload.student_name,
        exam_title=payload.exam_title,
        duration_min=payload.duration_min,
    )
    runtime_store.create_or_reset(created["id"])
    audit_event(
        payload.student_id,
        "proctor_session_started",
        {"session_id": created["id"], "exam_id": payload.exam_id},
    )
    return {
        "session_id": created["id"],
        "started_at": created["started_at"],
        "status": "active",
    }


@router.post("/sessions/{session_id}/frame")
def process_frame(session_id: str, payload: ProctorFrameRequest):
    session = get_proctor_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Proctor session not found")
    if session.get("ended_at"):
        raise HTTPException(status_code=400, detail="Proctor session already ended")

    state = runtime_store.get(session_id)
    if state is None:
        state = runtime_store.create_or_reset(session_id)

    try:
        bgr = decode_frame(payload.image_base64)
        metrics, alert = process_frame_and_update_state(state, bgr)
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"CV dependencies unavailable: {exc}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Frame processing failed: {exc}")

    if alert:
        insert_proctor_alert(session_id, alert)

    return {
        "session_id": session_id,
        "frame_count": state.frame_count,
        "no_face_seconds": round(state.no_face_seconds, 2),
        "away_seconds": round(state.away_seconds, 2),
        "focus_score": round(state.focus_score, 2),
        "total_alerts": state.total_alerts,
        "high_alerts": state.high_alerts,
        "medium_alerts": state.medium_alerts,
        "invalidated": state.invalidated,
        "invalidate_reason": state.invalidate_reason or None,
        "metrics": metrics,
        "alert": alert,
    }


@router.post("/sessions/{session_id}/end")
def end_session(session_id: str, payload: ProctorEndRequest | None = None):
    session = get_proctor_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Proctor session not found")

    state = runtime_store.end(session_id)
    if state is None:
        focus_score = float(session.get("focus_score_final") or 100.0)
        total_alerts = int(session.get("total_alerts") or 0)
        high_alerts = int(session.get("high_alerts") or 0)
        medium_alerts = int(session.get("medium_alerts") or 0)
        invalidated = bool(session.get("invalidated"))
        invalidate_reason = session.get("invalidate_reason")
    else:
        if payload and payload.invalidate_reason and not state.invalidate_reason:
            state.invalidated = True
            state.invalidate_reason = payload.invalidate_reason
        focus_score = state.focus_score
        total_alerts = state.total_alerts
        high_alerts = state.high_alerts
        medium_alerts = state.medium_alerts
        invalidated = state.invalidated
        invalidate_reason = state.invalidate_reason

    finalize_proctor_session(
        session_id=session_id,
        focus_score_final=focus_score,
        total_alerts=total_alerts,
        high_alerts=high_alerts,
        medium_alerts=medium_alerts,
        invalidated=invalidated,
        invalidate_reason=invalidate_reason,
    )
    audit_event(
        session.get("student_id"),
        "proctor_session_ended",
        {"session_id": session_id, "invalidated": invalidated},
    )
    return {
        "session_id": session_id,
        "status": "ended",
        "focus_score_final": round(focus_score, 2),
        "total_alerts": total_alerts,
        "high_alerts": high_alerts,
        "medium_alerts": medium_alerts,
        "invalidated": invalidated,
        "invalidate_reason": invalidate_reason,
    }


@router.get("/sessions/{session_id}")
def session_details(session_id: str):
    session = get_proctor_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Proctor session not found")
    state = runtime_store.get(session_id)
    return {
        "session": session,
        "runtime": {
            "frame_count": state.frame_count,
            "no_face_seconds": round(state.no_face_seconds, 2),
            "away_seconds": round(state.away_seconds, 2),
            "focus_score": round(state.focus_score, 2),
            "total_alerts": state.total_alerts,
            "high_alerts": state.high_alerts,
            "medium_alerts": state.medium_alerts,
            "invalidated": state.invalidated,
            "invalidate_reason": state.invalidate_reason or None,
            "latest_metrics": state.latest_metrics,
        }
        if state
        else None,
    }


@router.get("/sessions/{session_id}/alerts")
def session_alerts(session_id: str):
    if not get_proctor_session(session_id):
        raise HTTPException(status_code=404, detail="Proctor session not found")
    return {"alerts": get_proctor_alerts(session_id)}


@router.post("/sessions/{session_id}/invalidate")
def instructor_invalidate_session(session_id: str, payload: ProctorInvalidateRequest):
    ensure_instructor(payload.instructor_id)
    session = get_proctor_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Proctor session not found")
    invalidate_session(session_id, payload.reason)
    state = runtime_store.get(session_id)
    if state:
        state.invalidated = True
        state.invalidate_reason = payload.reason or "Exam manually invalidated by instructor."
    audit_event(
        payload.instructor_id,
        "proctor_session_invalidated",
        {"session_id": session_id, "reason": payload.reason},
    )
    return {"session_id": session_id, "invalidated": True, "reason": payload.reason}


@router.get("/instructors/{instructor_id}/sessions")
def instructor_sessions(instructor_id: int, limit: int = Query(default=200, ge=1, le=1000)):
    ensure_instructor(instructor_id)
    return {"sessions": list_instructor_proctor_sessions(instructor_id=instructor_id, limit=limit)}
