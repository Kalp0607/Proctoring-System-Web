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
# YOLOv11n: PyTorch checkpoint
YOLO_MODEL = "yolo11n.pt"

# Backend & Service Integration Config
BACKEND_API_URL = os.environ.get("BACKEND_API_URL", "http://localhost:5000/api/proctoring")
AI_SERVICE_PORT = int(os.environ.get("AI_SERVICE_PORT", "8000"))
AI_SERVICE_HOST = os.environ.get("AI_SERVICE_HOST", "0.0.0.0")

# Inference image size (imgsz): 320, 640, or 960
YOLO_IMAGE_SIZE = 640                # High accuracy (33ms inference)

# --- Multi-Stage Phone Detection Pipeline Configuration ---
PHONE_DETECTION_CONFIG = {
    # Inference Resolutions
    "full_frame_imgsz": 640,            # Primary full-frame YOLO resolution (640 for fast real-time performance)
    "roi_imgsz": 640,                   # High-res Person-ROI inspection resolution
    "roi_padding": 0.25,                # Expanded crop margin around student body (25% on each side)

    # Dual-Threshold Strategy (High Detector Recall + Strict Violation Confirmation)
    # Lowered from 0.25 → 0.15: Sentinel model returns ~0.086 on partially-visible edge phones;
    # 0.15 gives them a chance to enter the temporal pipeline without greatly increasing FP rate.
    "candidate_confidence": 0.15,       # Candidate generation threshold for high recall
    "violation_confidence": 0.35,       # Individual detection confidence required for positive evidence

    # Temporal Aggregation & State Machine
    "temporal_window": 8,               # Rolling frame window size
    "min_positive_frames": 4,           # Required positive frames within window to confirm violation
    "cooldown_seconds": 3.0,            # Cooldown duration after violation resolution

    # Lightweight Multi-Frame Tracking
    "tracking_enabled": True,
    "track_max_age": 8,                 # Increased: retain track longer through confidence dips
    "track_iou_threshold": 0.25,        # Minimum IoU to associate candidate with existing track
    "track_center_dist_threshold": 120.0, # Increased: allow larger jumps for moving phones

    # Adaptive SAHI (Sliced Slicing Fallback)
    "sahi_enabled": True,               # Enable adaptive slicing fallback for difficult/uncertain detections
    "sahi_slice_size": 384,             # Slice dimension (384x384)
    "sahi_overlap": 0.30,               # Increased overlap for better edge coverage
    # Trigger SAHI more aggressively: any frame with a person and no confident phone gets sliced
    "sahi_trigger_min_conf": 0.10,      # Lower band (was 0.20): catch very low-conf candidates too
    "sahi_trigger_max_conf": 0.40,      # If candidate conf >= 0.40, full/ROI pass is already confident
    "sahi_min_person_area_ratio": 0.15, # Minimum person area ratio before triggering fallback

    # Hand Proximity & Context Validation
    "hand_context_enabled": True,
    "hand_proximity_radius": 180,       # Increased radius for better hand-phone association
    "hand_proximity_boost": 0.12,       # Confidence boost when phone is held or near student hand

    # Physical Smartphone Geometry Constraints
    "min_pixel_area": 200,              # Lowered from 300: allow slightly smaller/distant phones
    "max_area_ratio": 0.30,             # Increased from 0.25: allow close-up phones
    "max_width_ratio": 0.65,            # Increased from 0.60
    "max_height_ratio": 0.80,           # Increased from 0.75
    "min_aspect_ratio": 0.8,            # Lowered from 1.0: allow nearly-square phones (landscape mode)
    "max_aspect_ratio": 6.0,            # Increased from 5.0: allow very tall phone crops

    # Static Background Suppression
    "static_consecutive_cycles": 8,     # Increased: need more evidence before suppressing
    "static_iou_threshold": 0.50        # Increased: require more overlap to classify as static
}

# Shortcut tokens for backwards compatibility
PHONE_CONFIDENCE_THRESHOLD = PHONE_DETECTION_CONFIG["violation_confidence"]
PHONE_CANDIDATE_THRESHOLD = PHONE_DETECTION_CONFIG["candidate_confidence"]
DEDICATED_PHONE_CONFIRM_THRESHOLD = PHONE_DETECTION_CONFIG["violation_confidence"]
PERSON_CONFIDENCE_THRESHOLD = 0.60
BOOK_CONFIDENCE_THRESHOLD = 0.40

# Dedicated Model Weights
PHONE_DEDICATED_MODEL = "sentinelvision_yolov8n.pt"
PHONE_DEDICATED_MODEL_2 = None       # Disabled: faulty checkpoint
ENABLE_TWO_STAGE_PHONE_DETECTION = True
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

# Run shared YOLO object detection as fast as possible (guarded by is_yolo_running flag)
# OBJECT_DETECTION_INTERVAL=1 means: try every frame, but the is_yolo_running guard prevents
# concurrent runs. Detection fires immediately when the previous inference completes.
OBJECT_DETECTION_INTERVAL = 1        # Try every frame; is_yolo_running prevents overlap
PERSON_DETECTION_INTERVAL = OBJECT_DETECTION_INTERVAL

# Continuous temporal confirmation thresholds (in seconds)
MULTIPLE_PERSON_CONFIRM_SECONDS = 2.0
PHONE_CONFIRM_SECONDS = 0.1          # Instant confirmation on phone detection (instant popup banner & screenshot)
BOOK_CONFIRM_SECONDS = 1.5

# Stage 3.5 Rolling Window Temporal Ratio Smoothing Parameters
TEMPORAL_WINDOW_SIZE = 5            # Rolling history window
PHONE_WINDOW_MIN_DETECTIONS = 1     # Immediately confirm on positive detection cycle (instant pop-up)

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
OBJECT_CLEAR_GRACE_SECONDS = 1.2

# Execution device ('cpu', 'cuda', '0', etc. Defaults to 'cpu' or auto GPU if available)
DEVICE = "cpu"

# Minimum cooldown duration (in seconds) between resolving an episode and creating a new one of the same type
VIOLATION_COOLDOWN_SEC = 1.0

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
