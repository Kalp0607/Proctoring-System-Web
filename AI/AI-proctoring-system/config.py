import os
from pathlib import Path

# Base Directory of the Project
BASE_DIR = Path(__file__).resolve().parent

# --- File & Directory Paths ---
DATA_DIR = BASE_DIR / "data"
REFERENCE_DIR = DATA_DIR / "reference"
STUDENT_REFERENCE_IMAGE = REFERENCE_DIR / "student.jpg"

MODELS_DIR = BASE_DIR / "models"
VIOLATIONS_DIR = BASE_DIR / "violations"
SCREENSHOTS_DIR = VIOLATIONS_DIR / "screenshots"
VIOLATION_LOG_FILE = VIOLATIONS_DIR / "violations.json"

# Screenshot Evidence Settings
SAVE_SCREENSHOTS_FOR_AUDIO = False  # Disabled: No screenshot capture for audio/speech violations

# Ensure directories exist
REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

# --- Stage 1 Detector & Verification Thresholds ---
# Cosine similarity threshold for face verification (InsightFace/ArcFace embeddings)
FACE_SIMILARITY_THRESHOLD = 0.45

# Continuous time (in seconds) before a FACE_MISSING state creates a confirmed violation episode
FACE_MISSING_THRESHOLD_SEC = 3.0

# Continuous time (in seconds) before an IDENTITY_MISMATCH state creates a confirmed violation episode
IDENTITY_MISMATCH_THRESHOLD_SEC = 3.0

# --- Stage 2, 3, & 3.5 Object Detector Thresholds ---
# Ultralytics YOLO model selection — base COCO model for person, book, remote detection
# yolo11n.onnx: ONNX-optimized for maximum CPU speed (~2x faster than .pt)
YOLO_MODEL = "yolo11n.onnx"

# Backend & Service Integration Config
BACKEND_API_URL = os.environ.get("BACKEND_API_URL", "http://localhost:5000/api/proctoring")
AI_SERVICE_PORT = int(os.environ.get("AI_SERVICE_PORT", "8000"))
AI_SERVICE_HOST = os.environ.get("AI_SERVICE_HOST", "0.0.0.0")

# Inference image size (imgsz): 320, 384, 480, or 640
YOLO_IMAGE_SIZE = 480                # Standard YOLO resolution for balanced speed & accuracy

# --- Multi-Stage Phone Detection Pipeline Configuration ---
PHONE_DETECTION_CONFIG = {
    # Inference Resolutions
    "full_frame_imgsz": 480,            # Primary full-frame YOLO resolution (480 for fast real-time performance)
    "roi_imgsz": 480,                   # Person-ROI inspection resolution
    "roi_padding": 0.25,                # Expanded crop margin around student body (25% on each side)

    # Dual-Threshold Strategy (High Detector Recall + Strict Violation Confirmation)
    "candidate_confidence": 0.45,       # Phone detection threshold — only high-confidence detections tracked
    "violation_confidence": 0.45,       # Confirmation threshold (same as candidate for instant confirm)

    # Temporal Aggregation & State Machine — instant detection
    "temporal_window": 2,               # 2-frame rolling window (confirm on 1st hit)
    "min_positive_frames": 1,           # Confirm on the very first positive YOLO frame
    "cooldown_seconds": 0.0,            # No cooldown — box clears the moment phone leaves frame

    # Lightweight Multi-Frame Tracking
    "tracking_enabled": True,
    "track_max_age": 1,                 # Purge stale track within 1 missed inference cycle
    "track_iou_threshold": 0.25,        # Minimum IoU to associate candidate with existing track
    "track_center_dist_threshold": 120.0, # Spatial gating for moving phones

    # Hand Proximity & Context Validation
    "hand_context_enabled": False,
    "hand_proximity_radius": 180,
    "hand_proximity_boost": 0.12,

    # Physical Smartphone Geometry Constraints
    "min_pixel_area": 150,              # Allow realistic phone crops
    "max_area_ratio": 0.50,
    "max_width_ratio": 0.85,
    "max_height_ratio": 0.90,
    "min_aspect_ratio": 0.8,
    "max_aspect_ratio": 6.0,

    # Static Background Suppression
    "static_consecutive_cycles": 8,
    "static_iou_threshold": 0.50
}

# General YOLO Detection Thresholds
PHONE_CONFIDENCE_THRESHOLD = PHONE_DETECTION_CONFIG["violation_confidence"]
PHONE_CANDIDATE_THRESHOLD = PHONE_DETECTION_CONFIG["candidate_confidence"]
DEDICATED_PHONE_CONFIRM_THRESHOLD = PHONE_DETECTION_CONFIG["violation_confidence"]
PERSON_CONFIDENCE_THRESHOLD = 0.40
BOOK_CONFIDENCE_THRESHOLD = 0.35

# Single Unified YOLO11n Model Only (Secondary/Dedicated models removed)
PHONE_DEDICATED_MODEL = None
PHONE_DEDICATED_MODEL_2 = None
ENABLE_TWO_STAGE_PHONE_DETECTION = False
HAND_DETECTION_CONFIDENCE = 0.40
HAND_ROI_PADDING = 0.50

# Person filtering parameters to prevent duplicate person detections and hand false positives
PERSON_IOU_THRESHOLD = 0.40          # IoU NMS threshold for duplicate person box suppression
MIN_PERSON_BOX_AREA = 0.03           # Minimum box area as fraction of frame (e.g. 3% = ~27.6k pixels at 1280x720)
PERSON_CONTAINMENT_THRESHOLD = 0.50  # Max allowed containment ratio of smaller sub-box inside larger body

# Camera Mirroring & Diagnostic Debug Mode
MIRROR_WEBCAM_FEED = True            # Single-point horizontal flipping at camera frame capture
SHOW_COORDINATE_DEBUG = False        # Disabled: clean camera feed for user

# --- Stage 5 Live Microphone Audio & Speaker Diarization Thresholds ---
AUDIO_ENABLED = True
AUDIO_SAMPLE_RATE = 16000            # Standard 16kHz mono audio sampling rate
AUDIO_CHANNELS = 1
AUDIO_CHUNK_SIZE = 1024

# Voice Activity Detection (VAD) Energy Threshold
VAD_ENERGY_THRESHOLD = 0.001

# Rolling Diarization Window & Periodic Analysis Settings
DIARIZATION_WINDOW_SECONDS = 20.0    # Rolling audio window duration (20 seconds)
DIARIZATION_INTERVAL_SECONDS = 4.0   # Run periodic diarization analysis every 4 seconds

# Minimum accumulated speech duration (seconds) inside window for a speaker label to be credible
MIN_DIARIZED_SPEAKER_SECONDS = 1.0

# Multi-Window Confirmation: required consecutive windows with 2+ credible speakers to trigger violation
MULTIPLE_SPEAKER_CONFIRM_WINDOWS = 2
MULTIPLE_SPEAKER_CONFIRM_SECONDS = 3.0
MULTIPLE_SPEAKER_CLEAR_GRACE_SECONDS = 3.0

# Cosine Distance threshold for Agglomerative Linkage Clustering (0.22 threshold for distinct voice separation)
SPEAKER_DISTANCE_THRESHOLD = 0.22

# Console & UI Diarization Telemetry Debug Mode
SHOW_DIARIZATION_DEBUG = False

# Cadence matching Face Verification (every 3rd frame)
OBJECT_DETECTION_INTERVAL = 3        # Run every 3rd frame, matching FaceVerifier cadence
PERSON_DETECTION_INTERVAL = OBJECT_DETECTION_INTERVAL

# Continuous temporal confirmation thresholds (in seconds)
MULTIPLE_PERSON_CONFIRM_SECONDS = 0.0   # Instant confirmation on detection (instant screenshot)
PHONE_CONFIRM_SECONDS = 0.0             # Instant confirmation on phone detection (instant popup banner & screenshot)
BOOK_CONFIRM_SECONDS = 0.0              # Instant confirmation on book detection (instant screenshot)

# Stage 3.5 Rolling Window Temporal Ratio Smoothing Parameters
TEMPORAL_WINDOW_SIZE = 5            # Rolling history window
PHONE_WINDOW_MIN_DETECTIONS = 1     # Immediately confirm on positive detection cycle (instant pop-up)

# Stage 3 YOLO Object Detection Smoothing & Acceleration (EMA filters like Head Pose)
OBJECT_TRACKER_BBOX_ALPHA = 0.55     # EMA smoothing factor for object bounding box interpolation (eliminates box jitter)
OBJECT_TRACKER_CONF_ALPHA = 0.65     # EMA smoothing factor for object detection confidence
OBJECT_TRACKER_MAX_AGE = 6           # Coasting frames: maintains tracking continuity through brief drops/occlusions
OBJECT_TRACKER_IOU_THRESH = 0.30     # Spatial IoU matching threshold

# --- Stage 4 Head Pose Estimation & Screen-Adaptive Thresholds ---
def detect_display_metrics():
    """
    Automatically detects connected display physical size and pixel resolution
    via Windows GDI to compute optimal, screen-adaptive head pose angle thresholds.
    """
    import math
    w_px, h_px = 1920, 1080
    w_mm, h_mm = 310, 175  # ~14 inch laptop default fallback
    try:
        import ctypes
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass
        hdc = user32.GetDC(0)
        w_px = user32.GetSystemMetrics(0)
        h_px = user32.GetSystemMetrics(1)
        w_mm = gdi32.GetDeviceCaps(hdc, 4)  # HORZSIZE in mm
        h_mm = gdi32.GetDeviceCaps(hdc, 6)  # VERTSIZE in mm
        user32.ReleaseDC(0, hdc)
    except Exception:
        pass

    # Validate physical size
    if w_mm < 100 or h_mm < 60:
        w_mm, h_mm = 310, 175

    # Estimate viewing distance based on display width
    # (laptops ~45-50cm, desktop monitors ~60-70cm)
    dist_mm = max(450.0, min(700.0, w_mm * 1.3))

    half_yaw_deg = math.degrees(math.atan((w_mm / 2.0) / dist_mm))
    half_pitch_deg = math.degrees(math.atan((h_mm / 2.0) / dist_mm))

    # Add comfortable eye/head movement margin (+5.0° yaw, +4.0° pitch)
    # to eliminate false positives when scanning screen corners/toolbars
    yaw_thr = max(20.0, round(half_yaw_deg + 5.0, 1))
    pitch_thr = max(18.0, round(half_pitch_deg + 4.0, 1))
    diag_inches = round(math.sqrt(w_mm**2 + h_mm**2) / 25.4, 1)

    info = {
        "resolution": f"{w_px}x{h_px}",
        "width_px": w_px,
        "height_px": h_px,
        "width_mm": w_mm,
        "height_mm": h_mm,
        "size_mm": f"{w_mm}mm x {h_mm}mm",
        "diag_inches": diag_inches,
        "dist_cm": round(dist_mm / 10.0, 1)
    }
    return yaw_thr, pitch_thr, info

# Automatically compute screen-adaptive thresholds on startup
HEAD_YAW_THRESHOLD, HEAD_PITCH_THRESHOLD, DETECTED_DISPLAY_INFO = detect_display_metrics()
DISPLAY_WIDTH_MM = DETECTED_DISPLAY_INFO.get("width_mm", 300.0)
DISPLAY_HEIGHT_MM = DETECTED_DISPLAY_INFO.get("height_mm", 190.0)

# Distance-Adaptive Head Pose Deviation Threshold Parameters
HEAD_POSE_YAW_MARGIN = 10.0         # Base comfort margin (deg) added to screen half-angle
HEAD_POSE_PITCH_MARGIN = 14.0       # Base comfort margin (deg) added to screen vertical half-angle (prevents false positives when glancing at screen)
HEAD_POSE_MIN_YAW_THRESHOLD = 26.0  # Minimum allowable yaw threshold (degrees)
HEAD_POSE_MAX_YAW_THRESHOLD = 45.0  # Maximum allowable yaw threshold (degrees)
HEAD_POSE_MIN_PITCH_THRESHOLD = 26.0 # Minimum allowable pitch threshold (degrees)
HEAD_POSE_MAX_PITCH_THRESHOLD = 40.0 # Maximum allowable pitch threshold (degrees)
HEAD_POSE_DISTANCE_ALPHA = 0.25     # EMA smoothing factor for real-time estimated distance

# Temporal confirmation threshold for LOOKING_AWAY (in seconds)
# 1.0s prevents momentary glances across the screen from false-triggering
HEAD_POSE_CONFIRM_SECONDS = 1.0

# Grace period (in seconds) before clearing pending/active LOOKING_AWAY state
HEAD_POSE_CLEAR_GRACE_SECONDS = 0.5 # Prompt resolution when head returns to center

# Exponential moving average (EMA) smoothing factor (0.0 to 1.0; 0.4 = smooth)
HEAD_POSE_ALPHA = 0.4

# Per-session baseline calibration duration (in seconds)
HEAD_POSE_CALIBRATION_SECONDS = 1.5

# Number of frames to accumulate for multi-frame baseline calibration (median-based)
HEAD_POSE_CALIBRATION_FRAMES = 30

# Process head pose estimation every Nth frame
HEAD_POSE_PROCESS_INTERVAL = 1

# Toggle 3D nose orientation vector & debug overlays
SHOW_HEAD_POSE_DEBUG = False

# Grace period (in seconds) for intermittent detection drops before clearing pending violations
# 0.0 allows boxes and violations to disappear as soon as object is not on screen
OBJECT_CLEAR_GRACE_SECONDS = 0.0
PHONE_CLEAR_GRACE_SECONDS = 0.0

# Execution device ('cpu', 'cuda', '0', etc. Defaults to 'cpu' or auto GPU if available)
DEVICE = "cpu"

# Minimum cooldown duration (in seconds) between resolving an episode and creating a new one of the same type
VIOLATION_COOLDOWN_SEC = 0.0

# --- Performance & Camera Settings ---
WEBCAM_INDEX = 0
WEBCAM_WIDTH = 1280
WEBCAM_HEIGHT = 720
FRAME_SKIP = 3  # Run AI face detection every Nth frame (fast landmark updates)

# --- UI & Visual Settings ---
SHOW_DIAGNOSTICS = False  # Disabled by default: clean camera feed for exam. Press 'd' anytime to toggle diagnostic mode.
UI_CANVAS_WIDTH = int(DETECTED_DISPLAY_INFO.get("width_px", 1920))
UI_CANVAS_HEIGHT = int(DETECTED_DISPLAY_INFO.get("height_px", 1080))
UI_SIDE_PANEL_WIDTH = 380

# State Names
STATE_VERIFIED = "VERIFIED"
STATE_IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
STATE_FACE_MISSING = "FACE_MISSING"
STATE_MULTIPLE_FACES = "MULTIPLE_FACES"

# Stage 2, 3, 4 & 5 Detection States
STATE_NORMAL = "NORMAL"
STATE_MULTIPLE_PEOPLE = "MULTIPLE_PEOPLE"
STATE_PHONE_DETECTED = "PHONE_DETECTED"
STATE_BOOK_DETECTED = "BOOK_DETECTED"
STATE_LOOKING_AWAY = "LOOKING_AWAY"
STATE_MULTIPLE_SPEAKERS = "MULTIPLE_SPEAKERS"
