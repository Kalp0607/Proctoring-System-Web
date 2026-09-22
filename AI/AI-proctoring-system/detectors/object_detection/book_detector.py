import logging
from typing import List, Tuple, Dict, Any, Optional
import numpy as np

from detectors.object_detection.models import ModelManager, YOLO11_CLASS_BOOK
from detectors.object_detection.schema import Detection
from detectors.object_detection.config import BookConfig

logger = logging.getLogger(__name__)


class BookDetector:
    """
    Dedicated Book Detector using YOLO11 model (Class ID 73).
    Differentiates books from phones and student notes.
    """

    def __init__(self, model_manager: ModelManager, config: BookConfig):
        self.model_manager = model_manager
        self.config = config

    def detect(self, frame: np.ndarray, frame_id: int = 0) -> List[Detection]:
        """Runs book detection on full frame."""
        if frame is None or frame.size == 0:
            return []

        raw_dets = self.model_manager.run_yolo11(
            image=frame,
            classes=[YOLO11_CLASS_BOOK],
            conf=self.config.confidence,
            imgsz=self.config.imgsz
        )

        detections: List[Detection] = []
        for det in raw_dets:
            detections.append(Detection(
                type="book",
                bbox=det["bbox"],
                confidence=det["confidence"],
                source="yolo11",
                frame_id=frame_id,
                metadata={"raw_conf": det["confidence"]}
            ))

        return detections
