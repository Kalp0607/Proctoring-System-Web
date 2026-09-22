import logging
from typing import List, Tuple, Dict, Any, Optional
import numpy as np

from detectors.object_detection.schema import Detection
from detectors.object_detection.person_detector import compute_iou

logger = logging.getLogger(__name__)


class StaticBackgroundSuppressor:
    """
    Suppresses persistent stationary background objects (e.g. wall switchboards, power strips)
    that falsely trigger phone thresholds repeatedly without student movement.
    """

    def __init__(self, max_consecutive: int = 6, iou_threshold: float = 0.40):
        self.max_consecutive = max_consecutive
        self.iou_threshold = iou_threshold
        self.static_clusters: List[Dict[str, Any]] = []

    def update_and_filter(self, candidates: List[Detection]) -> List[Detection]:
        """Filters out detections that match persistent static background objects."""
        filtered = []
        for cand in candidates:
            matched = False
            for cluster in self.static_clusters:
                iou = compute_iou(cand.bbox, cluster["bbox"])
                if iou >= self.iou_threshold:
                    cluster["count"] += 1
                    cluster["last_seen"] = cand.timestamp
                    matched = True
                    if cluster["count"] >= self.max_consecutive:
                        # Suppress static object
                        cand.metadata["static_suppressed"] = True
                    break

            if not matched:
                self.static_clusters.append({
                    "bbox": cand.bbox,
                    "count": 1,
                    "last_seen": cand.timestamp
                })

            if not cand.metadata.get("static_suppressed", False):
                filtered.append(cand)

        # Decay inactive clusters
        now = candidates[0].timestamp if candidates else 0.0
        self.static_clusters = [c for c in self.static_clusters if (now - c["last_seen"]) < 5.0]

        return filtered


class DetectionFusion:
    """
    Fuses candidate detections from Full-Frame, Person-ROI, and SAHI passes.
    Applies IoU deduplication, multi-pass confidence boosting, and static background suppression.
    """

    def __init__(self, iou_threshold: float = 0.35, enable_static_suppression: bool = True):
        self.iou_threshold = iou_threshold
        self.suppressor = StaticBackgroundSuppressor() if enable_static_suppression else None

    def fuse_phone_candidates(self, candidates: List[Detection]) -> List[Detection]:
        """
        Merges overlapping phone candidates across passes.
        """
        if not candidates:
            return []

        # Sort candidates descending by confidence
        sorted_cands = sorted(candidates, key=lambda c: c.confidence, reverse=True)
        fused: List[Detection] = []

        for cand in sorted_cands:
            merged = False
            for existing in fused:
                iou = compute_iou(cand.bbox, existing.bbox)
                if iou >= self.iou_threshold:
                    # Duplicate detected across passes:
                    # If both Full-Frame and High-Res ROI saw it, boost confidence slightly (+0.05)
                    if cand.source != existing.source:
                        existing.confidence = min(0.99, max(existing.confidence, cand.confidence) + 0.05)
                        existing.metadata["cross_pass_confirmed"] = True
                    merged = True
                    break

            if not merged:
                fused.append(cand)

        if self.suppressor is not None:
            fused = self.suppressor.update_and_filter(fused)

        return fused
