import os
import sys
import time
import logging
import threading
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, List
from collections import deque
import base64
import requests

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

import config
from camera.camera_manager import CameraManager
from detectors.face_verifier import FaceVerifier
from detectors.object_detector import ObjectDetector
from detectors.head_pose_detector import HeadPoseDetector
from audio.audio_manager import AudioManager
from audio.speaker_detector import SpeakerDetector
from violations.logger import ViolationLogger
from violations.violation_manager import ViolationManager
from ui.proctoring_ui import ProctoringUI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("AIProctorService")

app = FastAPI(title="AI Proctoring Service - Multi-Student Architecture", version="2.0.0")

# Enable CORS for all origins (Wi-Fi network access from any device)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class VerifyPhotoRequest(BaseModel):
    photoUrl: Optional[str] = None
    photoBase64: Optional[str] = None
    liveFrameBase64: Optional[str] = None
    cameraIndex: int = -1


class StartSessionRequest(BaseModel):
    testId: str
    studentId: str
    studentName: Optional[str] = ""
    photoUrl: Optional[str] = None
    photoBase64: Optional[str] = None
    backendUrl: Optional[str] = None
    cameraIndex: int = -1


class FrameRequest(BaseModel):
    testId: str
    studentId: str
    frameBase64: str


class StopSessionRequest(BaseModel):
    testId: Optional[str] = None
    studentId: Optional[str] = None


class SessionState:
    """Isolated session state for an individual student in a specific exam."""

    def __init__(self, test_id: str, student_id: str, student_name: str = "", backend_url: str = ""):
        self.lock = threading.RLock()
        self.is_active: bool = True
        self.test_id: str = test_id
        self.student_id: str = student_id
        self.student_name: str = student_name or "Candidate"
        self.backend_url: str = backend_url or config.BACKEND_API_URL
        self.created_at: float = time.time()
        self.last_activity: float = time.time()

        # Independent proctoring components per student
        self.face_verifier: Optional[FaceVerifier] = None
        self.head_pose_detector: Optional[HeadPoseDetector] = None
        self.speaker_detector: Optional[SpeakerDetector] = None
        self.violation_logger: Optional[ViolationLogger] = None
        self.violation_mgr: Optional[ViolationManager] = None
        self.ui_renderer: Optional[ProctoringUI] = None

        # Camera & worker for local hardware mode fallback
        self.camera: Optional[CameraManager] = None
        self.audio_manager: Optional[AudioManager] = None
        self.worker_thread: Optional[threading.Thread] = None
        self.stop_signal: threading.Event = threading.Event()

        # Telemetry & Frame Buffers
        self.latest_frame: Optional[np.ndarray] = None
        self.latest_jpeg: Optional[bytes] = None
        self.total_frames: int = 0
        self.fps: float = 0.0
        self.fps_start_time: float = time.time()
        self.fps_frame_count: int = 0

        self.last_face_result = None
        self.last_obj_results = None
        self.last_head_result = None
        self.last_audio_result = None

        self.telemetry: Dict[str, Any] = {
            "status": "ACTIVE",
            "face_detected": False,
            "face_verified": False,
            "similarity": 0.0,
            "looking_away": False,
            "direction": "CENTER",
            "phone_detected": False,
            "multiple_people": False,
            "book_detected": False,
            "multiple_speakers": False,
            "speaker_count": 0,
            "violations_count": 0,
            "active_violations": [],
            "fps": 0.0,
        }
        self.recent_events: deque = deque(maxlen=50)


# Thread-safe multi-session registry
sessions_lock = threading.RLock()
sessions: Dict[str, SessionState] = {}
last_active_session: Optional[SessionState] = None

# Global shared YOLO Object Detector (Singleton to optimize memory across multiple students)
yolo_lock = threading.RLock()
shared_object_detector: Optional[ObjectDetector] = None

try:
    logger.info("Initializing Shared YOLO Object Detector singleton for multi-candidate proctoring...")
    shared_object_detector = ObjectDetector(model_name=config.YOLO_MODEL, img_size=config.YOLO_IMAGE_SIZE)
    shared_object_detector.start_background_warmup()
    logger.info("Shared YOLO Object Detector initialized successfully.")
except Exception as err:
    logger.error(f"Failed to initialize shared ObjectDetector: {err}")


def get_session_key(test_id: Optional[str], student_id: Optional[str]) -> str:
    t = (test_id or "default").upper().strip()
    s = str(student_id or "default").strip()
    return f"{t}_{s}"


def get_session(test_id: Optional[str] = None, student_id: Optional[str] = None) -> Optional[SessionState]:
    """Retrieves the isolated SessionState matching testId and studentId."""
    with sessions_lock:
        if test_id and student_id:
            key = get_session_key(test_id, student_id)
            if key in sessions:
                return sessions[key]
            # Match by studentId if testId casing slightly differs
            for k, sess in sessions.items():
                if sess.student_id == student_id and sess.is_active:
                    return sess

        if student_id:
            for k, sess in sessions.items():
                if sess.student_id == student_id and sess.is_active:
                    return sess

        # Single active session fallback
        global last_active_session
        if last_active_session and last_active_session.is_active:
            return last_active_session
        for sess in sessions.values():
            if sess.is_active:
                return sess
        return None


def resolve_photo_path(photo_url: Optional[str], photo_base64: Optional[str], student_id: Optional[str] = None) -> Optional[Path]:
    """Resolves student reference photo from URL, Base64, or uploads folder."""
    clean_id = (student_id or "student").replace("/", "_").replace("\\", "_")
    temp_target = config.REFERENCE_DIR / f"{clean_id}_reference.jpg"
    temp_target.parent.mkdir(parents=True, exist_ok=True)

    # 1. Base64
    if photo_base64:
        try:
            raw_b64 = photo_base64.split(",")[-1]
            img_bytes = base64.b64decode(raw_b64)
            with open(temp_target, "wb") as f:
                f.write(img_bytes)
            return temp_target
        except Exception as e:
            logger.warning(f"Failed to decode photoBase64: {e}")

    if not photo_url:
        return None

    # 2. Base64 Data URL
    if photo_url.startswith("data:image"):
        try:
            raw_b64 = photo_url.split(",")[-1]
            img_bytes = base64.b64decode(raw_b64)
            with open(temp_target, "wb") as f:
                f.write(img_bytes)
            return temp_target
        except Exception as e:
            logger.warning(f"Failed to decode photo_url Data URL: {e}")

    # 3. HTTP URL
    if photo_url.startswith("http://") or photo_url.startswith("https://"):
        try:
            r = requests.get(photo_url, timeout=10)
            if r.status_code == 200:
                with open(temp_target, "wb") as f:
                    f.write(r.content)
                return temp_target
        except Exception as e:
            logger.error(f"Failed to fetch photo from HTTP URL {photo_url}: {e}")

    # 4. Local uploads folder in Web/server/uploads
    possible_paths = [
        Path(photo_url),
        config.BASE_DIR.parent.parent / "Web" / "server" / photo_url.lstrip("/"),
        config.BASE_DIR.parent.parent / "Web" / "server" / "uploads" / Path(photo_url).name,
        config.REFERENCE_DIR / Path(photo_url).name,
        config.STUDENT_REFERENCE_IMAGE,
    ]

    for p in possible_paths:
        if p.exists() and p.is_file():
            return p

    return None


def forward_violation_to_backend(sess: SessionState, episode, screenshot_path: Optional[str]):
    """Sends confirmed violation episode and screenshot to Express backend asynchronously for a specific student."""
    friendly_labels = {
        "LOOKING_AWAY": "Looking away",
        "FACE_MISSING": "Face not visible",
        "IDENTITY_MISMATCH": "Identity mismatch",
        "MULTIPLE_PEOPLE": "Multiple people detected",
        "PHONE_DETECTED": "Phone detected",
        "BOOK_DETECTED": "Book detected",
        "MULTIPLE_SPEAKERS": "Multiple voices detected",
    }
    clean_msg = friendly_labels.get(episode.vtype, "Warning detected")

    event_payload = {
        "id": episode.id,
        "type": episode.vtype,
        "message": clean_msg,
        "raw_message": episode.message,
        "timestamp": episode.timestamp_str,
        "similarity": episode.similarity,
        "severity": "critical" if episode.vtype in ["PHONE_DETECTED", "MULTIPLE_PEOPLE", "IDENTITY_MISMATCH"] else "warning"
    }

    with sess.lock:
        sess.recent_events.append(event_payload)

    def _post_worker():
        opened_file = None
        try:
            backend_api = (sess.backend_url or config.BACKEND_API_URL or "http://127.0.0.1:5000/api/proctoring").rstrip("/")
            backend_api = backend_api.replace("localhost", "127.0.0.1")
            url = f"{backend_api}/violation"

            data = {
                "testId": sess.test_id,
                "studentId": sess.student_id,
                "type": episode.vtype,
                "message": episode.message,
                "duration_seconds": episode.duration_seconds or 0,
                "similarity": episode.similarity,
            }

            files = None
            if screenshot_path and os.path.exists(screenshot_path):
                filename = os.path.basename(screenshot_path)
                data["screenshotUrl"] = f"/uploads/{filename}"
                # Also copy screenshot directly to Express uploads folder for fast static serving
                try:
                    server_uploads = config.BASE_DIR.parent.parent / "Web" / "server" / "uploads"
                    server_uploads.mkdir(parents=True, exist_ok=True)
                    dest_path = server_uploads / filename
                    if not dest_path.exists():
                        shutil.copy2(screenshot_path, dest_path)
                except Exception as cp_err:
                    logger.warning(f"Copy screenshot to server uploads notice: {cp_err}")

                opened_file = open(screenshot_path, "rb")
                files = {"screenshot": (filename, opened_file, "image/jpeg")}

            logger.info(f"Forwarding AI violation [{episode.vtype}] for Student [{sess.student_id}] to backend: {url}")
            res = requests.post(url, data=data, files=files, timeout=6)
            logger.info(f"Backend response for Student [{sess.student_id}] violation: {res.status_code}")
            if res.status_code >= 400:
                logger.error(f"Backend returned error {res.status_code} for violation: {res.text}")
        except Exception as e:
            logger.error(f"Failed to post violation to backend ({sess.student_id}): {e}")
        finally:
            if opened_file:
                try:
                    opened_file.close()
                except Exception:
                    pass

    threading.Thread(target=_post_worker, daemon=True).start()


def forward_summary_to_backend(sess: SessionState, notes: str = "AI Proctoring session completed"):
    """Submits the final session summary and risk rating to Express backend in a background worker."""
    def _summary_worker():
        try:
            backend_api = (sess.backend_url or config.BACKEND_API_URL or "http://127.0.0.1:5000/api/proctoring").rstrip("/")
            backend_api = backend_api.replace("localhost", "127.0.0.1")
            url = f"{backend_api}/session-summary"

            with sess.lock:
                active_count = len(sess.recent_events)
                critical_count = sum(1 for e in sess.recent_events if e.get("severity") == "critical")
                test_id = sess.test_id
                student_id = sess.student_id
                looking_away_count = sum(1 for e in sess.recent_events if e.get("type") == config.STATE_LOOKING_AWAY)

            if critical_count >= 1 or active_count >= 4:
                risk_level = "High"
            elif active_count >= 1:
                risk_level = "Medium"
            else:
                risk_level = "Low"

            notes_extra = ""
            if looking_away_count > 0:
                notes_extra = f" | Looking Away: {looking_away_count} times"

            payload = {
                "testId": test_id,
                "studentId": student_id,
                "riskLevel": risk_level,
                "notes": f"{notes}{notes_extra} | Total AI Infractions: {active_count} (Critical: {critical_count})"
            }

            logger.info(f"Submitting AI session summary for Student [{student_id}] to backend: {payload}")
            res = requests.post(url, json=payload, timeout=6)
            if res.status_code >= 400:
                logger.error(f"Backend returned error {res.status_code} for summary: {res.text}")
        except Exception as e:
            logger.error(f"Failed to post summary to backend ({sess.student_id}): {e}")

    threading.Thread(target=_summary_worker, daemon=True).start()


def process_session_frame(sess: SessionState, frame: np.ndarray) -> Dict[str, Any]:
    """Processes an incoming webcam frame for a specific student's independent proctoring pipeline."""
    if frame is None or frame.size == 0 or not sess.is_active:
        return {"success": False, "active": sess.is_active, "telemetry": sess.telemetry, "events": list(sess.recent_events)}

    with sess.lock:
        sess.total_frames += 1
        sess.last_activity = time.time()
        sess.fps_frame_count += 1
        now = time.time()
        elapsed = now - sess.fps_start_time
        if elapsed >= 1.0:
            sess.fps = sess.fps_frame_count / elapsed
            sess.fps_frame_count = 0
            sess.fps_start_time = now

        # Single-point horizontal mirroring for student natural view
        if config.MIRROR_WEBCAM_FEED:
            frame = cv2.flip(frame, 1)

        # 1. Face Verification AI (independent reference per candidate)
        if sess.face_verifier:
            try:
                sess.last_face_result = sess.face_verifier.process(frame)
            except Exception as e:
                logger.debug(f"Face verification error: {e}")

        # 2. Shared YOLO Object Detection
        if shared_object_detector:
            with yolo_lock:
                try:
                    sess.last_obj_results = shared_object_detector.process(frame)
                except Exception as e:
                    logger.debug(f"YOLO object detection error: {e}")

        # 3. 3D Head Pose Estimation
        if sess.head_pose_detector:
            tg = sess.last_face_result.landmarks if (sess.last_face_result and sess.last_face_result.face_detected) else None
            try:
                sess.last_head_result = sess.head_pose_detector.process(frame, target_landmarks=tg)
            except Exception as e:
                logger.debug(f"Head pose error: {e}")

        # 4. Compile active results
        active_results = []
        if sess.last_face_result:
            active_results.append(sess.last_face_result)
        if sess.last_obj_results:
            active_results.extend(sess.last_obj_results.values())
        if sess.last_head_result:
            active_results.append(sess.last_head_result)
        if sess.last_audio_result:
            active_results.append(sess.last_audio_result)

        # 5. Diagnostic Annotations & Evidence Frame
        annotated_evidence_frame = frame.copy()
        if sess.ui_renderer:
            try:
                annotated_evidence_frame = sess.ui_renderer._draw_diagnostics(
                    annotated_evidence_frame, sess.last_face_result, sess.last_obj_results, sess.last_head_result
                )
            except Exception as ui_err:
                logger.debug(f"UI render error: {ui_err}")

        # 6. Evaluate Violations via isolated ViolationManager
        if active_results and sess.violation_mgr:
            sess.violation_mgr.update(active_results, annotated_evidence_frame)

        # 7. Update Student Telemetry State
        face_det = bool(sess.last_face_result and sess.last_face_result.face_detected)
        face_ver = bool(sess.last_face_result and sess.last_face_result.state == config.STATE_VERIFIED)
        face_sim = float(sess.last_face_result.similarity_score) if sess.last_face_result else 0.0

        phone_det = False
        book_det = False
        multi_people = False
        if sess.last_obj_results:
            ph = sess.last_obj_results.get("cell_phone")
            bk = sess.last_obj_results.get("book")
            ps = sess.last_obj_results.get("person")
            if ph and ph.state == config.STATE_PHONE_DETECTED:
                phone_det = True
            if bk and bk.state == config.STATE_BOOK_DETECTED:
                book_det = True
            if ps and ps.state == config.STATE_MULTIPLE_PEOPLE:
                multi_people = True

        head_looking_away = bool(sess.last_head_result and sess.last_head_result.state == config.STATE_LOOKING_AWAY)
        head_dir = sess.last_head_result.raw_data.get("direction", "CENTER") if (sess.last_head_result and sess.last_head_result.raw_data) else "CENTER"

        multi_speakers = bool(sess.last_audio_result and sess.last_audio_result.state == config.STATE_MULTIPLE_SPEAKERS)
        speaker_cnt = int(sess.last_audio_result.raw_data.get("credible_speaker_count", 0)) if (sess.last_audio_result and sess.last_audio_result.raw_data) else 0

        active_viols = sess.violation_mgr.get_active_violations() if sess.violation_mgr else []
        total_viols = len(sess.recent_events)

        sess.latest_frame = frame
        sess.telemetry = {
            "status": "ACTIVE",
            "face_detected": face_det,
            "face_verified": face_ver,
            "similarity": round(face_sim, 2),
            "looking_away": head_looking_away,
            "direction": head_dir,
            "phone_detected": phone_det,
            "multiple_people": multi_people,
            "book_detected": book_det,
            "multiple_speakers": multi_speakers,
            "speaker_count": speaker_cnt,
            "violations_count": total_viols,
            "active_violations": active_viols,
            "fps": round(sess.fps, 1),
        }

        # Generate scaled preview JPEG for live stream / HUD inspection
        try:
            preview_frame = cv2.resize(annotated_evidence_frame, (480, 270))
            _, buf = cv2.imencode(".jpg", preview_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            sess.latest_jpeg = buf.tobytes()
        except Exception:
            pass

        return {
            "success": True,
            "active": True,
            "telemetry": sess.telemetry,
            "events": list(sess.recent_events),
        }


def local_camera_worker(sess: SessionState):
    """Background worker loop when running on host machine with direct local webcam."""
    logger.info(f"Local camera worker started for Student: {sess.student_id}")
    while not sess.stop_signal.is_set() and sess.is_active:
        if not sess.camera:
            break
        frame = sess.camera.get_frame()
        if frame is None:
            time.sleep(0.02)
            continue

        process_session_frame(sess, frame)
        time.sleep(0.04)

    logger.info(f"Local camera worker stopped for Student: {sess.student_id}")


# ---------------- API Endpoints ----------------

@app.get("/")
def index():
    with sessions_lock:
        active_count = sum(1 for s in sessions.values() if s.is_active)
    return {
        "service": "AI Exam Proctoring Service",
        "version": "2.0.0 (Multi-Student Local Wi-Fi Architecture)",
        "status": "online",
        "active_candidates": active_count,
    }


@app.get("/api/ai/health")
def health_check(testId: Optional[str] = None, studentId: Optional[str] = None):
    sess = get_session(testId, studentId)
    with sessions_lock:
        active_count = sum(1 for s in sessions.values() if s.is_active)

    return {
        "service": "AI Exam Proctoring Service",
        "status": "online",
        "healthy": True,
        "active_candidates": active_count,
        "active_session": bool(sess and sess.is_active),
        "test_id": sess.test_id if sess else None,
        "student_id": sess.student_id if sess else None,
    }


@app.post("/api/ai/verify-photo")
def verify_candidate_photo(req: VerifyPhotoRequest):
    """
    Pre-flight photo verification endpoint.
    Extracts face embedding from reference photo, grabs 1 frame (from browser liveFrameBase64
    or fallback local webcam), and returns similarity score and match result.
    """
    try:
        ref_path = resolve_photo_path(req.photoUrl, req.photoBase64)
        if not ref_path or not ref_path.exists():
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "Reference photo not found or could not be resolved."}
            )

        verifier = FaceVerifier(similarity_threshold=config.FACE_SIMILARITY_THRESHOLD)
        try:
            verifier.enroll_reference(str(ref_path))
        except Exception as e:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": f"Reference photo enrollment failed: {str(e)}"}
            )

        frame = None
        if req.liveFrameBase64:
            try:
                raw_b64 = req.liveFrameBase64.split(",")[-1]
                frame_bytes = base64.b64decode(raw_b64)
                np_arr = np.frombuffer(frame_bytes, np.uint8)
                frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            except Exception as e:
                logger.warning(f"Failed to decode liveFrameBase64: {e}")

        if frame is None:
            # Fallback to direct webcam capture on host machine only if explicit cameraIndex provided
            if req.cameraIndex >= 0:
                cap = cv2.VideoCapture(req.cameraIndex)
                try:
                    if not cap.isOpened():
                        return {
                            "success": False,
                            "face_detected": False,
                            "is_match": False,
                            "similarity": 0.0,
                            "threshold": config.FACE_SIMILARITY_THRESHOLD,
                            "message": "Webcam unavailable on host. Please allow browser camera access."
                        }

                    ret, cap_frame = cap.read()
                    if not ret or cap_frame is None:
                        return {
                            "success": False,
                            "face_detected": False,
                            "is_match": False,
                            "similarity": 0.0,
                            "threshold": config.FACE_SIMILARITY_THRESHOLD,
                            "message": "Failed to capture webcam frame."
                        }
                    frame = cap_frame
                finally:
                    cap.release()
            else:
                return {
                    "success": False,
                    "face_detected": False,
                    "is_match": False,
                    "similarity": 0.0,
                    "threshold": config.FACE_SIMILARITY_THRESHOLD,
                    "message": "Live camera preview required for verification. Please ensure camera preview is active in browser."
                }

        if config.MIRROR_WEBCAM_FEED and not req.liveFrameBase64:
            frame = cv2.flip(frame, 1)

        result = verifier.process(frame)
        is_match = bool(result.face_detected and result.state == config.STATE_VERIFIED)

        return {
            "success": True,
            "face_detected": result.face_detected,
            "is_match": is_match,
            "similarity": round(result.similarity_score, 3),
            "threshold": config.FACE_SIMILARITY_THRESHOLD,
            "message": result.message or ("Identity Verified" if is_match else "Identity Mismatch")
        }

    except Exception as err:
        logger.error(f"Error in verify_candidate_photo: {err}", exc_info=True)
        return JSONResponse(status_code=500, content={"success": False, "message": str(err)})


@app.post("/api/ai/start-session")
def start_proctoring_session(req: StartSessionRequest, background_tasks: BackgroundTasks):
    """
    Starts an isolated multimodal AI proctoring session for a candidate taking a test.
    Supports multiple simultaneous candidates on the same Wi-Fi network without collision.
    """
    global last_active_session
    key = get_session_key(req.testId, req.studentId)

    with sessions_lock:
        # Check if candidate already has an active session
        if key in sessions:
            old_sess = sessions[key]
            if old_sess.is_active:
                logger.info(f"Proctoring session already active for Test: {req.testId}, Student: {req.studentId}")
                return {
                    "success": True,
                    "message": "Proctoring session already active for this student",
                    "testId": req.testId,
                    "studentId": req.studentId,
                    "sessionKey": key,
                }
            else:
                # Clean up inactive session
                old_sess.stop_signal.set()
                if old_sess.camera:
                    old_sess.camera.stop()

        # Create brand-new isolated session state
        sess = SessionState(
            test_id=req.testId,
            student_id=req.studentId,
            student_name=req.studentName or "Candidate",
            backend_url=req.backendUrl or config.BACKEND_API_URL
        )

        # 1. Resolve & Enroll Reference Photo specifically for this candidate
        ref_path = resolve_photo_path(req.photoUrl, req.photoBase64, student_id=req.studentId)
        if not ref_path:
            logger.warning(f"Reference photo not found for Student [{req.studentId}]. Checking default.")
            ref_path = config.STUDENT_REFERENCE_IMAGE

        try:
            sess.face_verifier = FaceVerifier(similarity_threshold=config.FACE_SIMILARITY_THRESHOLD)
            if ref_path and ref_path.exists():
                sess.face_verifier.enroll_reference(str(ref_path))
                logger.info(f"Student [{req.studentId}] enrolled successfully from: {ref_path}")
            else:
                logger.warning(f"Student [{req.studentId}] started without enrolled face reference.")
        except Exception as e:
            logger.warning(f"Face enrollment warning for [{req.studentId}]: {e}")

        # 2. Initialize Head Pose Detector with candidate calibration
        try:
            sess.head_pose_detector = HeadPoseDetector()
            sess.head_pose_detector.start_calibration(config.HEAD_POSE_CALIBRATION_SECONDS)
        except Exception as e:
            logger.error(f"Failed to load HeadPoseDetector: {e}")

        # 3. Initialize Audio & Speaker Detector
        sess.speaker_detector = SpeakerDetector()

        # 4. Initialize Violation Logger & Manager with per-student callback & paths
        sess.violation_logger = ViolationLogger(test_id=req.testId, student_id=req.studentId)

        def _on_violation(episode, screenshot_path):
            forward_violation_to_backend(sess, episode, screenshot_path)

        sess.violation_mgr = ViolationManager(
            logger_instance=sess.violation_logger,
            on_violation_start=_on_violation,
            test_id=req.testId,
            student_id=req.studentId
        )
        sess.ui_renderer = ProctoringUI()

        # 5. Optional local hardware camera fallback (only if local cameraIndex requested and on server host)
        # For remote Wi-Fi clients, frames are streamed via POST /api/ai/session/frame
        if req.cameraIndex >= 0 and sys.platform.startswith("win"):
            # Only start hardware camera if not already active to avoid locking hardware
            try:
                sess.camera = CameraManager(camera_index=req.cameraIndex, width=config.WEBCAM_WIDTH, height=config.WEBCAM_HEIGHT)
                sess.camera.start()
                sess.worker_thread = threading.Thread(target=local_camera_worker, args=(sess,), daemon=True)
                sess.worker_thread.start()
            except Exception as cam_err:
                logger.debug(f"Direct hardware camera not opened (browser stream will be used): {cam_err}")
                sess.camera = None

        sessions[key] = sess
        last_active_session = sess

    logger.info(f"AI Proctoring session started successfully for Test: {req.testId}, Student: {req.studentId} (Total Active: {len(sessions)})")

    return {
        "success": True,
        "message": "AI Proctoring Session Active",
        "testId": sess.test_id,
        "studentId": sess.student_id,
        "sessionKey": key,
        "backendUrl": sess.backend_url,
    }


@app.post("/api/ai/session/frame")
@app.post("/api/ai/frame")
def ingest_session_frame(req: FrameRequest):
    """
    High-performance real-time frame ingestion endpoint for student browsers.
    Runs the student's isolated AI detection pipeline on their current webcam frame
    and immediately returns updated proctoring telemetry and events.
    """
    sess = get_session(req.testId, req.studentId)
    if not sess or not sess.is_active:
        return {
            "success": False,
            "active": False,
            "message": f"No active proctoring session found for student: {req.studentId}",
            "telemetry": None,
            "events": []
        }

    try:
        raw_b64 = req.frameBase64.split(",")[-1]
        frame_bytes = base64.b64decode(raw_b64)
        np_arr = np.frombuffer(frame_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if frame is None:
            return {"success": False, "active": True, "message": "Failed to decode frame", "telemetry": sess.telemetry}

        return process_session_frame(sess, frame)

    except Exception as err:
        logger.error(f"Error processing frame for Student [{req.studentId}]: {err}")
        return {"success": False, "active": True, "message": str(err), "telemetry": sess.telemetry}


@app.post("/api/ai/stop-session")
def stop_proctoring_session(req: Optional[StopSessionRequest] = None):
    """
    Safely terminates the student's proctoring session, releases resources,
    and posts the final session summary to Express backend.
    """
    global last_active_session
    test_id = req.testId if req else None
    student_id = req.studentId if req else None

    sess = get_session(test_id, student_id)
    if not sess or not sess.is_active:
        return {"success": True, "message": "No active proctoring session to stop"}

    acquired = sess.lock.acquire(timeout=1.5)
    try:
        logger.info(f"Stopping AI Proctoring session for Test: {sess.test_id}, Student: {sess.student_id}")
        sess.is_active = False
        sess.stop_signal.set()

        if sess.camera:
            try:
                sess.camera.stop()
            except Exception:
                pass
            sess.camera = None

        if sess.audio_manager:
            try:
                sess.audio_manager.stop()
            except Exception:
                pass
            sess.audio_manager = None

        if sess.violation_mgr:
            try:
                sess.violation_mgr.print_post_test_logs()
            except Exception:
                pass

        forward_summary_to_backend(sess, "Proctoring session ended normally upon exam completion")
    finally:
        if acquired:
            try:
                sess.lock.release()
            except Exception:
                pass

    key = get_session_key(sess.test_id, sess.student_id)
    with sessions_lock:
        if key in sessions:
            del sessions[key]
        if last_active_session == sess:
            last_active_session = None

    return {
        "success": True,
        "message": "AI Proctoring Session Stopped",
        "testId": sess.test_id,
        "studentId": sess.student_id,
    }


@app.get("/api/ai/status")
def get_session_status(testId: Optional[str] = Query(None), studentId: Optional[str] = Query(None)):
    """
    Returns live proctoring telemetry and infraction events for a specific student's examination session.
    """
    sess = get_session(testId, studentId)
    if not sess or not sess.is_active:
        return {
            "active": False,
            "testId": testId,
            "studentId": studentId,
            "telemetry": None,
            "events": []
        }

    acquired = sess.lock.acquire(timeout=1.0)
    try:
        return {
            "active": sess.is_active,
            "testId": sess.test_id,
            "studentId": sess.student_id,
            "telemetry": sess.telemetry,
            "events": list(sess.recent_events)
        }
    finally:
        if acquired:
            try:
                sess.lock.release()
            except Exception:
                pass


def generate_mjpeg_stream(sess: SessionState):
    """Generator yielding JPEG multipart boundary frames for live streaming."""
    blank_frame = np.zeros((270, 480, 3), dtype=np.uint8)
    cv2.rectangle(blank_frame, (0, 0), (480, 270), (18, 24, 38), -1)
    cv2.putText(blank_frame, f"AI Monitor: {sess.student_name}", (40, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (180, 195, 215), 2)
    _, blank_jpeg = cv2.imencode(".jpg", blank_frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
    blank_bytes = blank_jpeg.tobytes()

    while sess.is_active:
        with sess.lock:
            frame_bytes = sess.latest_jpeg or blank_bytes

        header = (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n"
            b"Content-Length: " + str(len(frame_bytes)).encode() + b"\r\n\r\n"
        )
        try:
            yield header + frame_bytes + b"\r\n"
        except (GeneratorExit, ConnectionResetError, BrokenPipeError):
            break
        time.sleep(0.04)  # ~25 FPS


@app.get("/api/ai/video-feed")
@app.get("/video-feed")
def video_feed(testId: Optional[str] = Query(None), studentId: Optional[str] = Query(None)):
    """
    Streams live MJPEG camera feed with AI telemetry overlays for a specific candidate.
    """
    sess = get_session(testId, studentId)
    if not sess:
        blank_frame = np.zeros((270, 480, 3), dtype=np.uint8)
        cv2.putText(blank_frame, "No Active Stream", (130, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (180, 195, 215), 2)
        _, blank_jpeg = cv2.imencode(".jpg", blank_frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        return StreamingResponse(
            iter([b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + blank_jpeg.tobytes() + b"\r\n"]),
            media_type="multipart/x-mixed-replace; boundary=frame"
        )

    return StreamingResponse(
        generate_mjpeg_stream(sess),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "proctor_service:app",
        host=config.AI_SERVICE_HOST,
        port=config.AI_SERVICE_PORT,
        reload=False
    )
