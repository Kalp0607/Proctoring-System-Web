# pyrefly: ignore [missing-import]
import cv2
# pyrefly: ignore [missing-import]
import numpy as np
import logging
import math
import time
from typing import Optional, Tuple, List, Dict, Any

from detectors.base_detector import BaseDetector, DetectorResult
import config

logger = logging.getLogger(__name__)


class HeadPoseDetector(BaseDetector):
    """
    3D Head Pose Detector using OpenCV solvePnP and RetinaFace landmarks.
    Provides true Euler angles (Yaw, Pitch, Roll) in degrees to guarantee 
    mathematical symmetry for all directions (Up, Down, Left, Right).
    """

    def __init__(self):
        self.detector_name = "HeadPoseDetector"

        self.is_calibrated = False
        self.baseline_yaw: float = 0.0
        self.baseline_pitch: float = 0.0

        self.YAW_THRESHOLD = config.HEAD_YAW_THRESHOLD
        self.PITCH_THRESHOLD = config.HEAD_PITCH_THRESHOLD

        # Real-time distance tracking (in mm)
        self.smooth_dist_mm: Optional[float] = None
        self.dist_alpha = getattr(config, 'HEAD_POSE_DISTANCE_ALPHA', 0.25)
        self.baseline_dist_mm: float = 450.0

        # Physical screen dimensions from config
        self.screen_w_mm = getattr(config, 'DISPLAY_WIDTH_MM', 300.0)
        self.screen_h_mm = getattr(config, 'DISPLAY_HEIGHT_MM', 190.0)

        # Dynamic thresholds based on distance
        self.current_yaw_threshold = self.YAW_THRESHOLD
        self.current_pitch_threshold = self.PITCH_THRESHOLD

        # EMA smoothing factor (applied per-frame to reduce jitter)
        self.alpha = config.HEAD_POSE_ALPHA

        # EMA-smoothed angles (these are what we use for classification)
        self.smooth_yaw: float = 0.0
        self.smooth_pitch: float = 0.0
        self.smooth_roll: float = 0.0
        self._ema_initialized: bool = False

        # Retain last known raw angles for debugging
        self.last_yaw = 0.0
        self.last_pitch = 0.0
        self.last_roll = 0.0

        # Multi-frame calibration state
        self._calibration_samples: List[Tuple[float, float]] = []
        self._calibration_dist_samples: List[float] = []
        self._calibration_target_frames = getattr(config, 'HEAD_POSE_CALIBRATION_FRAMES', 30)
        self._calibration_active = True  # Start collecting from first frame

        disp_info = getattr(config, 'DETECTED_DISPLAY_INFO', {})
        logger.info(
            f"HeadPoseDetector: Screen-Adaptive Thresholds initialized -> "
            f"Base Yaw ±{self.YAW_THRESHOLD}°, Pitch ±{self.PITCH_THRESHOLD}° "
            f"(Display: {disp_info.get('diag_inches', '?')}\" {disp_info.get('resolution', '')})"
        )

        # Anthropometric 3D canonical facial model points (in mm)
        # Scaled 1:1 to human facial anatomy matching InsightFace/RetinaFace 5 landmarks:
        # Left eye pupil: (-32mm, -32mm, -35mm)
        # Right eye pupil: (+32mm, -32mm, -35mm)  (64mm interpupillary distance)
        # Nose tip: (0mm, 0mm, 0mm) origin
        # Left mouth corner: (-25mm, +45mm, -25mm)
        # Right mouth corner: (+25mm, +45mm, -25mm) (50mm mouth width)
        self.model_points = np.array([
            (-32.0, -32.0, -35.0),    # Left eye pupil (negative X = left in face coords)
            ( 32.0, -32.0, -35.0),    # Right eye pupil (positive X = right in face coords)
            (  0.0,   0.0,   0.0),    # Nose tip (origin)
            (-25.0,  45.0, -25.0),    # Left mouth corner
            ( 25.0,  45.0, -25.0)     # Right mouth corner
        ], dtype=np.float64)

        # Forward-pointing 3D axis for nose ray projection (120mm forward from nose tip)
        self.nose_end_point_3D = np.array([(0.0, 0.0, 120.0)], dtype=np.float64)

        # Dist coeffs (assume no lens distortion)
        self.dist_coeffs = np.zeros((4, 1), dtype=np.float64)

        # Cache last successful solvePnP outputs for nose ray drawing
        self._last_rvec = None
        self._last_tvec = None
        self._last_camera_matrix = None

        # Debug logging throttle
        self._last_debug_log_time = 0.0

    def start_calibration(self, duration_sec: float = 2.0):
        """Resets calibration state to begin collecting new baseline samples."""
        self._calibration_samples = []
        self._calibration_dist_samples = []
        self._calibration_active = True
        self.is_calibrated = False
        self._ema_initialized = False
        self.smooth_dist_mm = None
        logger.info(f"Calibration started: collecting {self._calibration_target_frames} frames for baseline.")

    def estimate_distance_mm(self, image_points: np.ndarray, frame_width: int) -> float:
        """
        Estimates viewing distance in millimeters using human Inter-Pupillary Distance (IPD ~63mm)
        and camera focal length geometry.
        """
        left_eye, right_eye = image_points[0], image_points[1]
        eye_dist_px = math.hypot(right_eye[0] - left_eye[0], right_eye[1] - left_eye[1])

        if eye_dist_px < 5.0:
            return 450.0  # Fallback standard distance

        # Typical webcam HFOV is ~68-70 deg -> focal_px ~ 0.75 * width
        focal_px = 0.75 * frame_width
        dist_mm = (focal_px * 63.0) / eye_dist_px

        # Clamp to realistic human viewing distance bounds (250mm to 900mm)
        return max(250.0, min(900.0, dist_mm))

    def compute_dynamic_thresholds(self, dist_mm: float) -> Tuple[float, float]:
        """
        Computes distance-adaptive yaw and pitch deviation thresholds.
        As a person gets closer (smaller dist_mm), the visual angle to the screen perimeter
        increases: theta = atan((screen_dim / 2) / dist).
        Comfort margins are added to permit natural gaze shifts across the display.
        """
        safe_dist = max(200.0, dist_mm)
        half_yaw_deg = math.degrees(math.atan((self.screen_w_mm / 2.0) / safe_dist))
        half_pitch_deg = math.degrees(math.atan((self.screen_h_mm / 2.0) / safe_dist))

        # Proximity boost when leaning close (< 45cm)
        proximity_boost = max(0.0, (450.0 - safe_dist) / 450.0) * 3.0

        yaw_thr = half_yaw_deg + getattr(config, 'HEAD_POSE_YAW_MARGIN', 8.0) + proximity_boost
        pitch_thr = half_pitch_deg + getattr(config, 'HEAD_POSE_PITCH_MARGIN', 6.0) + (proximity_boost * 0.5)

        # Clamp within configured bounds
        yaw_thr = max(
            getattr(config, 'HEAD_POSE_MIN_YAW_THRESHOLD', 22.0),
            min(getattr(config, 'HEAD_POSE_MAX_YAW_THRESHOLD', 42.0), yaw_thr)
        )
        pitch_thr = max(
            getattr(config, 'HEAD_POSE_MIN_PITCH_THRESHOLD', 18.0),
            min(getattr(config, 'HEAD_POSE_MAX_PITCH_THRESHOLD', 35.0), pitch_thr)
        )

        return round(yaw_thr, 1), round(pitch_thr, 1)

    def _extract_euler_angles(self, rmat: np.ndarray) -> Tuple[float, float, float]:
        """
        Extracts Euler angles (pitch, yaw, roll) from a 3x3 rotation matrix
        using manual atan2 decomposition (Tait-Bryan ZYX convention).
        
        This gives deterministic, mathematically correct angles independent
        of any OpenCV decomposition function's internal conventions.
        
        Returns:
            (pitch, yaw, roll) in degrees
        """
        sy = math.sqrt(rmat[0, 0] ** 2 + rmat[1, 0] ** 2)
        singular = sy < 1e-6

        if not singular:
            pitch = math.atan2(rmat[2, 1], rmat[2, 2])   # Rotation around X-axis
            yaw = math.atan2(-rmat[2, 0], sy)              # Rotation around Y-axis
            roll = math.atan2(rmat[1, 0], rmat[0, 0])      # Rotation around Z-axis
        else:
            pitch = math.atan2(-rmat[1, 2], rmat[1, 1])
            yaw = math.atan2(-rmat[2, 0], sy)
            roll = 0.0

        return math.degrees(pitch), math.degrees(yaw), math.degrees(roll)

    def _apply_ema(self, raw_yaw: float, raw_pitch: float, raw_roll: float) -> Tuple[float, float, float]:
        """
        Applies Exponential Moving Average smoothing to reduce frame-to-frame jitter.
        Uses config.HEAD_POSE_ALPHA as the smoothing factor (higher = more responsive, lower = smoother).
        """
        if not self._ema_initialized:
            self.smooth_yaw = raw_yaw
            self.smooth_pitch = raw_pitch
            self.smooth_roll = raw_roll
            self._ema_initialized = True
        else:
            self.smooth_yaw = self.alpha * raw_yaw + (1.0 - self.alpha) * self.smooth_yaw
            self.smooth_pitch = self.alpha * raw_pitch + (1.0 - self.alpha) * self.smooth_pitch
            self.smooth_roll = self.alpha * raw_roll + (1.0 - self.alpha) * self.smooth_roll

        return self.smooth_yaw, self.smooth_pitch, self.smooth_roll

    def process(self, frame: np.ndarray, target_landmarks: Optional[List[Tuple[int, int]]] = None) -> DetectorResult:
        """
        Estimates 3D head pose (Yaw, Pitch, Roll) using 5 landmarks via solvePnP.
        """
        if frame is None or frame.size == 0:
            return DetectorResult(
                detector_name=self.detector_name,
                state=config.STATE_NORMAL,
                message="Received empty frame"
            )

        nose_pt = None

        if target_landmarks is not None and len(target_landmarks) == 5:
            # Sort landmarks by X coordinate to guarantee correct anatomical mapping regardless of mirroring
            eyes = sorted([target_landmarks[0], target_landmarks[1]], key=lambda p: p[0])
            mouths = sorted([target_landmarks[3], target_landmarks[4]], key=lambda p: p[0])
            nose_pt = target_landmarks[2]

            image_points = np.array([
                eyes[0],    # Leftmost eye
                eyes[1],    # Rightmost eye
                nose_pt,    # Nose
                mouths[0],  # Leftmost mouth corner
                mouths[1]   # Rightmost mouth corner
            ], dtype=np.float64)

            # Approximate camera matrix based on frame size
            h, w = frame.shape[:2]
            focal_length = w
            center = (w / 2.0, h / 2.0)
            camera_matrix = np.array([
                [focal_length, 0, center[0]],
                [0, focal_length, center[1]],
                [0, 0, 1]
            ], dtype=np.float64)

            # Solve PnP
            success, rvec, tvec = cv2.solvePnP(
                self.model_points, 
                image_points, 
                camera_matrix, 
                self.dist_coeffs, 
                flags=cv2.SOLVEPNP_SQPNP
            )

            if success:
                # Convert rotation vector to rotation matrix
                rmat, _ = cv2.Rodrigues(rvec)

                # Extract Euler angles using deterministic atan2 decomposition
                raw_pitch, raw_yaw, raw_roll = self._extract_euler_angles(rmat)

                # Store raw values for debugging
                self.last_pitch = raw_pitch
                self.last_yaw = raw_yaw
                self.last_roll = raw_roll

                # Apply EMA smoothing to reduce jitter
                self.smooth_yaw, self.smooth_pitch, self.smooth_roll = self._apply_ema(
                    raw_yaw, raw_pitch, raw_roll
                )

                # Cache for nose ray projection
                self._last_rvec = rvec
                self._last_tvec = tvec
                self._last_camera_matrix = camera_matrix

                # Real-time distance estimation and dynamic threshold calculation
                dist_mm = self.estimate_distance_mm(image_points, w)
                if self.smooth_dist_mm is None:
                    self.smooth_dist_mm = dist_mm
                else:
                    self.smooth_dist_mm = self.dist_alpha * dist_mm + (1.0 - self.dist_alpha) * self.smooth_dist_mm

                self.current_yaw_threshold, self.current_pitch_threshold = self.compute_dynamic_thresholds(
                    self.smooth_dist_mm
                )

        # Use EMA-smoothed angles for all classification
        yaw = self.smooth_yaw
        pitch = self.smooth_pitch
        roll = self.smooth_roll
        dist_cm = round((self.smooth_dist_mm or 450.0) / 10.0, 1)

        # Multi-frame calibration: accumulate samples before locking baseline
        if self._calibration_active and target_landmarks is not None and self._ema_initialized:
            self._calibration_samples.append((yaw, pitch))
            if self.smooth_dist_mm is not None:
                self._calibration_dist_samples.append(self.smooth_dist_mm)

            if len(self._calibration_samples) >= self._calibration_target_frames:
                # Use median of accumulated samples as baseline (robust to outliers)
                yaw_samples = [s[0] for s in self._calibration_samples]
                pitch_samples = [s[1] for s in self._calibration_samples]
                self.baseline_yaw = float(np.median(yaw_samples))
                self.baseline_pitch = float(np.median(pitch_samples))
                if self._calibration_dist_samples:
                    self.baseline_dist_mm = float(np.median(self._calibration_dist_samples))
                self.is_calibrated = True
                self._calibration_active = False
                logger.info(
                    f"Locked 3D Baseline (median of {len(self._calibration_samples)} frames) — "
                    f"Yaw: {self.baseline_yaw:.1f}°, Pitch: {self.baseline_pitch:.1f}°, "
                    f"Dist: {self.baseline_dist_mm/10.0:.1f}cm (Thresholds: Yaw ±{self.current_yaw_threshold}°, Pitch ±{self.current_pitch_threshold}°)"
                )

        # Directional Classification based on deviations from baseline
        direction = "CENTER"
        is_looking_away = False
        yaw_diff = 0.0
        pitch_diff = 0.0
        
        if self.is_calibrated:
            yaw_diff = yaw - self.baseline_yaw
            pitch_diff = pitch - self.baseline_pitch

            # Use ABSOLUTE magnitude against dynamic distance-adaptive thresholds
            yaw_exceeds = abs(yaw_diff) > self.current_yaw_threshold
            pitch_exceeds = abs(pitch_diff) > self.current_pitch_threshold

            # Direction labeling uses the sign of the diff
            directions = []
            if pitch_exceeds:
                if pitch_diff > 0:
                    directions.append("UP")
                else:
                    directions.append("DOWN")

            if yaw_exceeds:
                if yaw_diff > 0:
                    directions.append("RIGHT")
                else:
                    directions.append("LEFT")

            if directions:
                direction = "-".join(directions)
                is_looking_away = True

            # Periodic debug logging (every 2 seconds when calibrated)
            now = time.time()
            if now - self._last_debug_log_time > 2.0:
                self._last_debug_log_time = now
                logger.debug(
                    f"HeadPose | Yaw: {yaw:.1f}° (diff: {yaw_diff:+.1f}°, thr: ±{self.current_yaw_threshold}°) | "
                    f"Pitch: {pitch:.1f}° (diff: {pitch_diff:+.1f}°, thr: ±{self.current_pitch_threshold}°) | "
                    f"Dist: {dist_cm}cm | Dir: {direction} | Away: {is_looking_away}"
                )

        state = config.STATE_LOOKING_AWAY if is_looking_away else config.STATE_NORMAL
        if self.is_calibrated:
            msg = f"Direction: {direction} (Diff: [Y:{yaw_diff:+.1f}°, P:{pitch_diff:+.1f}°], Thr: [±{self.current_yaw_threshold:.0f}°, ±{self.current_pitch_threshold:.0f}°], Dist: {dist_cm:.0f}cm)"
        else:
            msg = f"Direction: {direction} (Yaw: {yaw:.1f}°, Pitch: {pitch:.1f}°)"

        # Project true 3D nose ray using solvePnP rotation
        nose_end = None
        if nose_pt is not None and self._last_rvec is not None and self._last_camera_matrix is not None:
            try:
                # Project the 3D forward-pointing vector through the estimated rotation
                nose_end_2D, _ = cv2.projectPoints(
                    self.nose_end_point_3D,
                    self._last_rvec,
                    self._last_tvec,
                    self._last_camera_matrix,
                    self.dist_coeffs
                )
                p2 = (int(nose_end_2D[0][0][0]), int(nose_end_2D[0][0][1]))
                nose_end = p2
            except Exception:
                # Fallback: no ray drawn
                nose_end = nose_pt

        return DetectorResult(
            detector_name=self.detector_name,
            state=state,
            face_detected=True,
            num_faces=1,
            similarity_score=0.0,
            verified=not is_looking_away,
            bounding_box=None,
            landmarks=target_landmarks,
            message=msg,
            raw_data={
                "yaw": yaw,
                "pitch": pitch,
                "roll": roll,
                "raw_yaw": self.last_yaw,
                "raw_pitch": self.last_pitch,
                "direction": direction,
                "looking_away": is_looking_away,
                "nose_start": nose_pt,
                "nose_endpoint": nose_end,
                "baseline_yaw": self.baseline_yaw,
                "baseline_pitch": self.baseline_pitch,
                "calibrated": self.is_calibrated,
                "yaw_diff": yaw_diff,
                "pitch_diff": pitch_diff,
                "yaw_threshold": self.current_yaw_threshold,
                "pitch_threshold": self.current_pitch_threshold,
                "dist_cm": dist_cm
            }
        )
