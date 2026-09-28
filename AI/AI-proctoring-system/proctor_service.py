import os
import sys
import time
import logging
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List
from collections import deque
import base64
import requests

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
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

app = FastAPI(title="AI Proctoring Service", version="1.0.0")

# Enable CORS for Vite frontend (localhost:5173, Wi-Fi IP) and Express backend (localhost:5000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Shared Detection Models (loaded once in memory, reused across all candidates)
shared_object_detector: Optional[ObjectDetector] = None
shared_face_verifier_engine: Optional[FaceVerifier] = None
shared_ui_renderer: Optional[ProctoringUI] = None
models_lock = threading.Lock()


def get_shared_object_detector() -> Optional[ObjectDetector]:
    global shared_object_detector
    with models_lock:
        if shared_object_detector is None:
            try:
                shared_object_detector = ObjectDetector(model_name=config.YOLO_MODEL, img_size=config.YOLO_IMAGE_SIZE)
                logger.info("Shared ObjectDetector (YOLO) initialized.")
            except Exception as e:
                logger.error(f"Failed to initialize shared ObjectDetector: {e}")
        return shared_object_detector


def get_shared_face_verifier_engine() -> Optional[FaceVerifier]:
    global shared_face_verifier_engine
    with models_lock:
        if shared_face_verifier_engine is None:
            try:
                shared_face_verifier_engine = FaceVerifier(similarity_threshold=config.FACE_SIMILARITY_THRESHOLD)
                logger.info("Shared FaceVerifier engine initialized.")
            except Exception as e:
                logger.error(f"Failed to initialize shared FaceVerifier: {e}")
        return shared_face_verifier_engine


def get_shared_ui_renderer() -> ProctoringUI:
    global shared_ui_renderer
    with models_lock:
        if shared_ui_renderer is None:
            shared_ui_renderer = ProctoringUI()
        return shared_ui_renderer


class VerifyPhotoRequest(BaseModel):
    photoUrl: Optional[str] = None
    photoBase64: Optional[str] = None
    liveFrameBase64: Optional[str] = None
    cameraIndex: int = 0


class StartSessionRequest(BaseModel):
    testId: str
    studentId: str
    studentName: Optional[str] = ""
    photoUrl: Optional[str] = None
    photoBase64: Optional[str] = None
    backendUrl: Optional[str] = None
    cameraIndex: int = 0


class ProcessFrameRequest(BaseModel):
    testId: str
    studentId: str
    liveFrameBase64: str
    studentName: Optional[str] = ""
    photoUrl: Optional[str] = None
    photoBase64: Optional[str] = None


class StopSessionRequest(BaseModel):
    testId: Optional[str] = None
    studentId: Optional[str] = None


def resolve_photo_path(photo_url: Optional[str], photo_base64: Optional[str], target_name: Optional[str] = None) -> Optional[Path]:
    """Resolves a candidate reference photo from URL, local file, or Base64."""
    filename = target_name or "current_student_enrolled.jpg"
    temp_target = config.REFERENCE_DIR / filename
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
            logger.warning(f"Failed to decode photo_url data URI: {e}")

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


class CandidateSession:
    """Manages an isolated proctoring session for a single candidate appearing for a test."""

    def __init__(self, test_id: str, student_id: str, student_name: str = "", backend_url: str = ""):
        self.lock = threading.Lock()
        self.test_id = test_id
        self.student_id = student_id
        self.student_name = student_name or "Candidate"
        self.backend_url = backend_url or config.BACKEND_API_URL
        self.is_active = True
        self.created_at = time.time()
        self.last_activity = time.time()

        # Face Verifier for this candidate (shares underlying InsightFace/SFace model)
        self.face_verifier: Optional[FaceVerifier] = None
        self._init_face_verifier()

        # Head Pose Detector with personal calibration
        self.head_pose_detector = HeadPoseDetector()
        self.head_pose_detector.start_calibration(config.HEAD_POSE_CALIBRATION_SECONDS)

        # Violation Tracking
        self.violation_logger = ViolationLogger()
        self.violation_mgr = ViolationManager(
            logger_instance=self.violation_logger,
            on_violation_start=self._on_violation_start
        )

        # Diagnostics renderer
        self.ui_renderer = get_shared_ui_renderer()

        # Telemetry & Events
        self.latest_frame: Optional[np.ndarray] = None
        self.latest_jpeg: Optional[bytes] = None
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
            "fps": 25.0,
        }
        self.recent_events: deque = deque(maxlen=50)

        # Hardware camera fallback (only used if running standalone local PC loop)
        self.camera: Optional[CameraManager] = None
        self.audio_manager: Optional[AudioManager] = None
        self.worker_thread: Optional[threading.Thread] = None
        self.stop_signal = threading.Event()

    def _init_face_verifier(self):
        try:
            shared_fv = get_shared_face_verifier_engine()
            self.face_verifier = FaceVerifier(similarity_threshold=config.FACE_SIMILARITY_THRESHOLD)
            if shared_fv and shared_fv.insight_app:
                self.face_verifier.insight_app = shared_fv.insight_app
                self.face_verifier.engine_type = shared_fv.engine_type
            elif shared_fv:
                self.face_verifier.engine_type = shared_fv.engine_type
        except Exception as e:
            logger.warning(f"CandidateSession face verifier init notice: {e}")

    def enroll_photo(self, photo_url: Optional[str], photo_base64: Optional[str]) -> bool:
        """Enrolls reference face photo for identity verification."""
        target_name = f"candidate_{self.test_id}_{self.student_id}.jpg"
        ref_path = resolve_photo_path(photo_url, photo_base64, target_name=target_name)
        if not ref_path or not ref_path.exists():
            logger.warning(f"No reference photo resolved for candidate {self.student_id}. Using face presence mode.")
            ref_path = config.STUDENT_REFERENCE_IMAGE

        if self.face_verifier and ref_path and ref_path.exists():
            try:
                self.face_verifier.enroll_reference(str(ref_path))
                logger.info(f"Candidate {self.student_id} successfully enrolled from {ref_path}")
                return True
            except Exception as e:
                logger.warning(f"Candidate {self.student_id} photo enrollment notice: {e}")
        return False

    def _on_violation_start(self, episode, screenshot_path: Optional[str]):
        """Triggered immediately when ViolationManager confirms a violation episode."""
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
        with self.lock:
            self.recent_events.append(event_payload)

        # Post to Express backend asynchronously
        def _post_worker():
            opened_file = None
            try:
                backend_api = self.backend_url.rstrip("/")
                url = f"{backend_api}/violation"

                data = {
                    "testId": self.test_id,
                    "studentId": self.student_id,
                    "type": episode.vtype,
                    "message": episode.message,
                    "duration_seconds": episode.duration_seconds or 0,
                    "similarity": episode.similarity,
                }

                files = None
                if screenshot_path and os.path.exists(screenshot_path):
                    opened_file = open(screenshot_path, "rb")
                    files = {"screenshot": (os.path.basename(screenshot_path), opened_file, "image/jpeg")}

                logger.info(f"Forwarding AI violation [{episode.vtype}] for student [{self.student_id}] to {url}")
                res = requests.post(url, data=data, files=files, timeout=6)
                logger.info(f"Backend response for violation: {res.status_code}")
            except Exception as e:
                logger.debug(f"Violation post notice for student {self.student_id}: {e}")
            finally:
                if opened_file:
                    try:
                        opened_file.close()
                    except Exception:
                        pass

        threading.Thread(target=_post_worker, daemon=True).start()

    def forward_summary_to_backend(self, notes: str = "AI Proctoring session completed"):
        """Submits the candidate session summary and risk rating to Express backend in a background worker."""
        def _summary_worker():
            try:
                backend_api = self.backend_url.rstrip("/")
                url = f"{backend_api}/session-summary"

                with self.lock:
                    active_count = len(self.recent_events)
                    critical_count = sum(1 for e in self.recent_events if e.get("severity") == "critical")
                    test_id = self.test_id
                    student_id = self.student_id
                    looking_away_count = sum(1 for e in self.recent_events if e.get("type") == config.STATE_LOOKING_AWAY)

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

                logger.info(f"Submitting AI session summary for student [{student_id}]: {payload}")
                requests.post(url, json=payload, timeout=6)
            except Exception as e:
                logger.debug(f"Summary backend post notice: {e}")

        threading.Thread(target=_summary_worker, daemon=True).start()

    def stop(self):
        """Terminates session resources cleanly."""
        self.is_active = False
        self.stop_signal.set()
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2.0)
        if self.camera:
            self.camera.stop()
            self.camera = None
        if self.audio_manager:
            self.audio_manager.stop()
            self.audio_manager = None
        if self.violation_mgr:
            self.violation_mgr.print_post_test_logs()
        self.forward_summary_to_backend("Proctoring session ended normally upon exam completion")


# Global Multi-Session Registry
sessions_registry_lock = threading.Lock()
candidate_sessions: Dict[str, CandidateSession] = {}
last_active_session: Optional[CandidateSession] = None


def get_session_key(test_id: Optional[str], student_id: Optional[str]) -> str:
    tid = (test_id or "").strip()
    sid = (student_id or "").strip()
    return f"{tid}_{sid}"


def find_session(test_id: Optional[str] = None, student_id: Optional[str] = None) -> Optional[CandidateSession]:
    global last_active_session
    with sessions_registry_lock:
        if test_id and student_id:
            key = get_session_key(test_id, student_id)
            if key in candidate_sessions:
                return candidate_sessions[key]
            # Try by studentId alone
            for s in candidate_sessions.values():
                if s.student_id == student_id:
                    return s

        # Fallback to most recently active session
        if last_active_session and last_active_session.is_active:
            return last_active_session
        for s in reversed(list(candidate_sessions.values())):
            if s.is_active:
                return s
        return last_active_session or (list(candidate_sessions.values())[-1] if candidate_sessions else None)


# ---------------- API Endpoints ----------------

@app.get("/")
def index():
    active_cnt = sum(1 for s in candidate_sessions.values() if s.is_active)
    return {
        "service": "AI Exam Proctoring Service",
        "status": "online",
        "multi_device_mode": True,
        "active_sessions": active_cnt
    }


@app.get("/api/ai/health")
def health_check(testId: Optional[str] = None, studentId: Optional[str] = None):
    cand_sess = find_session(testId, studentId)
    active_cnt = sum(1 for s in candidate_sessions.values() if s.is_active)
    return {
        "service": "AI Exam Proctoring Service",
        "status": "online",
        "healthy": True,
        "multi_device_mode": True,
        "active_session": cand_sess.is_active if cand_sess else (active_cnt > 0),
        "total_active_candidates": active_cnt,
        "test_id": cand_sess.test_id if cand_sess else None,
        "student_id": cand_sess.student_id if cand_sess else None
    }


@app.post("/api/ai/verify-photo")
def verify_candidate_photo(req: VerifyPhotoRequest):
    """
    Pre-flight photo verification endpoint.
    Extracts face embedding from reference photo, grabs 1 webcam frame (or uses browser frame),
    and returns similarity score and match result.
    """
    try:
        ref_path = resolve_photo_path(req.photoUrl, req.photoBase64)
        if not ref_path or not ref_path.exists():
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "Reference photo not found or could not be resolved."}
            )

        shared_fv = get_shared_face_verifier_engine()
        verifier = FaceVerifier(similarity_threshold=config.FACE_SIMILARITY_THRESHOLD)
        if shared_fv and shared_fv.insight_app:
            verifier.insight_app = shared_fv.insight_app
            verifier.engine_type = shared_fv.engine_type

        try:
            verifier.enroll_reference(str(ref_path))
        except Exception as e:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": f"Reference photo enrollment failed: {str(e)}"}
            )

        # Acquire frame: 1) from browser liveFrameBase64 or 2) direct camera capture
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
            # Fallback to direct webcam capture on local machine
            cap = cv2.VideoCapture(req.cameraIndex)
            if not cap.isOpened():
                return {
                    "success": False,
                    "face_detected": False,
                    "is_match": False,
                    "similarity": 0.0,
                    "threshold": config.FACE_SIMILARITY_THRESHOLD,
                    "message": "Camera is busy or access not granted by browser. Please allow camera permissions."
                }

            ret, cap_frame = cap.read()
            cap.release()

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
    Initializes an isolated multimodal AI proctoring session for a candidate taking a test.
    Supports multiple simultaneous candidates across different devices over Wi-Fi.
    """
    global last_active_session
    key = get_session_key(req.testId, req.studentId)

    with sessions_registry_lock:
        cand_sess = candidate_sessions.get(key)
        if cand_sess and cand_sess.is_active:
            # Re-enroll photo if new one provided
            if req.photoUrl or req.photoBase64:
                cand_sess.enroll_photo(req.photoUrl, req.photoBase64)
            last_active_session = cand_sess
            return {
                "success": True,
                "message": "AI Proctoring session active",
                "testId": cand_sess.test_id,
                "studentId": cand_sess.student_id,
            }

        # Initialize candidate session
        cand_sess = CandidateSession(
            test_id=req.testId,
            student_id=req.studentId,
            student_name=req.studentName or "Candidate",
            backend_url=req.backendUrl or config.BACKEND_API_URL
        )
        cand_sess.enroll_photo(req.photoUrl, req.photoBase64)

        candidate_sessions[key] = cand_sess
        last_active_session = cand_sess

    logger.info(f"AI Proctoring session started for Test: [{req.testId}], Student: [{req.studentId}]")

    return {
        "success": True,
        "message": "AI Proctoring Session Active",
        "testId": cand_sess.test_id,
        "studentId": cand_sess.student_id,
        "backendUrl": cand_sess.backend_url
    }


@app.post("/api/ai/process-frame")
def process_candidate_frame(req: ProcessFrameRequest):
    """
    Receives a live webcam frame snapshot streamed from candidate's browser over Wi-Fi,
    executes multimodal AI proctoring (Face Verifier, YOLO, Head Pose),
    updates violation manager, and returns real-time telemetry and alerts.
    """
    global last_active_session
    cand_sess = find_session(req.testId, req.studentId)

    # Auto-initialize session if not explicitly created
    if not cand_sess or cand_sess.test_id != req.testId or cand_sess.student_id != req.studentId:
        key = get_session_key(req.testId, req.studentId)
        with sessions_registry_lock:
            cand_sess = candidate_sessions.get(key)
            if not cand_sess:
                cand_sess = CandidateSession(
                    test_id=req.testId,
                    student_id=req.studentId,
                    student_name=req.studentName or "Candidate",
                    backend_url=config.BACKEND_API_URL
                )
                cand_sess.enroll_photo(req.photoUrl, req.photoBase64)
                candidate_sessions[key] = cand_sess
            last_active_session = cand_sess

    if not req.liveFrameBase64:
        return {"success": False, "message": "No liveFrameBase64 frame provided"}

    # 1. Decode frame from Base64
    try:
        raw_b64 = req.liveFrameBase64.split(",")[-1]
        frame_bytes = base64.b64decode(raw_b64)
        np_arr = np.frombuffer(frame_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    except Exception as e:
        return {"success": False, "message": f"Base64 decode failed: {e}"}

    if frame is None or frame.size == 0:
        return {"success": False, "message": "Empty decoded frame"}

    obj_detector = get_shared_object_detector()
    last_face_result = None
    last_obj_results = None
    last_head_result = None

    # 2. Run Face Verification
    if cand_sess.face_verifier:
        try:
            last_face_result = cand_sess.face_verifier.process(frame)
        except Exception as e:
            logger.debug(f"Face verification inference notice: {e}")

    # 3. Run YOLO Object Detection (phone, book, multiple people)
    if obj_detector:
        try:
            last_obj_results = obj_detector.process(frame)
        except Exception as e:
            logger.debug(f"Object detector inference notice: {e}")

    # 4. Run 3D Head Pose Estimation
    if cand_sess.head_pose_detector:
        try:
            tg = last_face_result.landmarks if (last_face_result and last_face_result.face_detected) else None
            last_head_result = cand_sess.head_pose_detector.process(frame, target_landmarks=tg)
        except Exception as e:
            logger.debug(f"Head pose inference notice: {e}")

    # 5. Evaluate Active Violations
    active_results = []
    if last_face_result:
        active_results.append(last_face_result)
    if last_obj_results:
        active_results.extend(last_obj_results.values())
    if last_head_result:
        active_results.append(last_head_result)

    annotated_frame = frame.copy()
    if cand_sess.ui_renderer:
        annotated_frame = cand_sess.ui_renderer._draw_diagnostics(
            annotated_frame, last_face_result, last_obj_results, last_head_result
        )

    if active_results and cand_sess.violation_mgr:
        cand_sess.violation_mgr.update(active_results, annotated_frame)

    # 6. Extract Telemetry Fields
    face_det = bool(last_face_result and last_face_result.face_detected)
    face_ver = bool(last_face_result and last_face_result.state == config.STATE_VERIFIED)
    face_sim = float(last_face_result.similarity_score) if last_face_result else 0.0

    phone_det = False
    book_det = False
    multi_people = False
    if last_obj_results:
        ph = last_obj_results.get("cell_phone")
        bk = last_obj_results.get("book")
        ps = last_obj_results.get("person")
        if ph and ph.state == config.STATE_PHONE_DETECTED:
            phone_det = True
        if bk and bk.state == config.STATE_BOOK_DETECTED:
            book_det = True
        if ps and ps.state == config.STATE_MULTIPLE_PEOPLE:
            multi_people = True

    head_looking_away = bool(last_head_result and last_head_result.state == config.STATE_LOOKING_AWAY)
    head_dir = last_head_result.raw_data.get("direction", "CENTER") if (last_head_result and last_head_result.raw_data) else "CENTER"
    active_viols = cand_sess.violation_mgr.get_active_violations() if cand_sess.violation_mgr else []
    total_viols = len(cand_sess.recent_events)

    with cand_sess.lock:
        cand_sess.latest_frame = frame
        cand_sess.last_activity = time.time()
        cand_sess.telemetry = {
            "status": "ACTIVE",
            "face_detected": face_det,
            "face_verified": face_ver,
            "similarity": round(face_sim, 2),
            "looking_away": head_looking_away,
            "direction": head_dir,
            "phone_detected": phone_det,
            "multiple_people": multi_people,
            "book_detected": book_det,
            "multiple_speakers": False,
            "speaker_count": 0,
            "violations_count": total_viols,
            "active_violations": active_viols,
            "fps": 25.0,
        }

        # Store downscaled MJPEG frame for examiner/admin stream inspection
        preview_frame = cv2.resize(annotated_frame, (480, 270))
        _, buf = cv2.imencode(".jpg", preview_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        cand_sess.latest_jpeg = buf.tobytes()

        return {
            "success": True,
            "telemetry": cand_sess.telemetry,
            "events": list(cand_sess.recent_events)
        }


@app.post("/api/ai/stop-session")
def stop_proctoring_session(req: Optional[StopSessionRequest] = None):
    """
    Safely terminates the proctoring session for a candidate, releases resources,
    and posts final session summary and risk classification to Express backend.
    """
    tid = req.testId if req else None
    sid = req.studentId if req else None

    cand_sess = find_session(tid, sid)
    if not cand_sess or not cand_sess.is_active:
        return {"success": True, "message": "No active proctoring session to stop"}

    logger.info(f"Stopping AI Proctoring session for Student: [{cand_sess.student_id}], Test: [{cand_sess.test_id}]")
    cand_sess.stop()

    return {
        "success": True,
        "message": "AI Proctoring Session Stopped",
        "testId": cand_sess.test_id,
        "studentId": cand_sess.student_id
    }


@app.get("/api/ai/status")
def get_session_status(testId: Optional[str] = None, studentId: Optional[str] = None):
    """
    Returns live proctoring telemetry and recent infraction events for a candidate.
    """
    cand_sess = find_session(testId, studentId)
    if not cand_sess:
        return {
            "active": False,
            "testId": None,
            "studentId": None,
            "telemetry": None,
            "events": []
        }

    with cand_sess.lock:
        return {
            "active": cand_sess.is_active,
            "testId": cand_sess.test_id,
            "studentId": cand_sess.student_id,
            "telemetry": cand_sess.telemetry,
            "events": list(cand_sess.recent_events)
        }


def generate_mjpeg_stream(test_id: Optional[str] = None, student_id: Optional[str] = None):
    """Generator yielding JPEG multipart boundary frames for live streaming."""
    blank_frame = np.zeros((270, 480, 3), dtype=np.uint8)
    cv2.rectangle(blank_frame, (0, 0), (480, 270), (18, 24, 38), -1)
    cv2.putText(blank_frame, "AI Proctoring Feed Initializing...", (50, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (180, 195, 215), 2)
    _, blank_jpeg = cv2.imencode(".jpg", blank_frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
    blank_bytes = blank_jpeg.tobytes()

    while True:
        cand_sess = find_session(test_id, student_id)
        frame_bytes = blank_bytes
        if cand_sess:
            with cand_sess.lock:
                frame_bytes = cand_sess.latest_jpeg or blank_bytes

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
def video_feed(testId: Optional[str] = None, studentId: Optional[str] = None):
    """
    Streams live MJPEG camera feed with AI telemetry overlays for the in-browser HUD.
    """
    return StreamingResponse(
        generate_mjpeg_stream(testId, studentId),
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
