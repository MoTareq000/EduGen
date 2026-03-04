from __future__ import annotations

import base64
import binascii
import importlib
import time
from datetime import datetime
from functools import lru_cache
from typing import Any

import cv2
import numpy as np

from app.services.proctor_runtime import ProctorRuntimeState

# Landmark indices (copied from CV_project/app.py)
_NOSE = 1
_LEFT_EAR = 234
_RIGHT_EAR = 454
_L_EYE_OUT = 33
_L_EYE_IN = 133
_R_EYE_OUT = 362
_R_EYE_IN = 263
_L_IRIS = [468, 469, 470, 471, 472]
_R_IRIS = [473, 474, 475, 476, 477]

# Alert cooldown seconds per type (copied from CV_project/app.py)
_COOLDOWN = {"no_face": 7, "multiple_faces": 6, "head_turn": 8, "looking_away": 8}


@lru_cache(maxsize=1)
def _load_face_mesh() -> Any:
    mp_solutions = None
    for mod in ("mediapipe.solutions", "mediapipe.python.solutions"):
        try:
            mp_solutions = importlib.import_module(mod)
            break
        except ModuleNotFoundError:
            pass
    if mp_solutions is None:
        raise ImportError("MediaPipe solutions module not found. Use Python 3.10/3.11 and install mediapipe==0.10.14.")

    mp_fm = mp_solutions.face_mesh
    return mp_fm.FaceMesh(
        max_num_faces=2,
        refine_landmarks=True,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )


def decode_frame(image_base64: str) -> np.ndarray:
    payload = image_base64
    if "," in payload:
        payload = payload.split(",", 1)[1]
    try:
        raw = base64.b64decode(payload)
    except (ValueError, binascii.Error) as exc:
        raise ValueError(f"Invalid base64 image payload: {exc}")

    arr = np.frombuffer(raw, dtype=np.uint8)
    bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError("Unable to decode image bytes")
    return bgr


def analyse_frame(bgr: np.ndarray) -> dict[str, Any]:
    face_mesh = _load_face_mesh()
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    res = face_mesh.process(rgb)
    faces = res.multi_face_landmarks or []

    data: dict[str, Any] = dict(
        face_detected=False,
        multi_face=False,
        looking_away=False,
        gaze_x=0.5,
        gaze_y=0.5,
        head_yaw=0.0,
        confidence=0.0,
        alert_type=None,
        alert_msg=None,
        alert_severity=None,
    )

    if not faces:
        data.update(
            alert_type="no_face",
            alert_msg="Face not visible in camera frame",
            alert_severity="high",
        )
        return data

    data["face_detected"] = True
    if len(faces) > 1:
        data["multi_face"] = True
        data["alert_type"] = "multiple_faces"
        data["alert_msg"] = "Multiple faces detected - possible identity fraud"
        data["alert_severity"] = "high"

    lm = faces[0].landmark

    def lx(i: int) -> float:
        return lm[i].x

    def ly(i: int) -> float:
        return lm[i].y

    def avg_iris(ids: list[int]) -> tuple[float, float]:
        valid = [i for i in ids if i < len(lm)]
        if not valid:
            return 0.5, 0.5
        return (
            sum(lm[i].x for i in valid) / len(valid),
            sum(lm[i].y for i in valid) / len(valid),
        )

    nose_x = lx(_NOSE)
    face_w = abs(lx(_RIGHT_EAR) - lx(_LEFT_EAR)) + 1e-6
    mid_x = (lx(_LEFT_EAR) + lx(_RIGHT_EAR)) / 2
    head_yaw = (nose_x - mid_x) / (face_w / 2)

    gaze_off = 0.0
    has_iris = len(lm) > 473
    if has_iris:
        lcx, _ = avg_iris(_L_IRIS)
        rcx, _ = avg_iris(_R_IRIS)
        lew = abs(lx(_L_EYE_OUT) - lx(_L_EYE_IN)) + 1e-6
        rew = abs(lx(_R_EYE_OUT) - lx(_R_EYE_IN)) + 1e-6
        l_off = (lcx - (lx(_L_EYE_OUT) + lx(_L_EYE_IN)) / 2) / lew
        r_off = (rcx - (lx(_R_EYE_OUT) + lx(_R_EYE_IN)) / 2) / rew
        gaze_off = (l_off + r_off) / 2

    looking_away = abs(head_yaw) > 0.35 or abs(gaze_off) > 0.55
    confidence = float(np.clip(1.0 - abs(head_yaw) * 2, 0, 1))

    data.update(
        looking_away=looking_away,
        gaze_x=float(np.clip(0.5 + gaze_off, 0, 1)),
        gaze_y=float(ly(_NOSE)),
        head_yaw=float(head_yaw),
        confidence=confidence,
    )

    if looking_away and not data["alert_type"]:
        t = "head_turn" if abs(head_yaw) > 0.35 else "looking_away"
        data.update(
            alert_type=t,
            alert_msg=("Head turned away from screen" if t == "head_turn" else "Gaze moved off screen"),
            alert_severity="medium",
        )

    return data


def _can_alert(state: ProctorRuntimeState, atype: str) -> bool:
    now = time.time()
    cd = _COOLDOWN.get(atype, 8)
    if now - state.last_alert_ts.get(atype, 0) >= cd:
        state.last_alert_ts[atype] = now
        return True
    return False


def _push_alert(state: ProctorRuntimeState, atype: str, msg: str, severity: str) -> dict[str, Any] | None:
    if not _can_alert(state, atype):
        return None

    if severity == "high":
        state.high_alerts += 1
        state.focus_score = max(0, state.focus_score - 8)
    elif severity == "medium":
        state.medium_alerts += 1
        state.focus_score = max(0, state.focus_score - 4)
    state.total_alerts += 1

    if state.high_alerts >= 3:
        state.invalidated = True
        state.invalidate_reason = "Exam auto-invalidated: 3 or more high-severity violations detected."

    return {
        "time": datetime.utcnow().isoformat(),
        "type": atype,
        "message": msg,
        "severity": severity,
    }


def process_frame_and_update_state(state: ProctorRuntimeState, bgr: np.ndarray) -> tuple[dict[str, Any], dict[str, Any] | None]:
    now_ts = time.time()
    delta = max(0.0, now_ts - state.last_frame_ts)
    # Cap large gaps to avoid single delayed frame creating exaggerated penalties.
    delta = min(delta, 1.0)
    state.last_frame_ts = now_ts

    data = analyse_frame(bgr)

    state.frame_count += 1
    state.latest_metrics = data

    if (not data["face_detected"]) or data["looking_away"]:
        state.focus_score = max(0.0, state.focus_score - 0.12)
    else:
        state.focus_score = min(100.0, state.focus_score + 0.04)

    if not data["face_detected"]:
        state.no_face_frames += 1
        state.no_face_seconds += delta
        state.away_frames = 0
        state.away_seconds = 0.0
    elif data["looking_away"]:
        state.away_frames += 1
        state.away_seconds += delta
        state.no_face_frames = 0
        state.no_face_seconds = 0.0
    else:
        state.no_face_frames = 0
        state.away_frames = max(0, state.away_frames - 1)
        state.no_face_seconds = 0.0
        state.away_seconds = max(0.0, state.away_seconds - delta)

    alert_record: dict[str, Any] | None = None
    if data.get("alert_type") and data.get("alert_msg"):
        nfs = state.no_face_seconds
        afs = state.away_seconds
        # Streamlit used frame-based thresholds; web clients have variable FPS.
        # Convert sustained conditions to time windows for stable behavior.
        if data["alert_type"] == "no_face" and nfs >= 1.5:
            alert_record = _push_alert(state, "no_face", data["alert_msg"], "high")
        elif data["alert_type"] == "multiple_faces":
            alert_record = _push_alert(state, "multiple_faces", data["alert_msg"], "high")
        elif data["alert_type"] in ("head_turn", "looking_away") and afs >= 2.0:
            sev = "high" if afs >= 5.0 else "medium"
            alert_record = _push_alert(state, data["alert_type"], data["alert_msg"], sev)

    return data, alert_record
