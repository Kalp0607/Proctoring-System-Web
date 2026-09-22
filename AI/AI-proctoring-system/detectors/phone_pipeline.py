"""
Multi-Stage Real-Time Phone Detection Pipeline
=============================================
Inference-time engineered detection pipeline for AI exam proctoring:
1. Full-Frame Detection (YOLOv11s + SentinelVision)
2. High-Resolution Person-ROI Inspection with Coordinate Transformation
3. Adaptive SAHI Slicing Fallback for Marginal / Small / Angled Phones
4. MediaPipe Hand Proximity & Context Validation
5. Lightweight Multi-Frame Tracking & Spatial Consistency
6. Dual-Threshold Temporal Aggregation & State Machine (NO_PHONE -> SUSPECTED -> CONFIRMED -> COOLDOWN)
7. Static Background Elimination & Physical Geometry Bounds
"""

import cv2
import time
import logging
import numpy as np
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass, field
from collections import deque

import config

logger = logging.getLogger(__name__)

# COCO Class IDs
COCO_CLASS_PERSON = 0
COCO_CLASS_REMOTE = 65
COCO_CLASS_CELL_PHONE = 67


def compute_iou_xywh(box1: Tuple[int, int, int, int], box2: Tuple[int, int, int, int]) -> float:
    """Computes Intersection over Union (IoU) between two bounding boxes (x, y, w, h)."""
    x1, y1, w1, h1 = box1
    x2, y2, w2, h2 = box2

    inter_x1 = max(x1, x2)
    inter_y1 = max(y1, y2)
    inter_x2 = min(x1 + w1, x2 + w2)
    inter_y2 = min(y1 + h1, y2 + h2)

    inter_w = max(0, inter_x2 - inter_x1)
    inter_h = max(0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    area1 = w1 * h1
    area2 = w2 * h2
    union_area = area1 + area2 - inter_area

    if union_area <= 0:
        return 0.0
    return float(inter_area / union_area)


def compute_containment_ratio(box1: Tuple[int, int, int, int], box2: Tuple[int, int, int, int]) -> float:
    """Computes containment ratio of smaller box inside larger box."""
    x1, y1, w1, h1 = box1
    x2, y2, w2, h2 = box2

    inter_x1 = max(x1, x2)
    inter_y1 = max(y1, y2)
    inter_x2 = min(x1 + w1, x2 + w2)
    inter_y2 = min(y1 + h1, y2 + h2)

    inter_w = max(0, inter_x2 - inter_x1)
    inter_h = max(0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    area1 = w1 * h1
    area2 = w2 * h2
    min_area = min(area1, area2)

    if min_area <= 0:
        return 0.0
    return float(inter_area / min_area)


@dataclass
class PhoneCandidate:
    """Standardized representation of a single detected phone candidate."""
    bbox: Tuple[int, int, int, int]           # (x, y, w, h) in original full-frame coordinates
    confidence: float
    source: str                               # "FULL_FRAME", "PERSON_ROI", "SAHI"
    class_id: int = COCO_CLASS_CELL_PHONE
    hand_proximity: float = 0.0               # 0.0 (far) to 1.0 (in hand)
    adjusted_confidence: float = 0.0

    def __post_init__(self):
        if self.adjusted_confidence == 0.0:
            self.adjusted_confidence = self.confidence


class PhoneTrack:
    """Represents a continuous multi-frame object track of a physical smartphone."""

    def __init__(self, track_id: int, initial_candidate: PhoneCandidate, window_size: int = 8):
        self.track_id = track_id
        self.bbox = initial_candidate.bbox
        self.confidence = initial_candidate.adjusted_confidence
        self.source = initial_candidate.source
        self.hand_proximity = initial_candidate.hand_proximity

        # Temporal rolling history deque [1 = detected, 0 = missed]
        self.history = deque([1], maxlen=window_size)
        self.confidence_history = deque([initial_candidate.adjusted_confidence], maxlen=window_size)
        self.age_since_last_hit = 0
        self.total_frames_seen = 1

        self.state = "PHONE_SUSPECTED"         # "NO_PHONE", "PHONE_SUSPECTED", "PHONE_CONFIRMED", "PHONE_COOLDOWN"
        self.first_seen = time.time()
        self.last_seen = time.time()

    def update(self, candidate: PhoneCandidate):
        """Updates track with a newly associated frame candidate."""
        # Exponential smoothing on bounding box position for visual stability
        alpha = 0.75
        ox, oy, ow, oh = self.bbox
        nx, ny, nw, nh = candidate.bbox
        self.bbox = (
            int(alpha * nx + (1 - alpha) * ox),
            int(alpha * ny + (1 - alpha) * oy),
            int(alpha * nw + (1 - alpha) * ow),
            int(alpha * nh + (1 - alpha) * oh)
        )
        self.confidence = candidate.adjusted_confidence
        self.source = candidate.source
        self.hand_proximity = candidate.hand_proximity

        self.history.append(1)
        self.confidence_history.append(candidate.adjusted_confidence)
        self.age_since_last_hit = 0
        self.total_frames_seen += 1
        self.last_seen = time.time()

    def mark_missed(self):
        """Registers a frame where this track was not detected."""
        self.history.append(0)
        self.age_since_last_hit += 1

    @property
    def positive_count(self) -> int:
        return sum(self.history)

    @property
    def mean_confidence(self) -> float:
        if not self.confidence_history:
            return 0.0
        return float(np.mean(self.confidence_history))


class PhoneDetectionPipeline:
    """
    State-of-the-art inference-time phone detector integrating:
    - Full-Frame global inference
    - High-Resolution Person-ROI inspection
    - Adaptive SAHI sliced fallback
    - MediaPipe Hand Proximity Context
    - Multi-frame tracking & temporal aggregation
    """

    def __init__(self, yolo_model, sentinel_model=None, mp_hands=None, config_dict: Optional[Dict[str, Any]] = None):
        self.yolo_model = yolo_model
        self.sentinel_model = sentinel_model
        self.mp_hands = mp_hands

        # Resolve configuration with defaults
        cfg = getattr(config, 'PHONE_DETECTION_CONFIG', {})
        if config_dict:
            cfg = {**cfg, **config_dict}
        self.cfg = cfg

        self.full_frame_imgsz = cfg.get("full_frame_imgsz", 640)
        self.roi_imgsz = cfg.get("roi_imgsz", 640)
        self.roi_padding = cfg.get("roi_padding", 0.25)
        self.candidate_confidence = cfg.get("candidate_confidence", 0.25)
        self.violation_confidence = cfg.get("violation_confidence", 0.35)
        self.temporal_window = cfg.get("temporal_window", 8)
        self.min_positive_frames = cfg.get("min_positive_frames", 4)
        self.cooldown_seconds = cfg.get("cooldown_seconds", 3.0)

        self.tracking_enabled = cfg.get("tracking_enabled", True)
        self.track_max_age = cfg.get("track_max_age", 5)
        self.track_iou_threshold = cfg.get("track_iou_threshold", 0.30)
        self.track_center_dist_threshold = cfg.get("track_center_dist_threshold", 80.0)

        self.sahi_enabled = cfg.get("sahi_enabled", True)
        self.sahi_slice_size = cfg.get("sahi_slice_size", 384)
        self.sahi_overlap = cfg.get("sahi_overlap", 0.25)
        self.sahi_trigger_min_conf = cfg.get("sahi_trigger_min_conf", 0.20)
        self.sahi_trigger_max_conf = cfg.get("sahi_trigger_max_conf", 0.40)

        self.hand_context_enabled = cfg.get("hand_context_enabled", True)
        self.hand_proximity_radius = cfg.get("hand_proximity_radius", 150)
        self.hand_proximity_boost = cfg.get("hand_proximity_boost", 0.15)

        # Tracking state
        self._next_track_id = 1
        self._tracks: List[PhoneTrack] = []

        # Static background temporal suppression tracker
        self._static_cycle_counter = 0
        self._static_tracker: List[Dict[str, Any]] = []

        # Cooldown state
        self._last_violation_time = 0.0
        self._in_cooldown = False

        # Dynamically resolve SentinelVision phone class ID
        self.sentinel_class_id = None
        if self.sentinel_model is not None:
            for cls_id, cls_name in self.sentinel_model.names.items():
                if any(k in cls_name.lower() for k in ('phone', 'cell', 'mobile')):
                    self.sentinel_class_id = cls_id
                    break

    def validate_geometry(self, w: int, h: int, fw: int, fh: int, source: str = "") -> bool:
        """Validates that candidate bounding box has realistic physical smartphone dimensions."""
        if w <= 0 or h <= 0 or fw <= 0 or fh <= 0:
            return False

        area = w * h
        frame_area = float(fw * fh)

        max_area_ratio = self.cfg.get("max_area_ratio", 0.25)
        min_pixel_area = self.cfg.get("min_pixel_area", 300)
        if area < min_pixel_area or (area / frame_area) > max_area_ratio:
            return False

        max_w = fw * self.cfg.get("max_width_ratio", 0.60)
        max_h = fh * self.cfg.get("max_height_ratio", 0.75)
        if w > max_w or h > max_h:
            return False

        if min(w, h) < 14 or max(w, h) < 20:
            return False

        longer = max(w, h)
        shorter = min(w, h)
        aspect_ratio = longer / float(max(shorter, 1))
        min_ar = self.cfg.get("min_aspect_ratio", 1.0)
        max_ar = self.cfg.get("max_aspect_ratio", 5.0)
        if not (min_ar <= aspect_ratio <= max_ar):
            return False

        return True

    def run_full_frame(self, frame: np.ndarray) -> List[PhoneCandidate]:
        """Pass 1: Runs global full-frame phone detection across YOLO11s and SentinelVision."""
        candidates = []
        fh, fw = frame.shape[:2]

        # 1. Base YOLO11s (COCO classes 67=cell phone, 65=remote)
        try:
            res_base = self.yolo_model.predict(
                source=frame,
                classes=[COCO_CLASS_CELL_PHONE, COCO_CLASS_REMOTE],
                conf=self.candidate_confidence,
                imgsz=self.full_frame_imgsz,
                verbose=False
            )
            if len(res_base) > 0 and res_base[0].boxes is not None:
                for box in res_base[0].boxes:
                    conf = float(box.conf[0].cpu().numpy())
                    xyxy = box.xyxy[0].cpu().numpy().astype(int)
                    w, h = int(xyxy[2] - xyxy[0]), int(xyxy[3] - xyxy[1])
                    if self.validate_geometry(w, h, fw, fh, source="FULL_FRAME_YOLO11"):
                        candidates.append(PhoneCandidate(
                            bbox=(int(xyxy[0]), int(xyxy[1]), w, h),
                            confidence=round(conf, 2),
                            source="FULL_FRAME"
                        ))
        except Exception as e:
            logger.debug(f"Full-frame YOLO11s error: {e}")

        # 2. SentinelVision Model
        if self.sentinel_model is not None and self.sentinel_class_id is not None:
            try:
                res_sent = self.sentinel_model.predict(
                    source=frame,
                    classes=[self.sentinel_class_id],
                    conf=self.candidate_confidence,
                    imgsz=self.full_frame_imgsz,
                    verbose=False
                )
                if len(res_sent) > 0 and res_sent[0].boxes is not None:
                    for box in res_sent[0].boxes:
                        conf = float(box.conf[0].cpu().numpy())
                        xyxy = box.xyxy[0].cpu().numpy().astype(int)
                        w, h = int(xyxy[2] - xyxy[0]), int(xyxy[3] - xyxy[1])
                        if self.validate_geometry(w, h, fw, fh, source="FULL_FRAME_SENTINEL"):
                            candidates.append(PhoneCandidate(
                                bbox=(int(xyxy[0]), int(xyxy[1]), w, h),
                                confidence=round(conf, 2),
                                source="FULL_FRAME"
                            ))
            except Exception as e:
                logger.debug(f"Full-frame SentinelVision error: {e}")

        return candidates

    def run_person_roi(
        self,
        frame: np.ndarray,
        person_boxes: Optional[List[Tuple[int, int, int, int]]]
    ) -> Tuple[List[PhoneCandidate], Optional[Tuple[int, int, int, int]]]:
        """
        Pass 2: Extracts expanded person body crop, runs targeted high-res inference,
        and accurately transforms crop coordinates back to full-frame coordinates.
        """
        if not person_boxes or frame is None or frame.size == 0:
            return [], None

        fh, fw = frame.shape[:2]
        # Use the primary/largest person box
        px, py, pw, ph = person_boxes[0]

        # Expand person box with padding to include lap, hands, and perimeter
        pad_w = int(pw * self.roi_padding)
        pad_h = int(ph * self.roi_padding)

        roi_x1 = max(0, px - pad_w)
        roi_y1 = max(0, py - pad_h)
        roi_x2 = min(fw, px + pw + pad_w)
        roi_y2 = min(fh, py + ph + pad_h)
        roi_w = roi_x2 - roi_x1
        roi_h = roi_y2 - roi_y1

        if roi_w < 60 or roi_h < 60:
            return [], None

        roi_crop = frame[roi_y1:roi_y2, roi_x1:roi_x2]
        if roi_crop.size == 0:
            return [], None

        candidates = []
        roi_box_full = (roi_x1, roi_y1, roi_w, roi_h)

        # Targeted inference on Person ROI using YOLO11s
        try:
            res_roi = self.yolo_model.predict(
                source=roi_crop,
                classes=[COCO_CLASS_CELL_PHONE, COCO_CLASS_REMOTE],
                conf=self.candidate_confidence,
                imgsz=self.roi_imgsz,
                verbose=False
            )
            if len(res_roi) > 0 and res_roi[0].boxes is not None:
                for box in res_roi[0].boxes:
                    conf = float(box.conf[0].cpu().numpy())
                    c_xyxy = box.xyxy[0].cpu().numpy().astype(int)
                    cw, ch = int(c_xyxy[2] - c_xyxy[0]), int(c_xyxy[3] - c_xyxy[1])

                    # Transform crop coordinates -> full-frame coordinates
                    full_x1 = roi_x1 + int(c_xyxy[0])
                    full_y1 = roi_y1 + int(c_xyxy[1])

                    if self.validate_geometry(cw, ch, fw, fh, source="PERSON_ROI_YOLO11"):
                        candidates.append(PhoneCandidate(
                            bbox=(full_x1, full_y1, cw, ch),
                            confidence=round(conf, 2),
                            source="PERSON_ROI"
                        ))
        except Exception as e:
            logger.debug(f"Person ROI YOLO11s error: {e}")

        # Targeted inference on Person ROI using SentinelVision
        if self.sentinel_model is not None and self.sentinel_class_id is not None:
            try:
                res_sent_roi = self.sentinel_model.predict(
                    source=roi_crop,
                    classes=[self.sentinel_class_id],
                    conf=self.candidate_confidence,
                    imgsz=self.roi_imgsz,
                    verbose=False
                )
                if len(res_sent_roi) > 0 and res_sent_roi[0].boxes is not None:
                    for box in res_sent_roi[0].boxes:
                        conf = float(box.conf[0].cpu().numpy())
                        c_xyxy = box.xyxy[0].cpu().numpy().astype(int)
                        cw, ch = int(c_xyxy[2] - c_xyxy[0]), int(c_xyxy[3] - c_xyxy[1])

                        full_x1 = roi_x1 + int(c_xyxy[0])
                        full_y1 = roi_y1 + int(c_xyxy[1])

                        if self.validate_geometry(cw, ch, fw, fh, source="PERSON_ROI_SENTINEL"):
                            candidates.append(PhoneCandidate(
                                bbox=(full_x1, full_y1, cw, ch),
                                confidence=round(conf, 2),
                                source="PERSON_ROI"
                            ))
            except Exception as e:
                logger.debug(f"Person ROI SentinelVision error: {e}")

        return candidates, roi_box_full

    def run_adaptive_sahi(
        self,
        frame: np.ndarray,
        person_roi_box: Optional[Tuple[int, int, int, int]],
        existing_candidates: List[PhoneCandidate]
    ) -> List[PhoneCandidate]:
        """
        Pass 3: Adaptive SAHI Slicing Fallback.
        Slices the student ROI into high-resolution overlapping tiles when candidates
        fall in the uncertain confidence band or when small phones need sub-patch verification.
        """
        if not self.sahi_enabled or frame is None or person_roi_box is None:
            return []

        # Determine if adaptive SAHI should trigger
        max_existing_conf = max([c.confidence for c in existing_candidates], default=0.0)
        has_confident_phone = max_existing_conf >= self.sahi_trigger_max_conf
        has_marginal_phone = self.sahi_trigger_min_conf <= max_existing_conf < self.sahi_trigger_max_conf
        has_no_phone = len(existing_candidates) == 0

        # Trigger ONLY on marginal confidence or when verifying an uncertain scene
        should_trigger = has_marginal_phone or (has_no_phone and getattr(config, 'SHOW_DIAGNOSTICS', False))
        if not should_trigger or has_confident_phone:
            return []

        rx, ry, rw, rh = person_roi_box
        fh, fw = frame.shape[:2]
        crop = frame[ry:ry+rh, rx:rx+rw]
        if crop.size == 0 or rw < self.sahi_slice_size // 2 or rh < self.sahi_slice_size // 2:
            return []

        slice_sz = self.sahi_slice_size
        step = int(slice_sz * (1.0 - self.sahi_overlap))
        sahi_candidates = []

        # Generate slicing grid
        y_starts = list(range(0, max(1, rh - slice_sz + 1), step))
        if y_starts[-1] + slice_sz < rh:
            y_starts.append(rh - slice_sz)

        x_starts = list(range(0, max(1, rw - slice_sz + 1), step))
        if x_starts[-1] + slice_sz < rw:
            x_starts.append(rw - slice_sz)

        for sy in y_starts:
            for sx in x_starts:
                tile = crop[sy:min(rh, sy + slice_sz), sx:min(rw, sx + slice_sz)]
                if tile.shape[0] < 40 or tile.shape[1] < 40:
                    continue

                try:
                    res_tile = self.yolo_model.predict(
                        source=tile,
                        classes=[COCO_CLASS_CELL_PHONE, COCO_CLASS_REMOTE],
                        conf=self.candidate_confidence,
                        imgsz=slice_sz,
                        verbose=False
                    )
                    if len(res_tile) > 0 and res_tile[0].boxes is not None:
                        for b in res_tile[0].boxes:
                            conf = float(b.conf[0].cpu().numpy())
                            t_xyxy = b.xyxy[0].cpu().numpy().astype(int)
                            tw, th = int(t_xyxy[2] - t_xyxy[0]), int(t_xyxy[3] - t_xyxy[1])

                            # Sliced Tile -> Person ROI -> Full-Frame Coordinates
                            full_x1 = rx + sx + int(t_xyxy[0])
                            full_y1 = ry + sy + int(t_xyxy[1])

                            if self.validate_geometry(tw, th, fw, fh, source="SAHI_TILE"):
                                sahi_candidates.append(PhoneCandidate(
                                    bbox=(full_x1, full_y1, tw, th),
                                    confidence=round(conf, 2),
                                    source="SAHI"
                                ))
                except Exception:
                    pass

        return sahi_candidates

    def merge_and_deduplicate(self, candidates: List[PhoneCandidate], fw: int, fh: int) -> List[PhoneCandidate]:
        """Merges detections across all passes and applies IoU non-maximum suppression."""
        if not candidates:
            return []

        # Sort candidates descending by confidence
        sorted_cands = sorted(candidates, key=lambda c: c.confidence, reverse=True)
        merged: List[PhoneCandidate] = []
        nms_iou_threshold = self.cfg.get("iou_nms_threshold", 0.40)

        for cand in sorted_cands:
            is_dup = False
            for kept in merged:
                iou = compute_iou_xywh(cand.bbox, kept.bbox)
                containment = compute_containment_ratio(cand.bbox, kept.bbox)
                if iou >= nms_iou_threshold or containment >= 0.65:
                    is_dup = True
                    break
            if not is_dup:
                merged.append(cand)

        return merged

    def update_hand_context(self, candidates: List[PhoneCandidate], hand_boxes: Optional[List[Tuple[int, int, int, int]]]):
        """Calculates hand proximity and boosts confidence when phone is held or near student hands."""
        if not candidates or not hand_boxes or not self.hand_context_enabled:
            return

        for cand in candidates:
            cx = cand.bbox[0] + cand.bbox[2] // 2
            cy = cand.bbox[1] + cand.bbox[3] // 2
            min_dist = float('inf')

            for hx1, hy1, hx2, hy2 in hand_boxes:
                hcx = (hx1 + hx2) // 2
                hcy = (hy1 + hy2) // 2
                dist = np.sqrt((cx - hcx)**2 + (cy - hcy)**2)
                if dist < min_dist:
                    min_dist = dist

            if min_dist <= self.hand_proximity_radius:
                # Proximity score ranges from 0.5 (at edge) to 1.0 (inside hand)
                prox_score = float(max(0.0, 1.0 - (min_dist / self.hand_proximity_radius)))
                cand.hand_proximity = round(prox_score, 2)
                # Boost confidence by up to hand_proximity_boost
                cand.adjusted_confidence = min(0.99, round(cand.confidence + (prox_score * self.hand_proximity_boost), 2))

    def update_static_filter(self, candidates: List[PhoneCandidate], person_box: Optional[Tuple[int, int, int, int]]) -> List[PhoneCandidate]:
        """Eliminates static background fixtures (e.g. wall switchboards) appearing across consecutive cycles."""
        self._static_cycle_counter += 1
        current_cycle = self._static_cycle_counter
        consecutive_limit = self.cfg.get("static_consecutive_cycles", 6)
        iou_threshold = self.cfg.get("static_iou_threshold", 0.40)

        surviving = []
        for cand in candidates:
            matched_entry = None
            for entry in self._static_tracker:
                if compute_iou_xywh(cand.bbox, entry["bbox"]) >= iou_threshold:
                    matched_entry = entry
                    break

            if matched_entry is not None:
                matched_entry["count"] += 1
                matched_entry["last_cycle"] = current_cycle
                matched_entry["bbox"] = cand.bbox
                if matched_entry["count"] >= consecutive_limit:
                    logger.debug(f"[STATIC SUPPRESS] Static object suppressed at {cand.bbox} (count={matched_entry['count']})")
                    continue
                surviving.append(cand)
            else:
                self._static_tracker.append({
                    "bbox": cand.bbox,
                    "count": 1,
                    "last_cycle": current_cycle
                })
                surviving.append(cand)

        # Prune stale trackers (not seen for > 4 cycles)
        self._static_tracker = [e for e in self._static_tracker if (current_cycle - e["last_cycle"]) <= 4]
        return surviving

    def update_tracker(self, candidates: List[PhoneCandidate]) -> List[PhoneTrack]:
        """Lightweight multi-frame tracking: associates detections with existing tracks to prevent flickering."""
        if not self.tracking_enabled:
            # If tracking disabled, return instant 1-frame tracks
            return [PhoneTrack(i, c, window_size=self.temporal_window) for i, c in enumerate(candidates, start=1)]

        matched_track_indices = set()
        unmatched_candidates = []

        for cand in candidates:
            cand_cx = cand.bbox[0] + cand.bbox[2] // 2
            cand_cy = cand.bbox[1] + cand.bbox[3] // 2

            best_match_idx = None
            best_score = 0.0

            for idx, track in enumerate(self._tracks):
                if idx in matched_track_indices:
                    continue
                iou = compute_iou_xywh(cand.bbox, track.bbox)
                tcx = track.bbox[0] + track.bbox[2] // 2
                tcy = track.bbox[1] + track.bbox[3] // 2
                center_dist = np.sqrt((cand_cx - tcx)**2 + (cand_cy - tcy)**2)

                if iou >= self.track_iou_threshold or center_dist <= self.track_center_dist_threshold:
                    score = iou + max(0.0, 1.0 - (center_dist / self.track_center_dist_threshold))
                    if score > best_score:
                        best_score = score
                        best_match_idx = idx

            if best_match_idx is not None:
                self._tracks[best_match_idx].update(cand)
                matched_track_indices.add(best_match_idx)
            else:
                unmatched_candidates.append(cand)

        # Mark unmatched existing tracks as missed
        for idx, track in enumerate(self._tracks):
            if idx not in matched_track_indices:
                track.mark_missed()

        # Create new tracks for unmatched candidates
        for cand in unmatched_candidates:
            new_track = PhoneTrack(self._next_track_id, cand, window_size=self.temporal_window)
            self._next_track_id += 1
            self._tracks.append(new_track)

        # Prune dead tracks that exceeded max age without detection
        self._tracks = [t for t in self._tracks if t.age_since_last_hit <= self.track_max_age]
        return self._tracks

    def update_state_machine(self, active_tracks: List[PhoneTrack]) -> Tuple[str, List[PhoneTrack]]:
        """
        Evaluates temporal evidence per track to update state machine:
        NO_PHONE -> PHONE_SUSPECTED -> PHONE_CONFIRMED -> PHONE_COOLDOWN
        """
        now = time.time()
        confirmed_tracks = []

        # Check cooldown
        if self._in_cooldown:
            if now - self._last_violation_time < self.cooldown_seconds:
                return "PHONE_COOLDOWN", []
            else:
                self._in_cooldown = False

        for track in active_tracks:
            pos_hits = track.positive_count
            mean_conf = track.mean_confidence

            # Confirmation condition: persistent evidence within temporal window
            if pos_hits >= self.min_positive_frames and mean_conf >= (self.violation_confidence - 0.05):
                track.state = "PHONE_CONFIRMED"
                confirmed_tracks.append(track)
            elif pos_hits >= 2:
                track.state = "PHONE_SUSPECTED"
            else:
                track.state = "NO_PHONE"

        if confirmed_tracks:
            overall_state = "PHONE_DETECTED"
            self._last_violation_time = now
        elif any(t.state == "PHONE_SUSPECTED" for t in active_tracks):
            overall_state = "PHONE_SUSPECTED"
        else:
            overall_state = "NORMAL"

        return overall_state, confirmed_tracks

    def process(
        self,
        frame: np.ndarray,
        person_boxes: Optional[List[Tuple[int, int, int, int]]] = None,
        hand_boxes: Optional[List[Tuple[int, int, int, int]]] = None
    ) -> Dict[str, Any]:
        """
        Executes complete multi-stage detection pipeline with performance telemetry.
        """
        t_start = time.perf_counter()
        telemetry = {}

        if frame is None or frame.size == 0:
            return {
                "state": "NORMAL",
                "confirmed_tracks": [],
                "all_tracks": [],
                "candidates": [],
                "roi_box": None,
                "telemetry": {}
            }

        fh, fw = frame.shape[:2]

        # Pass 1: Full-Frame Global Detection
        t0 = time.perf_counter()
        full_candidates = self.run_full_frame(frame)
        telemetry["full_frame_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)

        # Pass 2: High-Resolution Person ROI Inspection
        t1 = time.perf_counter()
        roi_candidates, person_roi_box = self.run_person_roi(frame, person_boxes)
        telemetry["roi_ms"] = round((time.perf_counter() - t1) * 1000.0, 1)

        # Pass 3: Adaptive SAHI Slicing Fallback
        t2 = time.perf_counter()
        sahi_candidates = self.run_adaptive_sahi(frame, person_roi_box, full_candidates + roi_candidates)
        telemetry["sahi_ms"] = round((time.perf_counter() - t2) * 1000.0, 1)
        telemetry["sahi_triggered"] = len(sahi_candidates) > 0

        # Combine, Deduplicate, and Validate
        all_raw = full_candidates + roi_candidates + sahi_candidates
        merged = self.merge_and_deduplicate(all_raw, fw, fh)

        # Hand Context Proximity Fusion
        self.update_hand_context(merged, hand_boxes)

        # Static Background Suppression
        valid_candidates = self.update_static_filter(merged, person_boxes[0] if person_boxes else None)

        # Multi-Frame Tracking
        t3 = time.perf_counter()
        tracks = self.update_tracker(valid_candidates)
        telemetry["tracking_ms"] = round((time.perf_counter() - t3) * 1000.0, 1)

        # State Machine & Temporal Aggregation
        overall_state, confirmed_tracks = self.update_state_machine(tracks)

        t_total = time.perf_counter() - t_start
        telemetry["total_ms"] = round(t_total * 1000.0, 1)
        telemetry["fps"] = round(1.0 / max(t_total, 1e-4), 1)

        return {
            "state": overall_state,
            "confirmed_tracks": confirmed_tracks,
            "all_tracks": tracks,
            "candidates": valid_candidates,
            "roi_box": person_roi_box,
            "telemetry": telemetry
        }
