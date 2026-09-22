import logging
from typing import List, Tuple, Dict, Any, Optional
import numpy as np

from detectors.object_detection.schema import Detection
from detectors.object_detection.person_detector import compute_iou

logger = logging.getLogger(__name__)


class ObjectPersonAssociator:
    """
    Associates detected objects (phones, books) with specific detected students.
    Supports multi-person exam environments.
    """

    @staticmethod
    def associate(objects: List[Detection], person_rois: List[Dict[str, Any]]) -> List[Detection]:
        """
        Maps each object detection to the nearest/enclosing person ROI.
        """
        if not objects or not person_rois:
            return objects

        for obj in objects:
            if obj.person_id is not None:
                continue

            cx, cy = obj.center
            best_person_id = None
            best_overlap = 0.0

            for roi_info in person_rois:
                rx, ry, rw, rh = roi_info["roi_rect"]
                pid = roi_info["person_id"]

                # Check center point containment
                if rx <= cx <= rx + rw and ry <= cy <= ry + rh:
                    best_person_id = pid
                    break

                # Otherwise check IoU overlap
                iou = compute_iou(obj.bbox, (rx, ry, rw, rh))
                if iou > best_overlap:
                    best_overlap = iou
                    best_person_id = pid

            if best_person_id is not None:
                obj.person_id = best_person_id

        return objects
