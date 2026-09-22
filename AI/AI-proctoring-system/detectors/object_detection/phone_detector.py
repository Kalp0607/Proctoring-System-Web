import logging
import time
from typing import List, Tuple, Dict, Any, Optional
import numpy as np

from detectors.object_detection.models import ModelManager, SENTINEL_CLASS_PHONE, YOLO11_CLASS_PHONE
from detectors.object_detection.schema import Detection, TelemetryData
from detectors.object_detection.config import PhoneConfig, SAHIConfig
from detectors.object_detection.roi import ROIManager

logger = logging.getLogger(__name__)


class PhoneDetector:
    """
    Dedicated Phone Detector using SentinelVision model.
    Executes multi-pass inference: Full-Frame, High-Resolution Person-ROI, and Adaptive SAHI Slicing.
    """

    def __init__(self, model_manager: ModelManager, phone_config: PhoneConfig, sahi_config: SAHIConfig):
        self.model_manager = model_manager
        self.config = phone_config
        self.sahi_config = sahi_config

    def _validate_geometry(self, bbox: Tuple[int, int, int, int], frame_shape: Tuple[int, int]) -> bool:
        """Validates physical smartphone size and aspect ratio bounds."""
        fh, fw = frame_shape
        x, y, w, h = bbox

        if w <= 0 or h <= 0:
            return False

        area = w * h
        frame_area = fw * fh

        if area < self.config.min_pixel_area:
            return False

        if (area / float(frame_area)) > self.config.max_area_ratio:
            return False

        if (w / float(fw)) > self.config.max_width_ratio:
            return False

        if (h / float(fh)) > self.config.max_height_ratio:
            return False

        aspect = max(w, h) / float(min(w, h))
        if aspect < self.config.min_aspect_ratio or aspect > self.config.max_aspect_ratio:
            return False

        return True

    def detect_full_frame_yolo11(self, frame: np.ndarray, frame_id: int = 0) -> List[Detection]:
        """Pass 0: Full-Frame YOLO11 Phone Inference (COCO cls=67 cell phone).
        YOLO11 achieves 0.7-0.93 confidence on visible phones vs Sentinel's typical <0.15.
        Results are merged into the main candidate pool with source='yolo11_phone'."""
        if frame is None or frame.size == 0:
            return []

        raw_dets = self.model_manager.run_yolo11_phone(
            image=frame,
            conf=self.config.candidate_confidence,
            imgsz=self.config.full_frame_imgsz
        )

        detections: List[Detection] = []
        fh, fw = frame.shape[:2]

        for det in raw_dets:
            bbox = det["bbox"]
            conf = det["confidence"]
            if not self._validate_geometry(bbox, (fh, fw)):
                continue

            detections.append(Detection(
                type="phone",
                bbox=bbox,
                confidence=conf,
                source="yolo11_phone",
                frame_id=frame_id,
                metadata={"raw_conf": conf}
            ))

        return detections

    def detect_full_frame(self, frame: np.ndarray, frame_id: int = 0) -> List[Detection]:
        """Pass 1: Full-Frame Sentinel Inference."""
        if frame is None or frame.size == 0:
            return []

        raw_dets = self.model_manager.run_sentinel_phone(
            image=frame,
            conf=self.config.candidate_confidence,
            imgsz=self.config.full_frame_imgsz
        )

        detections: List[Detection] = []
        fh, fw = frame.shape[:2]

        for det in raw_dets:
            bbox = det["bbox"]
            conf = det["confidence"]
            if not self._validate_geometry(bbox, (fh, fw)):
                continue

            detections.append(Detection(
                type="phone",
                bbox=bbox,
                confidence=conf,
                source="sentinel_full",
                frame_id=frame_id,
                metadata={"raw_conf": conf}
            ))

        return detections

    def detect_person_rois(self, frame: np.ndarray, rois: List[Dict[str, Any]], frame_id: int = 0) -> List[Detection]:
        """Pass 2: High-Resolution Sentinel Inference inside Person ROIs."""
        if frame is None or frame.size == 0 or not rois:
            return []

        detections: List[Detection] = []
        fh, fw = frame.shape[:2]

        for roi_info in rois:
            crop = roi_info["crop"]
            roi_rect = roi_info["roi_rect"]
            person_id = roi_info["person_id"]

            if crop is None or crop.size == 0:
                continue

            raw_dets = self.model_manager.run_sentinel_phone(
                image=crop,
                conf=self.config.candidate_confidence,
                imgsz=self.config.roi_imgsz
            )

            for det in raw_dets:
                local_bbox = det["bbox"]
                conf = det["confidence"]

                # Convert from local crop coordinates to global frame coordinates
                global_bbox = ROIManager.local_to_global_bbox(local_bbox, roi_rect)

                if not self._validate_geometry(global_bbox, (fh, fw)):
                    continue

                detections.append(Detection(
                    type="phone",
                    bbox=global_bbox,
                    confidence=conf,
                    source="sentinel_roi",
                    frame_id=frame_id,
                    person_id=person_id,
                    metadata={"raw_conf": conf, "roi_rect": roi_rect}
                ))

        return detections

    def detect_full_frame_sahi(self, frame: np.ndarray, frame_id: int = 0) -> List[Detection]:
        """
        Pass 3b: Full-frame SAHI fallback.
        Slices the entire frame into overlapping tiles and runs Sentinel inference on each.
        Catches phones at frame edges that fall outside any person ROI boundary.
        Only called every 6th frame (controlled by pipeline) due to CPU cost.
        """
        if not self.sahi_config.enabled or frame is None or frame.size == 0:
            return []

        detections: List[Detection] = []
        fh, fw = frame.shape[:2]
        slice_sz = self.sahi_config.slice_size
        overlap = self.sahi_config.overlap
        step = int(slice_sz * (1.0 - overlap))

        y_starts = list(range(0, max(1, fh - slice_sz + step), step))
        if not y_starts or y_starts[-1] + slice_sz < fh:
            y_starts.append(max(0, fh - slice_sz))

        x_starts = list(range(0, max(1, fw - slice_sz + step), step))
        if not x_starts or x_starts[-1] + slice_sz < fw:
            x_starts.append(max(0, fw - slice_sz))

        for sy in y_starts:
            for sx in x_starts:
                ex = min(fw, sx + slice_sz)
                ey = min(fh, sy + slice_sz)
                actual_w = ex - sx
                actual_h = ey - sy

                if actual_w < 100 or actual_h < 100:
                    continue

                slice_crop = frame[sy:ey, sx:ex]
                raw_dets = self.model_manager.run_sentinel_phone(
                    image=slice_crop,
                    conf=self.sahi_config.trigger_min_conf,
                    imgsz=slice_sz
                )

                for det in raw_dets:
                    local_bbox = det["bbox"]
                    conf = det["confidence"]
                    global_bbox = (sx + local_bbox[0], sy + local_bbox[1], local_bbox[2], local_bbox[3])

                    if not self._validate_geometry(global_bbox, (fh, fw)):
                        continue

                    detections.append(Detection(
                        type="phone",
                        bbox=global_bbox,
                        confidence=conf,
                        source="sentinel_sahi_fullframe",
                        frame_id=frame_id,
                        metadata={"raw_conf": conf, "slice_rect": (sx, sy, actual_w, actual_h)}
                    ))

        return detections

    def detect_sahi_slices(self, frame: np.ndarray, rois: List[Dict[str, Any]], frame_id: int = 0) -> List[Detection]:
        """Pass 3: Adaptive Sliced Slicing Fallback on difficult/marginal candidate areas."""
        if not self.sahi_config.enabled or frame is None or frame.size == 0 or not rois:
            return []

        detections: List[Detection] = []
        fh, fw = frame.shape[:2]
        slice_sz = self.sahi_config.slice_size
        overlap = self.sahi_config.overlap
        step = int(slice_sz * (1.0 - overlap))

        for roi_info in rois:
            roi_rect = roi_info["roi_rect"]
            person_id = roi_info["person_id"]
            rx, ry, rw, rh = roi_rect

            # If ROI is smaller than slice_sz, no need to slice
            if rw <= slice_sz and rh <= slice_sz:
                continue

            # Generate overlapping grid slices inside the ROI
            y_starts = list(range(ry, ry + rh - slice_sz + step, step))
            if not y_starts or y_starts[-1] + slice_sz < ry + rh:
                y_starts.append(max(0, ry + rh - slice_sz))

            x_starts = list(range(rx, rx + rw - slice_sz + step, step))
            if not x_starts or x_starts[-1] + slice_sz < rx + rw:
                x_starts.append(max(0, rx + rw - slice_sz))

            for sy in y_starts:
                for sx in x_starts:
                    ex = min(fw, sx + slice_sz)
                    ey = min(fh, sy + slice_sz)
                    actual_w = ex - sx
                    actual_h = ey - sy

                    if actual_w < 100 or actual_h < 100:
                        continue

                    slice_crop = frame[sy:ey, sx:ex]
                    raw_dets = self.model_manager.run_sentinel_phone(
                        image=slice_crop,
                        conf=self.sahi_config.trigger_min_conf,
                        imgsz=slice_sz
                    )

                    for det in raw_dets:
                        local_bbox = det["bbox"]
                        conf = det["confidence"]
                        global_bbox = (sx + local_bbox[0], sy + local_bbox[1], local_bbox[2], local_bbox[3])

                        if not self._validate_geometry(global_bbox, (fh, fw)):
                            continue

                        detections.append(Detection(
                            type="phone",
                            bbox=global_bbox,
                            confidence=conf,
                            source="sentinel_sahi",
                            frame_id=frame_id,
                            person_id=person_id,
                            metadata={"raw_conf": conf, "slice_rect": (sx, sy, actual_w, actual_h)}
                        ))

        return detections
