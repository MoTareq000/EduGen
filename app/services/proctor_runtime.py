from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProctorRuntimeState:
    session_id: str
    focus_score: float = 100.0
    total_alerts: int = 0
    high_alerts: int = 0
    medium_alerts: int = 0
    invalidated: bool = False
    invalidate_reason: str = ""
    last_alert_ts: dict[str, float] = field(default_factory=dict)
    no_face_frames: int = 0
    away_frames: int = 0
    no_face_seconds: float = 0.0
    away_seconds: float = 0.0
    frame_count: int = 0
    latest_metrics: dict[str, Any] = field(default_factory=dict)
    started_at_epoch: float = field(default_factory=time.time)
    last_frame_ts: float = field(default_factory=time.time)
    ended: bool = False


class ProctorRuntimeStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._states: dict[str, ProctorRuntimeState] = {}

    def create_or_reset(self, session_id: str) -> ProctorRuntimeState:
        state = ProctorRuntimeState(session_id=session_id)
        with self._lock:
            self._states[session_id] = state
        return state

    def get(self, session_id: str) -> ProctorRuntimeState | None:
        with self._lock:
            return self._states.get(session_id)

    def end(self, session_id: str) -> ProctorRuntimeState | None:
        with self._lock:
            state = self._states.get(session_id)
            if state:
                state.ended = True
            return state


runtime_store = ProctorRuntimeStore()
