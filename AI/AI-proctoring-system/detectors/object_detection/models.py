import logging
import os
from pathlib import Path
from typing import Optional, Dict, Any, List
import numpy as np
from ultralytics import YOLO

logger = logging.getLogger(__name__)

# Class ID mappings confirmed from actual models
YOLO11_CLASS_PERSON = 0
YOLO11_CLASS_BOOK = 73
YOLO11_CLASS_PHONE = 67   # COCO class: 'cell phone' (detected by YOLO11 base model)
SENTINEL_CLASS_PHONE = 1
SENTINEL_CLASS_BOOK = 0
SENTINEL_CLASS_PERSON = 4


class ModelManager:
    """
    Singleton Model Lifecycle Manager.
    Loads and caches YOLO11 and SentinelVision models once at application startup.
    """
    _instance: Optional["ModelManager"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ModelManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self,
                 person_model_path: str = "yolo11s.pt",
                 book_model_path: str = "yolo11s.pt",
                 phone_model_path: str = "models/sentinelvision_yolov8n.pt",
                 device: str = "cpu"):
        if getattr(self, "_initialized", False):
            return

        self.device = device
        self.person_model_path = Path(person_model_path)
        self.book_model_path = Path(book_model_path)
        self.phone_model_path = Path(phone_model_path)

        self.yolo11_model: Optional[YOLO] = None
        self.sentinel_model: Optional[YOLO] = None

        self._load_models()
        self._prewarm()
        self._initialized = True

    def _resolve_model_path(self, model_path: Path) -> Path:
        """Resolves model path relative to project root or absolute."""
        if model_path.is_absolute() and model_path.exists():
            return model_path
        
        # Try current working directory
        if model_path.exists():
            return model_path
            
        # Try relative to project base directory
        base_dir = Path(__file__).resolve().parent.parent.parent
        resolved = base_dir / model_path
        if resolved.exists():
            return resolved
            
        return model_path

    def _load_models(self):
        """Loads Ultralytics YOLO models with robust error handling."""
        # 1. Load YOLO11 Model (for Person and Book)
        yolo_path = self._resolve_model_path(self.person_model_path)
        logger.info(f"Loading YOLO11 Base Model from: {yolo_path}")
        try:
            self.yolo11_model = YOLO(str(yolo_path))
            logger.info("YOLO11 Base Model successfully loaded.")
        except Exception as e:
            logger.error(f"Failed to load YOLO11 model from {yolo_path}: {e}")
            raise RuntimeError(f"YOLO11 model initialization failed: {e}")

        # 2. Load Sentinel Phone Model
        sentinel_path = self._resolve_model_path(self.phone_model_path)
        logger.info(f"Loading Sentinel Phone Model from: {sentinel_path}")
        try:
            self.sentinel_model = YOLO(str(sentinel_path))
            logger.info("Sentinel Phone Model successfully loaded.")
        except Exception as e:
            logger.error(f"Failed to load Sentinel phone model from {sentinel_path}: {e}")
            raise RuntimeError(f"Sentinel phone model initialization failed: {e}")

    def _prewarm(self):
        """Pre-warms models with dummy input to eliminate first-frame latency spikes."""
        logger.info("Pre-warming object detection models...")
        dummy_frame = np.zeros((640, 640, 3), dtype=np.uint8)
        try:
            if self.yolo11_model is not None:
                self.yolo11_model.predict(
                    source=dummy_frame,
                    classes=[YOLO11_CLASS_PERSON, YOLO11_CLASS_BOOK],
                    conf=0.50,
                    imgsz=640,
                    device=self.device,
                    verbose=False
                )
            if self.sentinel_model is not None:
                self.sentinel_model.predict(
                    source=dummy_frame,
                    classes=[SENTINEL_CLASS_PHONE],
                    conf=0.30,
                    imgsz=640,
                    device=self.device,
                    verbose=False
                )
            logger.info("Model pre-warming complete.")
        except Exception as e:
            logger.warning(f"Model pre-warm warning (non-fatal): {e}")

    def run_yolo11(self, image: np.ndarray, classes: List[int], conf: float, imgsz: int) -> List[Dict[str, Any]]:
        """Executes YOLO11 inference for given classes."""
        if self.yolo11_model is None or image is None or image.size == 0:
            return []

        results = self.yolo11_model.predict(
            source=image,
            classes=classes,
            conf=conf,
            imgsz=imgsz,
            device=self.device,
            verbose=False
        )

        detections = []
        if len(results) > 0 and results[0].boxes is not None:
            for box in results[0].boxes:
                cls_id = int(box.cls[0].cpu().numpy())
                c = float(box.conf[0].cpu().numpy())
                xyxy = box.xyxy[0].cpu().numpy().astype(int)
                x1, y1, x2, y2 = xyxy
                w, h = int(x2 - x1), int(y2 - y1)
                detections.append({
                    "class_id": cls_id,
                    "confidence": float(c),
                    "bbox": (int(x1), int(y1), w, h),
                    "xyxy": (int(x1), int(y1), int(x2), int(y2))
                })
        return detections

    def run_yolo11_phone(self, image: np.ndarray, conf: float, imgsz: int) -> List[Dict[str, Any]]:
        """Detects cell phones using YOLO11 base model (COCO cls=67).
        Provides a high-confidence supplementary phone detection pass since
        YOLO11 achieves 0.7-0.93 on visible phones while Sentinel may return <0.10."""
        return self.run_yolo11(
            image=image,
            classes=[YOLO11_CLASS_PHONE],
            conf=conf,
            imgsz=imgsz
        )

    def run_sentinel_phone(self, image: np.ndarray, conf: float, imgsz: int) -> List[Dict[str, Any]]:
        """Executes Sentinel phone detection on full image or cropped ROI."""
        if self.sentinel_model is None or image is None or image.size == 0:
            return []

        results = self.sentinel_model.predict(
            source=image,
            classes=[SENTINEL_CLASS_PHONE],
            conf=conf,
            imgsz=imgsz,
            device=self.device,
            verbose=False
        )

        detections = []
        if len(results) > 0 and results[0].boxes is not None:
            for box in results[0].boxes:
                cls_id = int(box.cls[0].cpu().numpy())
                c = float(box.conf[0].cpu().numpy())
                xyxy = box.xyxy[0].cpu().numpy().astype(int)
                x1, y1, x2, y2 = xyxy
                w, h = int(x2 - x1), int(y2 - y1)
                detections.append({
                    "class_id": cls_id,
                    "confidence": float(c),
                    "bbox": (int(x1), int(y1), w, h),
                    "xyxy": (int(x1), int(y1), int(x2), int(y2))
                })
        return detections
