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

# Enable CORS for Vite frontend (localhost:5173) and Express backend (localhost:5000)
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
    cameraIndex: int = 0


class StartSessionRequest(BaseModel):
    testId: str
    studentId: str
    studentName: Optional[str] = ""
    photoUrl: Optional[str] = None
    photoBase64: Optional[str] = None
    backendUrl: Optional[str] = None
    cameraIndex: int = 0


class SessionState:
    def __init__(self):
        self.lock = threading.Lock()
        self.is_active: bool = False
        self.test_id: Optional[str] = None
        self.student_id: Optional[str] = None
        self.student_name: Optional[str] = None
        self.backend_url: str = config.BACKEND_API_URL
        self.camera_index: int = 0

        self.camera: Optional[CameraManager] = None
        self.audio_manager: Optional[AudioManager] = None
        self.face_verifier: Optional[FaceVerifier] = None
        self.object_detector: Optional[ObjectDetector] = None
        self.head_pose_detector: Optional[HeadPoseDetector] = None
        self.speaker_detector: Optional[SpeakerDetector] = None
        self.violation_logger: Optional[ViolationLogger] = None
        self.violation_mgr: Optional[ViolationManager] = None
        self.ui_renderer: Optional[ProctoringUI] = None

        self.worker_thread: Optional[threading.Thread] = None
        self.stop_signal: threading.Event = threading.Event()

        self.latest_frame: Optional[np.ndarray] = None
        self.latest_jpeg: Optional[bytes] = None
        self.telemetry: Dict[str, Any] = {
            "status": "IDLE",
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


session = SessionState()


def resolve_photo_path(photo_url: Optional[str], photo_base64: Optional[str]) -> Optional[Path]:
    """Resolves a student photo reference from URL, local file, or Base64."""
    temp_target = config.REFERENCE_DIR / "current_student_enrolled.jpg"
    temp_target.parent.mkdir(parents=True, exist_ok=True)

    # 1. Base64
    if photo_base64:
        raw_b64 = photo_base64.split(",")[-1]
        img_bytes = base64.b64decode(raw_b64)
        with open(temp_target, "wb") as f:
            f.write(img_bytes)
        return temp_target

    if not photo_url:
        return None

    # 2. Base64 Data URL
    if photo_url.startswith("data:image"):
        raw_b64 = photo_url.split(",")[-1]
        img_bytes = base64.b64decode(raw_b64)
        with open(temp_target, "wb") as f:
            f.write(img_bytes)
        return temp_target

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


def forward_violation_to_backend(episode, screenshot_path: Optional[str]):
    """Sends confirmed violation episode and evidence screenshot to Express backend."""
    try:
        backend_api = session.backend_url.rstrip("/")
        url = f"{backend_api}/violation"

        data = {
            "testId": session.test_id,
            "studentId": session.student_id,
            "type": episode.vtype,
            "message": episode.message,
            "duration_seconds": episode.duration_seconds or 0,
            "similarity": episode.similarity,
        }

        files = None
        opened_file = None
        if screenshot_path and os.path.exists(screenshot_path):
            opened_file = open(screenshot_path, "rb")
            files = {"screenshot": (os.path.basename(screenshot_path), opened_file, "image/jpeg")}

        logger.info(f"Forwarding AI violation [{episode.vtype}] to backend: {url}")
        res = requests.post(url, data=data, files=files, timeout=8)
        if opened_file:
            opened_file.close()

        logger.info(f"Backend response for violation: {res.status_code}")

        # Friendly simplified labels for frontend and telemetry notifications
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

        # Add event to queue for frontend notifications
        event_payload = {
            "id": episode.id,
            "type": episode.vtype,
            "message": clean_msg,
            "raw_message": episode.message,
            "timestamp": episode.timestamp_str,
            "similarity": episode.similarity,
            "severity": "critical" if episode.vtype in ["PHONE_DETECTED", "MULTIPLE_PEOPLE", "IDENTITY_MISMATCH"] else "warning"
        }
        session.recent_events.append(event_payload)

    except Exception as e:
        logger.error(f"Failed to forward violation to backend: {e}")


def forward_summary_to_backend(notes: str = "AI Proctoring session completed"):
    """Submits the final session summary and risk rating to Express backend."""
    try:
        backend_api = session.backend_url.rstrip("/")
        url = f"{backend_api}/session-summary"

        active_count = len(session.recent_events)
        critical_count = sum(1 for e in session.recent_events if e.get("severity") == "critical")

        if critical_count >= 1 or active_count >= 4:
            risk_level = "High"
        elif active_count >= 1:
            risk_level = "Medium"
        else:
            risk_level = "Low"

        payload = {
            "testId": session.test_id,
            "studentId": session.student_id,
            "riskLevel": risk_level,
            "notes": f"{notes} | Total AI Infractions: {active_count} (Critical: {critical_count})"
        }

        logger.info(f"Submitting AI session summary to backend: {payload}")
        requests.post(url, json=payload, timeout=8)
    except Exception as e:
        logger.error(f"Failed to submit session summary to backend: {e}")


def proctoring_loop():
    """Continuous background proctoring worker thread."""
    logger.info("AI Proctoring Worker Loop started.")

    frame_count = 0
    total_frames = 0
    fps = 0.0
    start_time = time.time()

    last_face_result = None
    last_obj_results = None
    last_head_result = None
    last_audio_result = None

    is_face_running = False
    is_yolo_running = False
    is_head_running = False
    is_diarization_running = False
    last_diarization_launch = 0.0

    TARGET_FPS = 25.0
    FRAME_TIME = 1.0 / TARGET_FPS
    last_frame_time = 0.0

    def run_diarization_worker(pcm_20s_audio: np.ndarray, is_available: bool):
        nonlocal is_diarization_running, last_audio_result
        try:
            res = session.speaker_detector.run_diarization(pcm_20s_audio, is_audio_available=is_available)
            last_audio_result = res
        except Exception as err:
            logger.error(f"Diarization worker error: {err}")
        finally:
            is_diarization_running = False

    while not session.stop_signal.is_set():
        now_loop = time.time()
        if now_loop - last_frame_time < FRAME_TIME:
            time.sleep(0.005)
            continue

        if not session.camera:
            break

        frame = session.camera.get_frame()
        if frame is None:
            time.sleep(0.01)
            continue

        last_frame_time = now_loop

        if config.MIRROR_WEBCAM_FEED:
            frame = cv2.flip(frame, 1)

        total_frames += 1
        frame_count += 1
        now = time.time()
        elapsed = now - start_time
        if elapsed >= 1.0:
            fps = frame_count / elapsed
            frame_count = 0
            start_time = now

        # 1. Face Verification AI
        if (total_frames % config.FRAME_SKIP == 0 or last_face_result is None) and not is_face_running:
            is_face_running = True
            def run_face(f):
                nonlocal last_face_result, is_face_running
                try:
                    last_face_result = session.face_verifier.process(f)
                except Exception as e:
                    logger.error(f"Face verification inference error: {e}")
                finally:
                    is_face_running = False
            threading.Thread(target=run_face, args=(frame.copy(),), daemon=True).start()

        # 2. YOLO Object Detection
        if (total_frames % config.OBJECT_DETECTION_INTERVAL == 0 or last_obj_results is None) and not is_yolo_running:
            is_yolo_running = True
            def run_yolo(f):
                nonlocal last_obj_results, is_yolo_running
                try:
                    res = session.object_detector.process(f)
                    ph = res.get("cell_phone")
                    book = res.get("book")
                    person = res.get("person")
                    evidence_results = []
                    if ph and ph.state == config.STATE_PHONE_DETECTED:
                        evidence_results.append(ph)
                        logger.warning(f"Phone detected in camera frame (Conf: {ph.similarity_score:.2f})")
                    if book and book.state == config.STATE_BOOK_DETECTED:
                        evidence_results.append(book)
                        logger.warning(f"Book/material detected in camera frame (Conf: {book.similarity_score:.2f})")
                    if person and person.state == config.STATE_MULTIPLE_PEOPLE:
                        evidence_results.append(person)
                        logger.warning(f"Multiple people detected in camera frame (Conf: {person.similarity_score:.2f})")
                    if evidence_results and session.ui_renderer:
                        evidence_frame = session.ui_renderer._draw_diagnostics(f.copy(), last_face_result, res, last_head_result)
                        for detector_result in evidence_results:
                            if detector_result.raw_data is not None:
                                detector_result.raw_data["_evidence_frame"] = evidence_frame.copy()
                    last_obj_results = res
                except Exception as e:
                    logger.error(f"Object detection inference error: {e}")
                finally:
                    is_yolo_running = False
            threading.Thread(target=run_yolo, args=(frame.copy(),), daemon=True).start()

        # 3. 3D Head Pose Estimation
        if (total_frames % config.HEAD_POSE_PROCESS_INTERVAL == 0 or last_head_result is None) and not is_head_running:
            is_head_running = True
            def run_head(f, tg_marks):
                nonlocal last_head_result, is_head_running
                try:
                    last_head_result = session.head_pose_detector.process(f, target_landmarks=tg_marks)
                except Exception as e:
                    logger.error(f"Head pose estimation error: {e}")
                finally:
                    is_head_running = False
            tg = last_face_result.landmarks if (last_face_result and last_face_result.face_detected) else None
            threading.Thread(target=run_head, args=(frame.copy(), tg), daemon=True).start()

        # 4. Periodic Speaker Diarization
        if now - last_diarization_launch >= config.DIARIZATION_INTERVAL_SECONDS and not is_diarization_running:
            last_diarization_launch = now
            is_diarization_running = True
            pcm_20s = session.audio_manager.get_recent_audio(duration_sec=config.DIARIZATION_WINDOW_SECONDS)
            threading.Thread(
                target=run_diarization_worker,
                args=(pcm_20s, session.audio_manager.is_available),
                daemon=True
            ).start()

        # 5. Evaluate active violations
        active_results = []
        if last_face_result:
            active_results.append(last_face_result)
        if last_obj_results:
            active_results.extend(last_obj_results.values())
        if last_head_result:
            active_results.append(last_head_result)
        if last_audio_result:
            active_results.append(last_audio_result)

        annotated_evidence_frame = frame.copy()
        if session.ui_renderer:
            annotated_evidence_frame = session.ui_renderer._draw_diagnostics(
                annotated_evidence_frame, last_face_result, last_obj_results, last_head_result
            )

        if active_results and session.violation_mgr:
            session.violation_mgr.update(active_results, annotated_evidence_frame)

        # 6. Update Telemetry State
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

        multi_speakers = bool(last_audio_result and last_audio_result.state == config.STATE_MULTIPLE_SPEAKERS)
        speaker_cnt = int(last_audio_result.raw_data.get("credible_speaker_count", 0)) if (last_audio_result and last_audio_result.raw_data) else 0

        active_viols = session.violation_mgr.get_active_violations() if session.violation_mgr else []
        total_viols = len(session.recent_events)

        with session.lock:
            session.latest_frame = frame
            session.telemetry = {
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
                "fps": round(fps, 1),
            }

            # Generate MJPEG preview frame (scaled down for bandwidth efficiency)
            preview_frame = cv2.resize(annotated_evidence_frame, (480, 270))
            _, buf = cv2.imencode(".jpg", preview_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            session.latest_jpeg = buf.tobytes()

    logger.info("AI Proctoring Worker Loop terminated.")


# ---------------- API Endpoints ----------------

@app.get("/")
def index():
    return {
        "service": "AI Exam Proctoring Service",
        "status": "online",
        "active_session": session.is_active,
        "test_id": session.test_id
    }


@app.get("/api/ai/health")
def health_check():
    return {
        "service": "AI Exam Proctoring Service",
        "status": "online",
        "healthy": True,
        "active_session": session.is_active,
        "test_id": session.test_id,
        "student_id": session.student_id
    }



@app.post("/api/ai/verify-photo")
def verify_candidate_photo(req: VerifyPhotoRequest):
    """
    Pre-flight photo verification endpoint.
    Extracts face embedding from reference photo, grabs 1 webcam frame,
    and returns similarity score and match result.
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
            # Fallback to direct webcam capture
            cap = cv2.VideoCapture(req.cameraIndex)
            if not cap.isOpened():
                return {
                    "success": False,
                    "face_detected": False,
                    "is_match": False,
                    "similarity": 0.0,
                    "threshold": config.FACE_SIMILARITY_THRESHOLD,
                    "message": f"Camera index {req.cameraIndex} is busy or locked by browser. Please allow browser live frame capture."
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
    Starts an end-to-end multimodal AI proctoring session for a candidate taking a test.
    """
    with session.lock:
        if session.is_active:
            if session.test_id == req.testId and session.student_id == req.studentId:
                return {"success": True, "message": "Proctoring session already active for this test", "testId": req.testId}
            # Clean up prior session if different
            session.stop_signal.set()
            if session.worker_thread:
                session.worker_thread.join(timeout=2.0)
            if session.camera:
                session.camera.stop()
            if session.audio_manager:
                session.audio_manager.stop()
            if session.object_detector:
                session.object_detector.stop_worker()
                session.object_detector = None

        session.test_id = req.testId
        session.student_id = req.studentId
        session.student_name = req.studentName or "Candidate"
        session.backend_url = req.backendUrl or config.BACKEND_API_URL
        session.camera_index = req.cameraIndex
        session.recent_events.clear()
        session.stop_signal.clear()

        # 1. Resolve & Enroll Reference Photo
        ref_path = resolve_photo_path(req.photoUrl, req.photoBase64)
        if not ref_path:
            logger.warning(f"Reference photo not found for {req.photoUrl}. Falling back to default.")
            ref_path = config.STUDENT_REFERENCE_IMAGE

        try:
            session.face_verifier = FaceVerifier(similarity_threshold=config.FACE_SIMILARITY_THRESHOLD)
            if ref_path and ref_path.exists():
                session.face_verifier.enroll_reference(str(ref_path))
                logger.info(f"Student enrolled successfully from: {ref_path}")
            else:
                logger.warning("Starting session without reference face enrollment (Face presence only).")
        except Exception as e:
            logger.warning(f"Face verification enrollment warning: {e}. Running with face-presence mode.")

        # 2. Initialize Object Detector (YOLOv11)
        try:
            session.object_detector = ObjectDetector(model_name=config.YOLO_MODEL, img_size=config.YOLO_IMAGE_SIZE)
        except Exception as e:
            logger.error(f"Failed to load ObjectDetector: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to load YOLO model: {e}")

        # 3. Initialize Head Pose Detector
        try:
            session.head_pose_detector = HeadPoseDetector()
            session.head_pose_detector.start_calibration(config.HEAD_POSE_CALIBRATION_SECONDS)
        except Exception as e:
            logger.error(f"Failed to load HeadPoseDetector: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to load Head Pose Detector: {e}")

        # 4. Initialize Audio Diarization
        session.audio_manager = AudioManager(buffer_duration=config.DIARIZATION_WINDOW_SECONDS)
        session.audio_manager.start()
        session.speaker_detector = SpeakerDetector()

        # 5. Initialize Camera
        session.camera = CameraManager(camera_index=req.cameraIndex, width=config.WEBCAM_WIDTH, height=config.WEBCAM_HEIGHT)
        if not session.camera.start():
            session.audio_manager.stop()
            raise HTTPException(status_code=500, detail=f"Cannot initialize camera at index {req.cameraIndex}")

        # 6. Initialize Violation Manager with auto-backend hook
        session.violation_logger = ViolationLogger()
        session.violation_mgr = ViolationManager(
            logger_instance=session.violation_logger,
            on_violation_start=forward_violation_to_backend
        )
        session.ui_renderer = ProctoringUI()

        # 7. Start worker loop
        session.is_active = True
        session.worker_thread = threading.Thread(target=proctoring_loop, daemon=True)
        session.worker_thread.start()

        logger.info(f"AI Proctoring session started successfully for Test: {req.testId}, Student: {req.studentId}")

        return {
            "success": True,
            "message": "AI Proctoring Session Active",
            "testId": session.test_id,
            "studentId": session.student_id,
            "backendUrl": session.backend_url
        }


@app.post("/api/ai/stop-session")
def stop_proctoring_session():
    """
    Safely terminates the active proctoring session, releases camera and microphone,
    and posts the final session summary to the Express backend.
    """
    with session.lock:
        if not session.is_active:
            return {"success": True, "message": "No active proctoring session to stop"}

        logger.info(f"Stopping AI Proctoring session for Test: {session.test_id}")
        session.stop_signal.set()
        if session.worker_thread:
            session.worker_thread.join(timeout=3.0)

        if session.camera:
            session.camera.stop()
            session.camera = None

        if session.audio_manager:
            session.audio_manager.stop()
            session.audio_manager = None

        if session.object_detector:
            session.object_detector.stop_worker()
            session.object_detector = None

        forward_summary_to_backend("Proctoring session ended normally upon exam completion")

        session.is_active = False
        test_id = session.test_id
        session.test_id = None
        session.student_id = None

        return {"success": True, "message": "AI Proctoring Session Stopped", "testId": test_id}


@app.get("/api/ai/status")
def get_session_status():
    """
    Returns live proctoring telemetry and recent infraction events for the web client.
    """
    with session.lock:
        return {
            "active": session.is_active,
            "testId": session.test_id,
            "studentId": session.student_id,
            "telemetry": session.telemetry,
            "events": list(session.recent_events)
        }


def generate_mjpeg_stream():
    """Generator yielding JPEG multipart boundary frames for live streaming."""
    blank_frame = np.zeros((270, 480, 3), dtype=np.uint8)
    cv2.putText(blank_frame, "AI Proctoring Standby", (80, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (150, 150, 150), 2)
    _, blank_jpeg = cv2.imencode(".jpg", blank_frame)
    blank_bytes = blank_jpeg.tobytes()

    while True:
        with session.lock:
            frame_bytes = session.latest_jpeg or blank_bytes
            active = session.is_active

        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
        time.sleep(0.04)  # ~25 FPS


@app.get("/api/ai/video-feed")
def video_feed():
    """
    Streams live MJPEG camera feed with AI telemetry overlays for the in-browser HUD.
    """
    return StreamingResponse(
        generate_mjpeg_stream(),
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
