

import streamlit as st
import cv2
import mediapipe as mp
import numpy as np
import pandas as pd
import time
import json
import io
import os
import importlib
import sys
import platform
from datetime import datetime
from PIL import Image
from supabase import create_client


# ══════════════════════════════════════════════════════════════
# SUPABASE (DB) UTILITIES
# ══════════════════════════════════════════════════════════════
def _get_secret(name: str):
    """Read from st.secrets safely (returns None if missing)."""
    try:
        return st.secrets[name]
    except Exception:
        return None

@st.cache_resource
def get_supabase():
    """Create and cache a Supabase client (server-side)."""
    url = os.getenv("SUPABASE_URL") or _get_secret("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or _get_secret("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None
    return create_client(url, key)

def db_create_session():
    """Insert a new row in proctor_sessions and return session id (uuid)."""
    sb = get_supabase()
    if sb is None:
        return None
    payload = {
        "student_name": st.session_state.student_name,
        "exam_title": st.session_state.exam_title,
        "duration_min": int(st.session_state.duration_min),
        "started_at": datetime.fromtimestamp(st.session_state.exam_start).isoformat()
                      if st.session_state.exam_start else datetime.now().isoformat(),
    }
    res = sb.table("proctor_sessions").insert(payload).execute()
    data = getattr(res, "data", None) or []
    return data[0]["id"] if data else None

def db_insert_alert(session_id, entry):
    """Insert one alert row linked to session_id."""
    sb = get_supabase()
    if sb is None or not session_id:
        return
    sb.table("proctor_alerts").insert({
        "session_id": session_id,
        "type": entry["type"],
        "message": entry["message"],
        "severity": entry["severity"],
        # 'at' uses default now() in DB
    }).execute()

def db_finalize_session(session_id):
    """Update proctor_sessions with end time + final stats."""
    sb = get_supabase()
    if sb is None or not session_id:
        return
    sb.table("proctor_sessions").update({
        "ended_at": datetime.now().isoformat(),
        "focus_score_final": float(st.session_state.focus_score),
        "total_alerts": int(st.session_state.total_alerts),
        "high_alerts": int(st.session_state.high_alerts),
        "medium_alerts": int(st.session_state.medium_alerts),
        "invalidated": bool(st.session_state.invalidated),
        "invalidate_reason": st.session_state.invalidate_reason,
    }).eq("id", session_id).execute()

def finalize_if_needed():
    """Call db_finalize_session once (safe to call multiple times)."""
    if st.session_state.get("session_finalized", False):
        return
    sid = st.session_state.get("session_id")
    if sid:
        db_finalize_session(sid)
    st.session_state.session_finalized = True

# ══════════════════════════════════════════════════════════════
# ROBUST CAMERA UTILITIES
# ══════════════════════════════════════════════════════════════

def _get_backends():
    """Return list of (backend_id, backend_name) to try in order for this OS."""
    os_name = platform.system()
    if os_name == "Windows":
        return [
            (cv2.CAP_DSHOW,   "DirectShow (Windows)"),
            (cv2.CAP_MSMF,    "Media Foundation (Windows)"),
            (cv2.CAP_ANY,     "Auto-detect"),
        ]
    elif os_name == "Darwin":
        return [
            (cv2.CAP_AVFOUNDATION, "AVFoundation (Mac)"),
            (cv2.CAP_ANY,          "Auto-detect"),
        ]
    else:  # Linux
        return [
            (cv2.CAP_V4L2,  "V4L2 (Linux)"),
            (cv2.CAP_ANY,   "Auto-detect"),
        ]


def find_working_camera(max_index: int = 5):
    """
    Scan camera indices 0..max_index with every OS-appropriate backend.
    Returns (cv2.VideoCapture, index, backend_name) or (None, -1, reason).
    """
    backends = _get_backends()
    tried = []

    for idx in range(max_index):
        for backend_id, backend_name in backends:
            try:
                cap = cv2.VideoCapture(idx, backend_id)
                if not cap.isOpened():
                    cap.release()
                    tried.append(f"index={idx} backend={backend_name} → not opened")
                    continue

                # Try to actually grab a frame — some drivers open but give nothing
                cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                ok, frame = cap.read()
                if not ok or frame is None or frame.size == 0:
                    cap.release()
                    tried.append(f"index={idx} backend={backend_name} → opened but no frame")
                    continue

                # SUCCESS
                return cap, idx, backend_name

            except Exception as exc:
                tried.append(f"index={idx} backend={backend_name} → exception: {exc}")
                continue

    reason = "\n".join(tried) if tried else "No cameras found."
    return None, -1, reason


def camera_diagnostics():
    """
    Show a detailed diagnostic panel so the user knows exactly
    what is wrong with their camera setup.
    """
    st.markdown("## 🔍 Camera Diagnostics")
    st.error("❌ **No working camera was found.** See the diagnosis below.")

    os_name  = platform.system()
    py_ver   = sys.version.split()[0]
    cv2_ver  = cv2.__version__

    st.markdown(f"""
    <div class='info-card'>
        <b>System Info</b><br>
        OS: <code>{os_name}</code> &nbsp;|&nbsp;
        Python: <code>{py_ver}</code> &nbsp;|&nbsp;
        OpenCV: <code>{cv2_ver}</code>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### 🔎 Scanning All Camera Indices…")
    found_any = False
    for idx in range(6):
        cols = st.columns([1, 3])
        for backend_id, backend_name in _get_backends():
            try:
                cap = cv2.VideoCapture(idx, backend_id)
                opened = cap.isOpened()
                if opened:
                    ok, frame = cap.read()
                    has_frame = ok and frame is not None and frame.size > 0
                else:
                    has_frame = False
                cap.release()

                if opened and has_frame:
                    st.success(f"✅ **Camera index {idx}** works with **{backend_name}**")
                    found_any = True
                elif opened:
                    st.warning(f"⚠️ Camera index {idx} opens with {backend_name} but returns no frames")
                # silently skip "not opened"
            except Exception as e:
                st.error(f"❌ Camera index {idx} / {backend_name}: `{e}`")

    if not found_any:
        st.error("🚫 **No camera index returned a usable frame.**")

    st.divider()
    st.markdown("### 🛠️ How to Fix")

    fixes = {
        "Windows": [
            "**Close other apps** using the camera: Zoom, Teams, Discord, OBS, Skype.",
            "Go to **Settings → Privacy & Security → Camera** and make sure apps are allowed.",
            "Open **Device Manager → Imaging Devices** and check your camera is listed with no ⚠️ icon.",
            "Try updating your camera driver: right-click the camera in Device Manager → Update driver.",
            "If you have an **antivirus** (Kaspersky, Bitdefender…), it may be blocking camera access — check its settings.",
            "Try **restarting your computer** — another process may have locked the camera.",
        ],
        "Darwin": [
            "Go to **System Settings → Privacy & Security → Camera** and enable access for Terminal/VS Code.",
            "Close FaceTime, Photo Booth, Zoom, Teams or any app using the camera.",
            "Try running: `sudo killall VDCAssistant` in Terminal, then restart the app.",
            "Make sure you're on **macOS 10.15+**.",
        ],
        "Linux": [
            "Run `ls /dev/video*` — if nothing shows, the camera is not detected by the OS.",
            "Run `sudo usermod -aG video $USER` then **log out and back in**.",
            "Try installing: `sudo apt install v4l-utils` then `v4l2-ctl --list-devices`.",
            "Try `sudo apt install libopencv-dev` if OpenCV was installed without V4L2 support.",
        ],
    }

    for i, fix in enumerate(fixes.get(os_name, fixes["Linux"]), 1):
        st.markdown(f"**{i}.** {fix}")

    st.divider()
    st.markdown("### 🔄 Manual Camera Index Override")
    st.markdown("If you know your camera index, enter it here to force it:")
    manual_idx = st.number_input("Camera Index", min_value=0, max_value=10, value=0, step=1)
    if st.button("🔁 Retry with this index", type="primary"):
        st.session_state["cam_index_override"] = int(manual_idx)
        st.session_state.running = True
        st.rerun()

    if st.button("🔁 Retry Auto-Detection"):
        st.session_state.running = True
        st.rerun()


def open_camera():
    """
    Open the camera, respecting any manual override set by the user.
    Returns (cv2.VideoCapture, label_str) or (None, error_str).
    """
    override = st.session_state.get("cam_index_override", None)

    if override is not None:
        # User manually specified an index — try every backend for that index
        for backend_id, backend_name in _get_backends():
            try:
                cap = cv2.VideoCapture(override, backend_id)
                if cap.isOpened():
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    ok, frame = cap.read()
                    if ok and frame is not None and frame.size > 0:
                        return cap, f"Camera {override} via {backend_name}"
                cap.release()
            except Exception:
                continue
        return None, f"Camera index {override} could not be opened with any backend."

    # Auto-scan
    cap, idx, info = find_working_camera()
    if cap is not None:
        return cap, f"Camera {idx} via {info}"
    return None, info


# ══════════════════════════════════════════════════════════════
# PAGE CONFIGURATION
# ══════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="EyeGuard — AI Proctoring",
    page_icon="👁",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ══════════════════════════════════════════════════════════════
# STYLING
# ══════════════════════════════════════════════════════════════
st.markdown("""
<style>
/* ── global ── */
html, body, [data-testid="stAppViewContainer"] {
    background-color: #0a0d12;
    color: #e2e8f0;
}
[data-testid="stSidebar"] {
    background-color: #0d1117;
    border-right: 1px solid #1e2530;
}
/* ── headings ── */
h1, h2, h3 { color: #e2e8f0 !important; }

/* ── metric cards ── */
[data-testid="metric-container"] {
    background: #0d1117;
    border: 1px solid #1e2530;
    border-radius: 12px;
    padding: 10px 16px !important;
}
[data-testid="stMetricValue"] { color: #00e5ff !important; font-weight: 700; }
[data-testid="stMetricLabel"] { color: #64748b !important; }

/* ── buttons ── */
.stButton > button {
    border-radius: 10px;
    font-weight: 700;
    border: none;
    transition: opacity .2s, transform .2s;
}
.stButton > button:hover { opacity: .85; transform: translateY(-1px); }

/* ── selectbox / text_input ── */
[data-testid="stTextInput"] input,
[data-testid="stSelectbox"] select,
.stSelectbox > div > div {
    background: #0d1117 !important;
    border: 1px solid #1e2530 !important;
    border-radius: 8px !important;
    color: #e2e8f0 !important;
}

/* ── progress bar ── */
[data-testid="stProgress"] > div { border-radius: 8px; }

/* ── divider ── */
hr { border-color: #1e2530 !important; }

/* ── dataframe ── */
[data-testid="stDataFrame"] { border: 1px solid #1e2530; border-radius: 10px; }

/* ── hide streamlit branding ── */
#MainMenu, footer, [data-testid="stStatusWidget"] { visibility: hidden; }

/* ── custom badges ── */
.badge-ok   { display:inline-block; background:#10b98122; border:1px solid #10b98155;
              border-radius:6px; padding:3px 10px; color:#34d399; font-size:.82rem; font-weight:600; }
.badge-warn { display:inline-block; background:#f59e0b22; border:1px solid #f59e0b55;
              border-radius:6px; padding:3px 10px; color:#fbbf24; font-size:.82rem; font-weight:600; }
.badge-bad  { display:inline-block; background:#ef444422; border:1px solid #ef444455;
              border-radius:6px; padding:3px 10px; color:#f87171; font-size:.82rem; font-weight:600; }
.badge-info { display:inline-block; background:#7c3aed22; border:1px solid #7c3aed55;
              border-radius:6px; padding:3px 10px; color:#a78bfa; font-size:.82rem; font-weight:600; }

/* ── alert row colours ── */
.alert-high   { color:#ef4444; font-weight:700; }
.alert-medium { color:#f59e0b; font-weight:700; }
.alert-low    { color:#10b981; font-weight:600; }

/* ── card ── */
.info-card {
    background:#0d1117; border:1px solid #1e2530; border-radius:14px;
    padding:18px 22px; margin-bottom:10px;
}
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
# SESSION STATE — initialise every key we need
# ══════════════════════════════════════════════════════════════
_DEFAULTS = {
    "page":             "home",       # home | student | instructor
    "running":          False,
    "student_name":     "",
    "exam_title":       "Midterm CS101",
    "duration_min":     60,
    "exam_start":       None,

    # DB session (Supabase)
    "session_id":       None,
    "session_finalized": False,

    # per-frame gaze data
    "face_detected":    False,
    "multi_face":       False,
    "looking_away":     False,
    "gaze_x":           0.5,
    "gaze_y":           0.5,
    "head_yaw":         0.0,
    "confidence":       0.0,

    # sustained-frame counters
    "no_face_frames":   0,
    "away_frames":      0,
    "frame_count":      0,

    # scoring & alerts
    "focus_score":      100.0,
    "alerts":           [],           # list[dict]
    "last_alert_ts":    {},           # type -> float timestamp
    "total_alerts":     0,
    "high_alerts":      0,
    "medium_alerts":    0,

    # instructor-side data (mirrors student state for demo)
    "instructor_session_active": False,
    "instructor_student_data":   {},  # name -> latest snapshot
    "instructor_alert_feed":     [],

    # invalidation
    "invalidated":      False,
    "invalidate_reason":"",

    # camera
    "cam_index_override": None,
}

for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ══════════════════════════════════════════════════════════════
# MEDIAPIPE — load once and cache
# ══════════════════════════════════════════════════════════════

# Some environments/package builds may not expose `mp.solutions` at top-level.
try:
    mp_solutions = mp.solutions
except AttributeError:
    mp_solutions = None
    for _mod in ("mediapipe.solutions", "mediapipe.python.solutions"):
        try:
            mp_solutions = importlib.import_module(_mod)
            break
        except ModuleNotFoundError:
            pass
    if mp_solutions is None:
        raise ImportError("MediaPipe solutions module not found. Use Python 3.10/3.11 and install mediapipe==0.10.14.")
@st.cache_resource(show_spinner="Loading AI model…")
def _load_face_mesh():
    mp_fm = mp_solutions.face_mesh
    fm = mp_fm.FaceMesh(
        max_num_faces=2,
        refine_landmarks=True,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    return fm

face_mesh = _load_face_mesh()

# Landmark indices
_NOSE        = 1
_LEFT_EAR    = 234
_RIGHT_EAR   = 454
_L_EYE_OUT   = 33;  _L_EYE_IN = 133
_R_EYE_OUT   = 362; _R_EYE_IN = 263
_L_IRIS      = [468, 469, 470, 471, 472]
_R_IRIS      = [473, 474, 475, 476, 477]

# Alert cooldown seconds per type
_COOLDOWN = {"no_face": 7, "multiple_faces": 6, "head_turn": 8, "looking_away": 8}

# ══════════════════════════════════════════════════════════════
# CORE: analyse a single BGR frame
# ══════════════════════════════════════════════════════════════
def analyse_frame(bgr):
    """Return (annotated_rgb, data_dict)."""
    h, w = bgr.shape[:2]
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    res = face_mesh.process(rgb)
    ann = rgb.copy()

    data = dict(face_detected=False, multi_face=False, looking_away=False,
                gaze_x=0.5, gaze_y=0.5, head_yaw=0.0, confidence=0.0,
                alert_type=None, alert_msg=None, alert_severity=None)

    faces = res.multi_face_landmarks or []

    # ── NO FACE ────────────────────────────────────────────
    if not faces:
        overlay = ann.copy()
        cv2.rectangle(overlay, (0,0), (w, h), (200, 30, 30), -1)
        ann = cv2.addWeighted(ann, 0.75, overlay, 0.25, 0)
        cv2.putText(ann, "NO FACE DETECTED", (w//2 - 160, h//2),
                    cv2.FONT_HERSHEY_DUPLEX, 1.1, (255, 80, 80), 2)
        data.update(alert_type="no_face",
                    alert_msg="Face not visible in camera frame",
                    alert_severity="high")
        return ann, data

    data["face_detected"] = True

    # ── MULTIPLE FACES ─────────────────────────────────────
    if len(faces) > 1:
        data["multi_face"]     = True
        data["alert_type"]     = "multiple_faces"
        data["alert_msg"]      = "Multiple faces detected — possible identity fraud"
        data["alert_severity"] = "high"

    lm = faces[0].landmark

    def lx(i): return lm[i].x
    def ly(i): return lm[i].y

    def avg_iris(ids):
        valid = [i for i in ids if i < len(lm)]
        if not valid: return 0.5, 0.5
        return (sum(lm[i].x for i in valid)/len(valid),
                sum(lm[i].y for i in valid)/len(valid))

    # head yaw via nose/ear symmetry
    nose_x  = lx(_NOSE)
    face_w  = abs(lx(_RIGHT_EAR) - lx(_LEFT_EAR)) + 1e-6
    mid_x   = (lx(_LEFT_EAR) + lx(_RIGHT_EAR)) / 2
    head_yaw = (nose_x - mid_x) / (face_w / 2)

    # iris gaze offset
    gaze_off = 0.0
    has_iris = len(lm) > 473
    if has_iris:
        lcx, lcy = avg_iris(_L_IRIS)
        rcx, rcy = avg_iris(_R_IRIS)
        lew = abs(lx(_L_EYE_OUT) - lx(_L_EYE_IN)) + 1e-6
        rew = abs(lx(_R_EYE_OUT) - lx(_R_EYE_IN)) + 1e-6
        l_off = (lcx - (lx(_L_EYE_OUT)+lx(_L_EYE_IN))/2) / lew
        r_off = (rcx - (lx(_R_EYE_OUT)+lx(_R_EYE_IN))/2) / rew
        gaze_off = (l_off + r_off) / 2

    looking_away = abs(head_yaw) > 0.35 or abs(gaze_off) > 0.55
    confidence   = float(np.clip(1.0 - abs(head_yaw)*2, 0, 1))

    data.update(looking_away=looking_away,
                gaze_x=float(np.clip(0.5 + gaze_off, 0, 1)),
                gaze_y=float(ly(_NOSE)),
                head_yaw=float(head_yaw),
                confidence=confidence)

    if looking_away and not data["alert_type"]:
        t = "head_turn" if abs(head_yaw) > 0.35 else "looking_away"
        data.update(alert_type=t,
                    alert_msg=("Head turned away from screen" if t=="head_turn"
                               else "Gaze moved off screen"),
                    alert_severity="medium")

    # ── DRAW ANNOTATIONS ───────────────────────────────────
    dot_colour = (239, 68, 68) if (data["multi_face"] or looking_away) else (0, 229, 255)

    # bounding box
    xs = [int(lm[i].x*w) for i in range(min(len(lm),468))]
    ys = [int(lm[i].y*h) for i in range(min(len(lm),468))]
    pad = 10
    x1,y1,x2,y2 = max(0,min(xs)-pad),max(0,min(ys)-pad),min(w,max(xs)+pad),min(h,max(ys)+pad)
    cv2.rectangle(ann, (x1,y1), (x2,y2), dot_colour, 2)

    # key points
    for idx in [_L_EYE_OUT,_L_EYE_IN,_R_EYE_OUT,_R_EYE_IN,_NOSE,_LEFT_EAR,_RIGHT_EAR]:
        if idx < len(lm):
            cv2.circle(ann, (int(lm[idx].x*w), int(lm[idx].y*h)), 3, dot_colour, -1)

    # iris rings
    if has_iris:
        for iris_ids in [_L_IRIS, _R_IRIS]:
            cx, cy = avg_iris(iris_ids)
            cv2.circle(ann, (int(cx*w), int(cy*h)), 9, dot_colour, 2)

    # head-yaw arrow
    nose_px = (int(lx(_NOSE)*w), int(ly(_NOSE)*h))
    arrow_x = int(nose_px[0] + head_yaw * 80)
    cv2.arrowedLine(ann, nose_px, (arrow_x, nose_px[1]),
                    (255,200,0), 2, tipLength=0.3)

    # status label
    label     = "FOCUSED ✓" if not looking_away else "LOOKING AWAY ✗"
    lbl_color = (16,185,129) if not looking_away else (239,68,68)
    cv2.rectangle(ann, (0, h-36), (w, h), (10,14,20), -1)
    cv2.putText(ann, label, (10, h-10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, lbl_color, 2)

    # gaze dot on bottom bar
    bar_left, bar_right = 180, w-10
    gx = int(bar_left + data["gaze_x"] * (bar_right - bar_left))
    cv2.rectangle(ann, (bar_left, h-20), (bar_right, h-14), (30,40,55), -1)
    cv2.circle(ann, (gx, h-17), 7, dot_colour, -1)

    # confidence text
    cv2.putText(ann, f"conf {confidence:.2f}", (bar_left, h-22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100,120,150), 1)

    return ann, data

# ══════════════════════════════════════════════════════════════
# ALERT HELPERS
# ══════════════════════════════════════════════════════════════
def _can_alert(atype):
    now = time.time()
    cd  = _COOLDOWN.get(atype, 8)
    if now - st.session_state.last_alert_ts.get(atype, 0) >= cd:
        st.session_state.last_alert_ts[atype] = now
        return True
    return False


def push_alert(atype, msg, severity):
    if not _can_alert(atype):
        return
    entry = dict(time=datetime.now().strftime("%H:%M:%S"),
                 type=atype, message=msg, severity=severity)
    st.session_state.alerts.append(entry)
    db_insert_alert(st.session_state.get("session_id"), entry)
    st.session_state.total_alerts  += 1
    st.session_state.instructor_alert_feed.insert(0, entry)

    if severity == "high":
        st.session_state.high_alerts   += 1
        st.session_state.focus_score    = max(0, st.session_state.focus_score - 8)
    elif severity == "medium":
        st.session_state.medium_alerts += 1
        st.session_state.focus_score    = max(0, st.session_state.focus_score - 4)

    # Auto-invalidate after 3 high-severity alerts
    if st.session_state.high_alerts >= 3:
        st.session_state.invalidated      = True
        st.session_state.invalidate_reason = "Exam auto-invalidated: 3 or more high-severity violations detected."


def update_focus(looking_away):
    if looking_away:
        st.session_state.focus_score = max(0.0,   st.session_state.focus_score - 0.12)
    else:
        st.session_state.focus_score = min(100.0, st.session_state.focus_score + 0.04)

# ══════════════════════════════════════════════════════════════
# TIME HELPERS
# ══════════════════════════════════════════════════════════════
def elapsed_str():
    if not st.session_state.exam_start: return "00:00"
    s = int(time.time() - st.session_state.exam_start)
    return f"{s//60:02d}:{s%60:02d}"

def remaining_str():
    if not st.session_state.exam_start: return "--:--"
    left = max(0, st.session_state.duration_min*60 - int(time.time()-st.session_state.exam_start))
    return f"{left//60:02d}:{left%60:02d}"

def time_is_up():
    if not st.session_state.exam_start: return False
    return (time.time() - st.session_state.exam_start) >= st.session_state.duration_min * 60

# ══════════════════════════════════════════════════════════════
# REPORT BUILDER
# ══════════════════════════════════════════════════════════════
def build_report_csv():
    if not st.session_state.alerts:
        return pd.DataFrame(columns=["Time","Type","Message","Severity"]).to_csv(index=False).encode()
    return pd.DataFrame(st.session_state.alerts).to_csv(index=False).encode()

def build_report_json():
    report = {
        "student":       st.session_state.student_name,
        "exam":          st.session_state.exam_title,
        "duration_min":  st.session_state.duration_min,
        "started_at":    datetime.fromtimestamp(st.session_state.exam_start).isoformat()
                         if st.session_state.exam_start else None,
        "focus_score":   round(st.session_state.focus_score, 1),
        "total_alerts":  st.session_state.total_alerts,
        "high_alerts":   st.session_state.high_alerts,
        "medium_alerts": st.session_state.medium_alerts,
        "invalidated":   st.session_state.invalidated,
        "alerts":        st.session_state.alerts,
    }
    return json.dumps(report, indent=2).encode()

# ══════════════════════════════════════════════════════════════
# SIDEBAR NAVIGATION
# ══════════════════════════════════════════════════════════════
def render_sidebar_nav():
    with st.sidebar:
        st.markdown("""
        <div style='text-align:center;padding:1rem 0 0.5rem;'>
            <span style='font-size:2rem;'>👁</span>
            <h2 style='margin:0;color:#00e5ff;font-size:1.4rem;'>EyeGuard</h2>
            <p style='color:#64748b;font-size:0.78rem;margin:0;'>AI Proctoring System</p>
        </div>
        """, unsafe_allow_html=True)
        st.divider()

        pages = {"🏠  Home": "home", "📝  Student Portal": "student", "🎓  Instructor View": "instructor"}
        for label, key in pages.items():
            active = st.session_state.page == key
            if st.button(label, use_container_width=True,
                         type="primary" if active else "secondary"):
                st.session_state.page    = key
                st.session_state.running = False
                st.rerun()

        st.divider()
        st.markdown("<p style='color:#64748b;font-size:0.75rem;text-align:center;'>Powered by MediaPipe + OpenCV</p>",
                    unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
# PAGE: HOME
# ══════════════════════════════════════════════════════════════
def page_home():
    st.markdown("""
    <div style='text-align:center;padding:3rem 0 1.5rem;'>
        <div style='font-size:5rem;line-height:1;'>👁</div>
        <h1 style='font-size:3rem;font-weight:900;letter-spacing:-1px;
                   background:linear-gradient(135deg,#e2e8f0,#00e5ff);
                   -webkit-background-clip:text;-webkit-text-fill-color:transparent;'>
            EyeGuard
        </h1>
        <p style='color:#64748b;font-size:1.1rem;max-width:520px;margin:0 auto;'>
            AI-Powered Exam Proctoring · Real-Time Eye & Gaze Tracking
        </p>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("""
        <div class='info-card'>
            <h3 style='color:#a78bfa;'>🎓 Instructor</h3>
            <p style='color:#94a3b8;'>Monitor students live, receive instant gaze alerts,
            send warnings, clear students, and export full session reports.</p>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Open Instructor View →", use_container_width=True, type="primary"):
            st.session_state.page = "instructor"
            st.rerun()

    with c2:
        st.markdown("""
        <div class='info-card'>
            <h3 style='color:#00e5ff;'>📝 Student</h3>
            <p style='color:#94a3b8;'>Join your exam. Your webcam will track eye and gaze
            movements locally — no video is ever transmitted.</p>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Join as Student →", use_container_width=True):
            st.session_state.page = "student"
            st.rerun()

    st.divider()
    st.markdown("### ⚙️ Detection Capabilities")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.info("**🚫 No Face**\n\nDetected when student leaves frame or covers camera.")
    with col2:
        st.warning("**👥 Multi-Face**\n\nFlags when more than one person is visible.")
    with col3:
        st.error("**↩️ Head Turn**\n\nHead yaw > 35° triggers a gaze-away alert.")
    with col4:
        st.success("**👀 Gaze Drift**\n\nIris position drift > 55% from center.")

    st.divider()
    st.markdown("### 📋 Alert Escalation Logic")
    df = pd.DataFrame({
        "Condition":       ["Head turn > 35°",  "Gaze off-screen", "No face in frame", "Multiple faces"],
        "Severity":        ["Medium",            "Medium",          "High",             "High"],
        "Auto-Invalidate": ["After 3 High",      "After 3 High",    "After 3 High",     "Immediate warning"],
        "Cooldown":        ["8 sec",             "8 sec",           "7 sec",            "6 sec"],
    })
    st.dataframe(df, use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════
# PAGE: STUDENT
# ══════════════════════════════════════════════════════════════
def page_student():

    # live download placeholders (updated inside the webcam loop)
    csv_dl_ph = None
    json_dl_ph = None
    last_alerts_len = -1
    live_report_path = None

    # ── sidebar controls ───────────────────────────────────
    with st.sidebar:
        st.markdown("### 📝 Student Setup")
        name = st.text_input("Full Name", value=st.session_state.student_name,
                             placeholder="e.g. Jane Smith")
        exam = st.text_input("Exam Title", value=st.session_state.exam_title)
        dur  = st.selectbox("Duration", [30, 45, 60, 90, 120],
                             index=[30,45,60,90,120].index(st.session_state.duration_min)
                             if st.session_state.duration_min in [30,45,60,90,120] else 2,
                             format_func=lambda x: f"{x} minutes")
        st.divider()

        if not st.session_state.running:
            if st.button("▶ Start Monitoring", type="primary", use_container_width=True):
                if not name.strip():
                    st.error("Please enter your name.")
                else:
                    st.session_state.student_name   = name.strip()
                    st.session_state.exam_title      = exam.strip()
                    st.session_state.duration_min    = dur
                    st.session_state.running         = True
                    st.session_state.exam_start      = time.time()
                    st.session_state.alerts          = []
                    st.session_state.focus_score     = 100.0
                    st.session_state.total_alerts    = 0
                    st.session_state.high_alerts     = 0
                    st.session_state.medium_alerts   = 0
                    st.session_state.frame_count     = 0
                    st.session_state.no_face_frames  = 0
                    st.session_state.away_frames     = 0
                    st.session_state.last_alert_ts   = {}
                    st.session_state.invalidated     = False
                    st.session_state.invalidate_reason = ""
                    st.session_state.instructor_alert_feed = []
                    st.session_state.session_finalized = False
                    st.session_state.session_id = db_create_session()
                    st.rerun()
        else:
            if st.button("⏹ Stop Session", use_container_width=True):
                finalize_if_needed()
                st.session_state.running = False
                st.rerun()

            st.divider()
            st.markdown("#### 📥 Download Report")
            csv_dl_ph = st.empty()
            json_dl_ph = st.empty()
            safe_name = (st.session_state.student_name or "student").replace(" ", "_")
            live_report_path = os.path.join(os.getcwd(), f"eyeguard_{safe_name}_live.csv")

            # initial buttons (they will refresh automatically when new alerts appear)
            csv_dl_ph.download_button(
                "⬇ CSV Report",
                build_report_csv(),
                file_name=f"eyeguard_{safe_name}.csv",
                mime="text/csv",
                use_container_width=True,
                key=f"csv_{len(st.session_state.alerts)}",
            )
            json_dl_ph.download_button(
                "⬇ JSON Report",
                build_report_json(),
                file_name=f"eyeguard_{safe_name}.json",
                mime="application/json",
                use_container_width=True,
                key=f"json_{len(st.session_state.alerts)}",
            )

            # baseline so we don't recreate the same widget key in the first loop iteration
            last_alerts_len = len(st.session_state.alerts)

            st.caption("Buttons refresh automatically when a new alert is recorded.")
            st.caption(f"Auto-saved live CSV: {live_report_path}")

        st.divider()
        st.markdown("#### 🎥 Camera Settings")
        override = st.session_state.get("cam_index_override", None)
        if override is not None:
            st.markdown(f"<span class='badge-info'>Using camera index {override}</span>",
                        unsafe_allow_html=True)
            if st.button("🔄 Reset to Auto-Detect", use_container_width=True):
                st.session_state["cam_index_override"] = None
                st.rerun()
        else:
            st.markdown("<span class='badge-ok'>Auto-detect mode</span>",
                        unsafe_allow_html=True)
        manual_idx = st.number_input("Force camera index (0, 1, 2…)",
                                     min_value=0, max_value=10,
                                     value=int(override) if override is not None else 0,
                                     step=1,
                                     help="Try 0 first, then 1, 2 if the camera doesn't open")
        if st.button("✅ Apply Index", use_container_width=True):
            st.session_state["cam_index_override"] = int(manual_idx)
            st.rerun()

    # ── main area ─────────────────────────────────────────
    st.markdown(f"## 📝 {st.session_state.exam_title}")

    # ── invalidated ───────────────────────────────────────
    if st.session_state.invalidated:
        st.error(f"""
        ## 🚫 Exam Invalidated
        **{st.session_state.invalidate_reason}**

        Please contact your instructor immediately.
        """)
        st.markdown("#### 📊 Session Summary")
        finalize_if_needed()
        _render_summary()
        return

    if not st.session_state.running:
        st.info("👈 Fill in your details in the sidebar and click **▶ Start Monitoring** to begin.")
        st.divider()
        _render_sample_questions()
        return

    # ── time up ───────────────────────────────────────────
    if time_is_up():
        st.success("### ⏰ Time is up! Your exam has ended.")
        st.session_state.running = False
        finalize_if_needed()
        _render_summary()
        return

    # ── top metrics (LIVE) ───────────────────────────────────────
    m1c, m2c, m3c, m4c, m5c = st.columns(5)
    m1_ph = m1c.empty()
    m2_ph = m2c.empty()
    m3_ph = m3c.empty()
    m4_ph = m4c.empty()
    m5_ph = m5c.empty()
    progress_ph = st.empty()

    def _update_top_ui():
        fs = st.session_state.focus_score
        m1_ph.metric("🎯 Focus Score",   f"{fs:.1f}%")
        m2_ph.metric("⏱ Elapsed",        elapsed_str())
        m3_ph.metric("⏳ Remaining",     remaining_str())
        m4_ph.metric("⚠️ Total Alerts",  st.session_state.total_alerts)
        m5_ph.metric("🔴 High Alerts",   st.session_state.high_alerts)

        # focus progress bar
        bar_col = "#10b981" if fs >= 70 else "#f59e0b" if fs >= 40 else "#ef4444"
        progress_ph.markdown(f"""
        <div style='margin:4px 0 14px;'>
            <div style='height:8px;background:#1e2530;border-radius:999px;'>
                <div style='width:{fs:.1f}%;height:100%;background:{bar_col};
                            border-radius:999px;transition:width .25s;'></div>
            </div>
        </div>""", unsafe_allow_html=True)

    _update_top_ui()


    st.divider()

    left_col, right_col = st.columns([3, 2], gap="large")

    # ── LEFT: camera feed ─────────────────────────────────
    with left_col:
        st.markdown("#### 📷 Live Camera Feed")
        frame_placeholder = st.empty()
        status_placeholder = st.empty()

    # ── RIGHT: stats + alert log ──────────────────────────
    with right_col:
        st.markdown("#### 📊 Gaze Stats")
        gaze_ph   = st.empty()
        st.markdown("#### ⚠️ Alert Log")
        log_ph    = st.empty()

    st.divider()
    st.markdown("#### 📋 Exam Questions")
    _render_sample_questions()

    # ══════════════════════════════════════════════
    # WEBCAM LOOP
    # ══════════════════════════════════════════════
    with st.spinner("🔍 Searching for camera…"):
        cap, cam_label = open_camera()

    if cap is None:
        st.session_state.running = False
        camera_diagnostics()
        return

    st.success(f"✅ Camera opened: **{cam_label}**")

    try:
        while st.session_state.running and not time_is_up() and not st.session_state.invalidated:

            ret, frame = cap.read()
            if not ret:
                st.warning("⚠️ Lost camera feed.")
                break

            frame = cv2.flip(frame, 1)          # mirror so it feels natural
            annotated, data = analyse_frame(frame)

            # ── update state ──────────────────────────────
            st.session_state.frame_count   += 1
            st.session_state.face_detected  = data["face_detected"]
            st.session_state.multi_face     = data["multi_face"]
            st.session_state.looking_away   = data["looking_away"]
            st.session_state.gaze_x         = data["gaze_x"]
            st.session_state.gaze_y         = data["gaze_y"]
            st.session_state.head_yaw       = data["head_yaw"]
            st.session_state.confidence     = data["confidence"]
            update_focus(data["looking_away"])

            # ── sustained-frame counters ──────────────────
            if not data["face_detected"]:
                st.session_state.no_face_frames += 1
                st.session_state.away_frames     = 0
            elif data["looking_away"]:
                st.session_state.away_frames    += 1
                st.session_state.no_face_frames  = 0
            else:
                st.session_state.no_face_frames  = 0
                st.session_state.away_frames     = max(0, st.session_state.away_frames - 1)

            # ── fire alerts ───────────────────────────────
            if data["alert_type"] and data["alert_msg"]:
                nff = st.session_state.no_face_frames
                aff = st.session_state.away_frames
                # fire only after a few sustained frames (reduces false positives)
                if data["alert_type"] == "no_face" and nff >= 10:
                    sev = "high" if nff >= 30 else "medium"
                    push_alert("no_face", data["alert_msg"], sev)

                elif data["alert_type"] == "multiple_faces":
                    push_alert("multiple_faces", data["alert_msg"], "high")

                elif data["alert_type"] in ("head_turn", "looking_away") and aff >= 20:
                    sev = "high" if aff >= 60 else "medium"
                    push_alert(data["alert_type"], data["alert_msg"], sev)

            # ── render camera frame ───────────────────────
            frame_placeholder.image(annotated, channels="RGB",
                                    use_container_width=True)

            # ── status badge ──────────────────────────────
            if not data["face_detected"]:
                status_placeholder.markdown(
                    "<span class='badge-bad'>🚫 No Face Detected</span>", unsafe_allow_html=True)
            elif data["multi_face"]:
                status_placeholder.markdown(
                    "<span class='badge-bad'>👥 Multiple Faces</span>", unsafe_allow_html=True)
            elif data["looking_away"]:
                status_placeholder.markdown(
                    "<span class='badge-warn'>👀 Looking Away</span>", unsafe_allow_html=True)
            else:
                status_placeholder.markdown(
                    "<span class='badge-ok'>✅ Focused</span>", unsafe_allow_html=True)

            # ── gaze stats panel ──────────────────────────
            yaw_deg  = data["head_yaw"] * 90
            conf_pct = data["confidence"] * 100
            gaze_pct = data["gaze_x"] * 100
            gaze_ph.markdown(f"""
            <div class='info-card'>
                <table style='width:100%;font-size:.85rem;color:#94a3b8;border-collapse:collapse;'>
                    <tr><td>Face Detected</td>
                        <td style='text-align:right;color:{"#10b981" if data["face_detected"] else "#ef4444"};font-weight:700;'>
                            {"✅ Yes" if data["face_detected"] else "🚫 No"}</td></tr>
                    <tr><td>Multi-Face</td>
                        <td style='text-align:right;color:{"#ef4444" if data["multi_face"] else "#10b981"};font-weight:700;'>
                            {"⚠️ YES" if data["multi_face"] else "✅ No"}</td></tr>
                    <tr><td>Looking Away</td>
                        <td style='text-align:right;color:{"#f59e0b" if data["looking_away"] else "#10b981"};font-weight:700;'>
                            {"⚠️ YES" if data["looking_away"] else "✅ No"}</td></tr>
                    <tr><td>Head Yaw</td>
                        <td style='text-align:right;color:#00e5ff;font-family:monospace;'>
                            {yaw_deg:+.1f}°</td></tr>
                    <tr><td>Gaze Position</td>
                        <td style='text-align:right;color:#00e5ff;font-family:monospace;'>
                            {gaze_pct:.1f}%</td></tr>
                    <tr><td>Confidence</td>
                        <td style='text-align:right;color:#00e5ff;font-family:monospace;'>
                            {conf_pct:.1f}%</td></tr>
                    <tr><td>Focus Score</td>
                        <td style='text-align:right;color:{"#10b981" if st.session_state.focus_score>=70 else "#f59e0b" if st.session_state.focus_score>=40 else "#ef4444"};font-weight:700;'>
                            {st.session_state.focus_score:.1f}%</td></tr>
                    <tr><td>Frames Analysed</td>
                        <td style='text-align:right;color:#64748b;font-family:monospace;'>
                            {st.session_state.frame_count}</td></tr>
                </table>
            </div>
            """, unsafe_allow_html=True)

            # ── alert log ─────────────────────────────────
            alerts = st.session_state.alerts
            if not alerts:
                log_ph.markdown(
                    "<div class='info-card'><p style='color:#64748b;font-size:.85rem;'>No alerts yet. Stay focused!</p></div>",
                    unsafe_allow_html=True)
            else:
                rows = ""
                for a in reversed(alerts[-15:]):
                    sev   = a["severity"]
                    icon  = "🔴" if sev=="high" else "🟡" if sev=="medium" else "🟢"
                    color = "#ef4444" if sev=="high" else "#f59e0b" if sev=="medium" else "#10b981"
                    rows += f"""
                    <tr>
                        <td style='color:#64748b;font-family:monospace;font-size:.75rem;padding:4px 6px;'>{a["time"]}</td>
                        <td style='padding:4px 6px;'>{icon}</td>
                        <td style='color:{color};font-size:.8rem;padding:4px 6px;'>{a["message"]}</td>
                    </tr>"""
                log_ph.markdown(f"""
                <div class='info-card' style='max-height:280px;overflow-y:auto;'>
                    <table style='width:100%;border-collapse:collapse;'>{rows}</table>
                </div>""", unsafe_allow_html=True)

            # ── live UI updates (metrics + live downloads) ─────────────
            # update top metrics a few times per second to keep CPU reasonable
            if st.session_state.frame_count % 5 == 0:
                _update_top_ui()

            # refresh download buttons + auto-save CSV whenever a new alert is recorded
            if csv_dl_ph is not None and json_dl_ph is not None:
                cur_len = len(st.session_state.alerts)
                if cur_len != last_alerts_len:
                    last_alerts_len = cur_len
                    safe_name = (st.session_state.student_name or "student").replace(" ", "_")

                    csv_bytes = build_report_csv()
                    json_bytes = build_report_json()

                    csv_dl_ph.download_button(
                        "⬇ CSV Report",
                        csv_bytes,
                        file_name=f"eyeguard_{safe_name}.csv",
                        mime="text/csv",
                        use_container_width=True,
                        key=f"csv_{cur_len}",
                    )
                    json_dl_ph.download_button(
                        "⬇ JSON Report",
                        json_bytes,
                        file_name=f"eyeguard_{safe_name}.json",
                        mime="application/json",
                        use_container_width=True,
                        key=f"json_{cur_len}",
                    )

                    # Auto-save a live CSV on disk (same folder you're running Streamlit from)
                    if live_report_path:
                        try:
                            with open(live_report_path, "wb") as f:
                                f.write(csv_bytes)
                        except Exception:
                            pass

            # small pause — keeps CPU reasonable
            time.sleep(0.04)

    finally:
        cap.release()

    # Loop ended
    if time_is_up():
        st.success("### ⏰ Time is up! Exam session ended.")
    elif st.session_state.invalidated:
        st.error(f"### 🚫 {st.session_state.invalidate_reason}")

    finalize_if_needed()
    _render_summary()


# ──────────────────────────────────────────────────────────────
# HELPERS: questions + summary
# ──────────────────────────────────────────────────────────────
def _render_sample_questions():
    questions = [
        ("1. Which data structure uses LIFO ordering?",
         ["A) Queue", "B) Stack", "C) Linked List", "D) Tree"]),
        ("2. What is the time complexity of binary search?",
         ["A) O(n)", "B) O(n²)", "C) O(log n)", "D) O(1)"]),
        ("3. Which sorting algorithm has worst-case O(n log n)?",
         ["A) Bubble Sort", "B) Insertion Sort", "C) Merge Sort", "D) Selection Sort"]),
        ("4. In HTTP, which method is idempotent AND safe?",
         ["A) POST", "B) DELETE", "C) PUT", "D) GET"]),
        ("5. What does SQL stand for?",
         ["A) Sequential Query Logic", "B) Structured Query Language",
          "C) Simple Query Language", "D) Standard Queue Library"]),
    ]
    for q_text, options in questions:
        with st.expander(q_text, expanded=False):
            st.radio("Select your answer:", options, key=f"q_{q_text[:20]}", label_visibility="collapsed")


def _render_summary():
    st.divider()
    st.markdown("### 📊 Session Summary")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Focus Score",    f"{st.session_state.focus_score:.1f}%")
    c2.metric("Total Alerts",   st.session_state.total_alerts)
    c3.metric("High Alerts",    st.session_state.high_alerts)
    c4.metric("Medium Alerts",  st.session_state.medium_alerts)

    if st.session_state.alerts:
        st.markdown("#### 📋 Full Alert Log")
        df = pd.DataFrame(st.session_state.alerts)
        st.dataframe(df, use_container_width=True, hide_index=True)

    col1, col2 = st.columns(2)
    with col1:
        st.download_button("⬇ Download CSV Report", build_report_csv(),
                           file_name="eyeguard_report.csv", mime="text/csv",
                           use_container_width=True)
    with col2:
        st.download_button("⬇ Download JSON Report", build_report_json(),
                           file_name="eyeguard_report.json", mime="application/json",
                           use_container_width=True)

# ══════════════════════════════════════════════════════════════
# PAGE: INSTRUCTOR
# ══════════════════════════════════════════════════════════════
def page_instructor():

    with st.sidebar:
        st.markdown("### 🎓 Instructor Controls")

        if not st.session_state.instructor_session_active:
            inst_name  = st.text_input("Instructor Name", placeholder="Prof. Smith")
            exam_title = st.text_input("Exam Title",      value="Midterm CS101")
            dur = st.selectbox("Duration", [30,45,60,90,120],
                               format_func=lambda x: f"{x} min", index=2)

            if st.button("▶ Activate Session", type="primary", use_container_width=True):
                st.session_state.instructor_session_active = True
                st.session_state.exam_title    = exam_title
                st.session_state.duration_min  = dur
                st.session_state.exam_start    = time.time()
                st.session_state.instructor_alert_feed = []
                st.rerun()
        else:
            st.markdown(f"""
            <div class='info-card'>
                <p style='color:#64748b;font-size:.78rem;margin:0;'>ACTIVE SESSION</p>
                <p style='color:#00e5ff;font-weight:700;margin:4px 0;'>{st.session_state.exam_title}</p>
                <p style='color:#94a3b8;font-size:.85rem;margin:0;'>Elapsed: {elapsed_str()}</p>
            </div>""", unsafe_allow_html=True)

            st.divider()

            # Manual controls (operate on the shared session state)
            st.markdown("#### ⚡ Quick Actions")
            if st.button("✅ Clear Student Warnings", use_container_width=True):
                st.session_state.high_alerts   = 0
                st.session_state.medium_alerts = 0
                st.session_state.focus_score   = min(100, st.session_state.focus_score + 30)
                st.session_state.invalidated   = False
                st.success("Student warnings cleared.")

            warn_msg = st.text_input("Send Warning Message", placeholder="Please focus on the screen…")
            if st.button("📨 Send Warning", use_container_width=True):
                if warn_msg.strip():
                    push_alert("instructor_warning", f"Instructor: {warn_msg.strip()}", "medium")
                    st.success("Warning sent to student log.")

            st.divider()
            if st.button("🚫 Invalidate Exam", use_container_width=True):
                st.session_state.invalidated      = True
                st.session_state.invalidate_reason = "Exam manually invalidated by instructor."
                finalize_if_needed()
                st.error("Exam invalidated.")

            if st.button("⏹ End Session", use_container_width=True):
                finalize_if_needed()
                st.session_state.instructor_session_active = False
                st.session_state.running = False
                st.rerun()

            st.divider()
            st.download_button("⬇ CSV Report", build_report_csv(),
                               file_name="eyeguard_report.csv", mime="text/csv",
                               use_container_width=True)
            st.download_button("⬇ JSON Report", build_report_json(),
                               file_name="eyeguard_report.json", mime="application/json",
                               use_container_width=True)

    # ── MAIN DASHBOARD ────────────────────────────────────
    st.markdown("## 🎓 Instructor Dashboard")

    if not st.session_state.instructor_session_active:
        st.info("👈 Configure and activate a session in the sidebar.")
        return

    # ── top stats ──────────────────────────────────────────
    t1, t2, t3, t4, t5, t6 = st.columns(6)
    t1.metric("⏱ Elapsed",       elapsed_str())
    t2.metric("⏳ Remaining",    remaining_str())
    t3.metric("⚠️ Total Alerts", st.session_state.total_alerts)
    t4.metric("🔴 High",         st.session_state.high_alerts)
    t5.metric("🟡 Medium",       st.session_state.medium_alerts)
    fs = st.session_state.focus_score
    t6.metric("🎯 Focus",        f"{fs:.1f}%")

    # focus progress
    bar_col = "#10b981" if fs>=70 else "#f59e0b" if fs>=40 else "#ef4444"
    st.markdown(f"""
    <div style='margin:4px 0 14px;'>
        <div style='height:8px;background:#1e2530;border-radius:999px;'>
            <div style='width:{fs:.1f}%;height:100%;background:{bar_col};border-radius:999px;'></div>
        </div>
    </div>""", unsafe_allow_html=True)

    st.divider()

    # ── student status card ────────────────────────────────
    st.markdown("### 👤 Student Status")
    if st.session_state.student_name:
        sname = st.session_state.student_name
        if st.session_state.invalidated:
            badge = "<span class='badge-bad'>🚫 INVALIDATED</span>"
        elif st.session_state.high_alerts >= 2:
            badge = "<span class='badge-bad'>🔴 HIGH RISK</span>"
        elif st.session_state.medium_alerts >= 3:
            badge = "<span class='badge-warn'>🟡 WARNING</span>"
        else:
            badge = "<span class='badge-ok'>✅ ACTIVE</span>"

        face_b = "<span class='badge-ok'>👁 Face OK</span>" if st.session_state.face_detected \
                 else "<span class='badge-bad'>🚫 No Face</span>"
        gaze_b = "<span class='badge-warn'>👀 Away</span>"   if st.session_state.looking_away \
                 else "<span class='badge-ok'>✅ Focused</span>"

        st.markdown(f"""
        <div class='info-card'>
            <div style='display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;'>
                <div>
                    <span style='font-size:1.1rem;font-weight:700;color:#e2e8f0;'>{sname}</span>
                    &nbsp;{badge}
                </div>
                <div style='display:flex;gap:8px;flex-wrap:wrap;'>
                    {face_b} &nbsp; {gaze_b}
                </div>
            </div>
            <div style='margin-top:12px;display:flex;gap:24px;font-size:.83rem;color:#94a3b8;'>
                <span>Head Yaw: <b style='color:#00e5ff;'>{st.session_state.head_yaw*90:+.1f}°</b></span>
                <span>Confidence: <b style='color:#00e5ff;'>{st.session_state.confidence*100:.1f}%</b></span>
                <span>Gaze X: <b style='color:#00e5ff;'>{st.session_state.gaze_x*100:.1f}%</b></span>
                <span>Frames: <b style='color:#00e5ff;'>{st.session_state.frame_count}</b></span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info("No student connected yet. Ask the student to open the **Student Portal** tab.")

    st.divider()

    # ── live alert feed ────────────────────────────────────
    feed_col, chart_col = st.columns([3, 2], gap="large")

    with feed_col:
        st.markdown("### ⚡ Live Alert Feed")
        feed = st.session_state.instructor_alert_feed
        if not feed:
            st.markdown("<div class='info-card'><p style='color:#64748b;'>No alerts yet.</p></div>",
                        unsafe_allow_html=True)
        else:
            rows = ""
            for a in feed[:20]:
                sev   = a["severity"]
                icon  = "🔴" if sev=="high" else "🟡" if sev=="medium" else "🟢"
                color = "#ef4444" if sev=="high" else "#f59e0b" if sev=="medium" else "#10b981"
                rows += f"""
                <tr style='border-bottom:1px solid #1e2530;'>
                    <td style='padding:6px 8px;color:#64748b;font-family:monospace;font-size:.75rem;'>{a["time"]}</td>
                    <td style='padding:6px 8px;'>{icon}</td>
                    <td style='padding:6px 8px;color:{color};font-size:.82rem;'>{a["message"]}</td>
                    <td style='padding:6px 8px;'>
                        <span style='background:{color}22;border:1px solid {color}55;border-radius:4px;
                                     padding:2px 6px;font-size:.7rem;color:{color};'>{sev.upper()}</span>
                    </td>
                </tr>"""
            st.markdown(f"""
            <div class='info-card' style='max-height:340px;overflow-y:auto;padding:0;'>
                <table style='width:100%;border-collapse:collapse;'>{rows}</table>
            </div>""", unsafe_allow_html=True)

    with chart_col:
        st.markdown("### 📊 Alert Breakdown")
        if st.session_state.alerts:
            df_alerts = pd.DataFrame(st.session_state.alerts)
            counts = df_alerts.groupby(["type","severity"]).size().reset_index(name="count")
            st.dataframe(counts, use_container_width=True, hide_index=True)

            sev_counts = df_alerts["severity"].value_counts().reset_index()
            sev_counts.columns = ["Severity","Count"]
            st.bar_chart(sev_counts.set_index("Severity"))
        else:
            st.markdown("<div class='info-card'><p style='color:#64748b;'>No data yet.</p></div>",
                        unsafe_allow_html=True)

    st.divider()
    st.markdown("### 📋 Full Alert Table")
    if st.session_state.alerts:
        st.dataframe(pd.DataFrame(st.session_state.alerts),
                     use_container_width=True, hide_index=True)
    else:
        st.info("No alerts recorded yet.")

# ══════════════════════════════════════════════════════════════
# ROUTER
# ══════════════════════════════════════════════════════════════
render_sidebar_nav()

if   st.session_state.page == "home":       page_home()
elif st.session_state.page == "student":    page_student()
elif st.session_state.page == "instructor": page_instructor()