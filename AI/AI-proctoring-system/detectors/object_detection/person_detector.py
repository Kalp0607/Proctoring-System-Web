import logging
from typing import List, Tuple, Dict, Any, Optional
import numpy as np

from detectors.object_detection.models import ModelManager, YOLO11_CLASS_PERSON
from detectors.object_detection.schema import Detection
from detectors.object_detection.config import PersonConfig

logger = logging.getLogger(__name__)


def compute_iou(box1: Tuple[int, int, int, int], box2: Tuple[int, int, int, int]) -> float:
    """Computes Intersection over Union (IoU) for (x, y, w, h) boxes."""
    x1, y1, w1, h1 = box1
    x2, y2, w2, h2 = box2

    xi1 = max(x1, x2)
    yi1 = max(y1, y2)
    xi2 = min(x1 + w1, x2 + w2)
    yi2 = min(y1 + h1, y2 + h2)

    inter_w = max(0, xi2 - xi1)
    inter_h = max(0, yi2 - yi1)
    inter_area = inter_w * inter_h

    box1_area = w1 * h1
    box2_area = w2 * h2
    union_area = box1_area + box2_area - inter_area

    if union_area <= 0:
        return 0.0
    return inter_area / union_area


def compute_containment(inner_box: Tuple[int, int, int, int], outer_box: Tuple[int, int, int, int]) -> float:
    """Computes what fraction of inner_box is contained within outer_box."""
    x1, y1, w1, h1 = inner_box
    x2, y2, w2, h2 = outer_box

    xi1 = max(x1, x2)
    yi1 = max(y1, y2)
    xi2 = min(x1 + w1, x2 + w2)
    yi2 = min(y1 + h1, y2 + h2)

    inter_w = max(0, xi2 - xi1)
    inter_h = max(0, yi2 - yi1)
    inter_area = inter_w * inter_h

    inner_area = w1 * h1
    if inner_area <= 0:
        return 0.0
    return inter_area / float(inner_area)


class PersonDetector:
    """
    Dedicated Person Detector using base YOLO11.
    Extracts, filters, and deduplicates all student person bounding boxes.
    """

    def __init__(self, model_manager: ModelManager, config: PersonConfig):
        self.model_manager = model_manager
        self.config = config

    def detect(self, frame: np.ndarray, frame_id: int = 0) -> List[Detection]:
        """
        Runs person detection on frame and returns deduplicated normalized Detection list.
        """
        if frame is None or frame.size == 0:
            return []

        fh, fw = frame.shape[:2]
        frame_area = float(fw * fh)

        raw_dets = self.model_manager.run_yolo11(
            image=frame,
            classes=[YOLO11_CLASS_PERSON],
            conf=self.config.confidence,
            imgsz=self.config.imgsz
        )

        candidates: List[Dict[str, Any]] = []
        for det in raw_dets:
            conf = det["confidence"]
            bbox = det["bbox"]
            w, h = bbox[2], bbox[3]
            box_area = w * h

            # Filter tiny spurious boxes (< min_area_ratio of frame)
            if (box_area / frame_area) < self.config.min_area_ratio:
                continue

            candidates.append({
                "confidence": conf,
                "bbox": bbox,
                "area": box_area
            })

        # Sort candidates by area (largest body bounding box first)
        candidates.sort(key=lambda x: x["area"], reverse=True)

        # Deduplicate overlapping / nested person boxes
        kept_candidates: List[Dict[str, Any]] = []
        for cand in candidates:
            cand_bbox = cand["bbox"]
            is_duplicate = False

            for kept in kept_candidates:
                kept_bbox = kept["bbox"]
                # 1. IoU check
                iou = compute_iou(cand_bbox, kept_bbox)
                if iou >= self.config.iou_nms_threshold:
                    is_duplicate = True
                    break

                # 2. Containment check (sub-body parts inside full-body)
                containment = compute_containment(cand_bbox, kept_bbox)
                if containment >= self.config.max_containment_ratio:
                    is_duplicate = True
                    break

            if not is_duplicate:
                kept_candidates.append(cand)

        # Build normalized Detection objects with assigned person IDs
        person_detections: List[Detection] = []
        for idx, cand in enumerate(kept_candidates, start=1):
            det_obj = Detection(
                type="person",
                bbox=cand["bbox"],
                confidence=cand["confidence"],
                source="yolo11",
                frame_id=frame_id,
                person_id=idx,
                metadata={"area_ratio": round(cand["area"] / frame_area, 3)}
            )
            person_detections.append(det_obj)

        return person_detections
