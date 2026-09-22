import logging
from typing import List, Tuple, Optional, Dict, Any
import numpy as np
import cv2

from detectors.object_detection.config import ROIConfig
from detectors.object_detection.schema import Detection

logger = logging.getLogger(__name__)




class ROIManager:
    """
    Manages Region of Interest (ROI) generation for detected students and coordinate conversions.
    """

    def __init__(self, config: ROIConfig):
        self.config = config

    def generate_person_rois(self, frame: np.ndarray, person_detections: List[Detection]) -> List[Dict[str, Any]]:
        """
        Generates expanded ROI bounding rectangles and image crops for all detected people.
        
        Returns:
            List of dicts:
            {
                "person_id": int,
                "roi_rect": (roi_x, roi_y, roi_w, roi_h),
                "crop": np.ndarray (BGR crop from frame),
                "person_bbox": (px, py, pw, ph)
            }
        """
        if frame is None or frame.size == 0:
            return []

        fh, fw = frame.shape[:2]
        rois = []

        if not person_detections:
            # Fallback when person detector misses: central 80% region
            fallback_w = int(fw * 0.85)
            fallback_h = int(fh * 0.85)
            fallback_x = max(0, (fw - fallback_w) // 2)
            fallback_y = max(0, (fh - fallback_h) // 2)
            fallback_rect = (fallback_x, fallback_y, fallback_w, fallback_h)
            crop = frame[fallback_y:fallback_y + fallback_h, fallback_x:fallback_x + fallback_w].copy()
            
            rois.append({
                "person_id": None,
                "roi_rect": fallback_rect,
                "crop": crop,
                "person_bbox": fallback_rect
            })
            return rois

        for p in person_detections:
            px, py, pw, ph = p.bbox

            pad_w = int(pw * self.config.padding_x)
            pad_h = int(ph * self.config.padding_y)

            # Expanded bounds
            x1 = max(0, px - pad_w)
            y1 = max(0, py - pad_h)
            x2 = min(fw, px + pw + pad_w)
            y2 = min(fh, py + ph + pad_h)

            roi_w = x2 - x1
            roi_h = y2 - y1

            if roi_w < self.config.min_width or roi_h < self.config.min_height:
                continue

            crop = frame[y1:y2, x1:x2].copy()
            if crop.size == 0:
                continue

            rois.append({
                "person_id": p.person_id,
                "roi_rect": (x1, y1, roi_w, roi_h),
                "crop": crop,
                "person_bbox": p.bbox
            })

        return rois

    @staticmethod
    def local_to_global_bbox(local_bbox: Tuple[int, int, int, int],
                             roi_rect: Tuple[int, int, int, int],
                             model_input_size: Optional[Tuple[int, int]] = None) -> Tuple[int, int, int, int]:
        """
        Converts local bounding box coordinates from cropped/resized ROI to global full-frame coordinates.
        
        Args:
            local_bbox: (lx, ly, lw, lh) in ROI space (or model input space).
            roi_rect: (rx, ry, rw, rh) in global frame space.
            model_input_size: (input_w, input_h) if crop was resized before model inference.
        """
        lx, ly, lw, lh = local_bbox
        rx, ry, rw, rh = roi_rect

        if model_input_size is not None and model_input_size[0] > 0 and model_input_size[1] > 0:
            scale_x = rw / float(model_input_size[0])
            scale_y = rh / float(model_input_size[1])
        else:
            scale_x = 1.0
            scale_y = 1.0

        gx = int(rx + lx * scale_x)
        gy = int(ry + ly * scale_y)
        gw = int(lw * scale_x)
        gh = int(lh * scale_y)

        return (gx, gy, gw, gh)
