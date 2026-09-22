import logging
import math
from typing import List, Tuple, Dict, Any, Optional
import numpy as np

from detectors.object_detection.config import HandContextConfig
from detectors.object_detection.schema import Detection

logger = logging.getLogger(__name__)


class HandContextFusion:
    """
    Integrates MediaPipe hand tracking to calculate spatial proximity between candidate phones and student hands.
    Provides supporting evidence without making phone detection dependent on hand visibility.
    """

    def __init__(self, config: HandContextConfig):
        self.config = config
        self.mp_hands = None
        self._init_mediapipe()

    def _init_mediapipe(self):
        if not self.config.enabled:
            return
        try:
            import mediapipe as mp
            self.mp_hands = mp.solutions.hands.Hands(
                static_image_mode=False,
                max_num_hands=2,
                min_detection_confidence=self.config.detection_confidence,
                min_tracking_confidence=0.50
            )
        except Exception as e:
            logger.warning(f"MediaPipe Hands initialization failed (hand context disabled): {e}")
            self.mp_hands = None

    def detect_hand_centers(self, frame: np.ndarray) -> List[Tuple[float, float]]:
        """Extracts (x, y) center positions for detected hands in pixel coordinates."""
        if self.mp_hands is None or frame is None or frame.size == 0:
            return []

        fh, fw = frame.shape[:2]
        centers = []
        try:
            import cv2
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.mp_hands.process(rgb)
            if results and results.multi_hand_landmarks:
                for hand_landmarks in results.multi_hand_landmarks:
                    xs = [lm.x * fw for lm in hand_landmarks.landmark]
                    ys = [lm.y * fh for lm in hand_landmarks.landmark]
                    cx = float(np.mean(xs))
                    cy = float(np.mean(ys))
                    centers.append((cx, cy))
        except Exception as e:
            logger.debug(f"Hand detection error: {e}")

        return centers

    def fuse_hand_context(self, phone_detections: List[Detection], hand_centers: List[Tuple[float, float]]) -> List[Detection]:
        """
        Calculates hand proximity and applies soft confidence boost if phone is held in or near hand.
        """
        if not phone_detections or not hand_centers:
            return phone_detections

        radius = float(self.config.proximity_radius)
        boost = self.config.proximity_boost

        for phone in phone_detections:
            px, py = phone.center
            min_dist = float("inf")

            for hx, hy in hand_centers:
                dist = math.hypot(px - hx, py - hy)
                if dist < min_dist:
                    min_dist = dist

            if min_dist <= radius:
                # Proximity score (1.0 at center, 0.0 at radius)
                prox_score = max(0.0, 1.0 - (min_dist / radius))
                phone.hand_proximity = round(prox_score, 2)
                # Soft boost
                phone.confidence = min(0.99, phone.confidence + (prox_score * boost))
                phone.metadata["hand_distance_px"] = round(min_dist, 1)

        return phone_detections
