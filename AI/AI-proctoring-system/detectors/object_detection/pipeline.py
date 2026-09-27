"""
pipeline.py — Clean, reliable object detection pipeline.

Uses YOLO11 directly for all detections (person, phone, book).
YOLO11 achieves 0.7-0.99 confidence on phones (cls=67), 0.9+ on persons (cls=0),
and reliable book detection (cls=73, 84).

Architecture: Single-pass YOLO11 → NMS → SimpleTracker → temporal window → state output.
No Sentinel dependency. Simple, fast, testable, reliable.
"""

import time
import logging
from collections import deque
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import cv2

import torch
try:
    torch.set_num_threads(2)  # Prevent CPU thrashing with InsightFace & MediaPipe
except Exception:
    pass

logger = logging.getLogger(__name__)

# ─── YOLO11 COCO class IDs ───────────────────────────────────────────────────
CLS_PERSON      = 0
CLS_CELL_PHONE  = 67
CLS_BOOK        = 73
CLS_REMOTE      = 65   # often misclassified as phone — treat as phone candidate

# ─── Colour palette for debug rendering ─────────────────────────────────────
COLOR_PERSON = (255, 200, 0)    # Cyan-yellow
COLOR_PHONE  = (180, 0, 255)    # Magenta
COLOR_BOOK   = (0, 165, 255)    # Orange
COLOR_ROI    = (80, 200, 60)    # Green


# ─── Simple IoU helper ───────────────────────────────────────────────────────
def _iou(a: Tuple, b: Tuple) -> float:
    """Computes IoU between two (x,y,w,h) boxes."""
    ax1, ay1, aw, ah = a
    bx1, by1, bw, bh = b
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


# ─── Simple NMS ──────────────────────────────────────────────────────────────
def _nms(detections: List[Dict], iou_thresh: float = 0.45) -> List[Dict]:
    """Greedy NMS on a list of {bbox, confidence} dicts, sorted by confidence."""
    if not detections:
        return []
    sorted_dets = sorted(detections, key=lambda d: d["confidence"], reverse=True)
    kept = []
    for d in sorted_dets:
        if all(_iou(d["bbox"], k["bbox"]) < iou_thresh for k in kept):
            kept.append(d)
    return kept


# ─── IoU-based track matcher ─────────────────────────────────────────────────
class SimpleTracker:
    """Lightweight IoU tracker. Assigns stable IDs to detected objects."""

    def __init__(self, iou_thresh: float = 0.30, max_age: int = 2):
        self.tracks: List[Dict] = []
        self.next_id = 1
        self.iou_thresh = iou_thresh
        self.max_age = max_age

    def update(self, detections: List[Dict]) -> List[Dict]:
        """Match detections to existing tracks; age out stale ones."""
        for track in self.tracks:
            track["age"] += 1

        for det in detections:
            best_iou, best_track = 0.0, None
            for track in self.tracks:
                iou = _iou(det["bbox"], track["bbox"])
                if iou > best_iou and iou >= self.iou_thresh:
                    best_iou, best_track = iou, track

            if best_track is not None:
                best_track.update({
                    "bbox": det["bbox"],
                    "confidence": det["confidence"],
                    "source": det.get("source", "yolo11"),
                    "age": 0,
                    "hits": best_track["hits"] + 1
                })
            else:
                self.tracks.append({
                    "id": self.next_id,
                    "bbox": det["bbox"],
                    "confidence": det["confidence"],
                    "source": det.get("source", "yolo11"),
                    "age": 0,
                    "hits": 1
                })
                self.next_id += 1

        # Remove stale tracks — max_age=1 means box vanishes within 1 missed frame
        self.tracks = [t for t in self.tracks if t["age"] <= self.max_age]
        return list(self.tracks)


# ─── Rolling temporal window ─────────────────────────────────────────────────
class TemporalWindow:
    """Tracks positive/negative detections over a rolling window."""

    def __init__(self, window: int = 2, min_positives: int = 1, cooldown_sec: float = 0.0):
        self.window = deque(maxlen=max(1, window))
        self.min_positives = max(1, min_positives)
        self.confirmed = False
        self.cooldown_until = 0.0
        self.cooldown_sec = cooldown_sec

    def update(self, detected: bool, confidence: float) -> Dict[str, Any]:
        self.window.append(1 if detected else 0)
        pos = sum(self.window)
        now = time.time()

        if self.cooldown_sec > 0.0 and now < self.cooldown_until:
            self.confirmed = False
        elif pos >= self.min_positives:
            self.confirmed = True
        else:
            # No grace period — clear immediately when object is gone
            self.confirmed = False

        return {
            "confirmed": self.confirmed,
            "positive_frames": pos,
            "window_size": len(self.window),
            "score": round(confidence, 3)
        }

    def reset(self):
        self.window.clear()
        self.confirmed = False
        self.cooldown_until = 0.0


# ─── Main Pipeline ───────────────────────────────────────────────────────────
class ObjectDetectionPipeline:
    """
    Clean YOLO11-based detection pipeline.

    Single-pass YOLO11 inference detects persons (cls=0), phones (cls=67),
    and books (cls=73). Results flow through NMS → SimpleTracker → temporal window.

    Config keys (all optional, sensible defaults for instant detection):
        person_conf       : float  (default 0.40)
        phone_conf        : float  (default 0.20)   # low floor to catch held/tilted phones
        book_conf         : float  (default 0.35)
        phone_window      : int    (default 2)       # 2-frame window
        phone_min_pos     : int    (default 1)       # confirm on first hit
        phone_cooldown    : float  (default 0.0)     # no cooldown
        phone_max_age     : int    (default 1)       # clear box after 1 missed frame
        book_window       : int    (default 4)
        book_min_pos      : int    (default 1)
        book_cooldown     : float  (default 0.0)
        book_max_age      : int    (default 3)
        person_max_age    : int    (default 8)
        imgsz             : int    (default 480)
        device            : str    (default 'cpu')
        min_person_area   : float  (default 0.02)
        max_phone_area    : float  (default 0.50)
    """

    def __init__(self, yolo_model_path: str, config: Dict[str, Any] = None):
        from ultralytics import YOLO
        cfg = config or {}

        self.person_conf     = cfg.get("person_conf",     0.40)
        self.phone_conf      = cfg.get("phone_conf",       0.20)  # low floor for high recall
        self.book_conf       = cfg.get("book_conf",        0.35)
        self.imgsz           = cfg.get("imgsz",            480)
        self.device          = cfg.get("device",           "cpu")
        self.min_person_area = cfg.get("min_person_area",  0.02)
        self.max_phone_area  = cfg.get("max_phone_area",   0.50)

        # Floor conf for single YOLO pass — min of all per-class thresholds so
        # YOLO's internal NMS doesn't discard candidates before per-class filters run.
        self._yolo_pass_conf = min(self.person_conf, self.phone_conf, self.book_conf)

        # Temporal windows
        phone_window   = cfg.get("phone_window",   2)
        phone_min_pos  = cfg.get("phone_min_pos",  1)
        phone_cooldown = cfg.get("phone_cooldown", 0.0)
        book_window    = cfg.get("book_window",    4)
        book_min_pos   = cfg.get("book_min_pos",   1)
        book_cooldown  = cfg.get("book_cooldown",  0.0)

        # Tracker max_age: how many missed frames before track is purged
        # phone_max_age=1 → box disappears within 1 inference cycle after leaving screen
        phone_max_age  = cfg.get("phone_max_age",  1)
        book_max_age   = cfg.get("book_max_age",   3)
        person_max_age = cfg.get("person_max_age", 8)

        self.model = YOLO(yolo_model_path, task="detect")
        self.person_tracker = SimpleTracker(iou_thresh=0.40, max_age=person_max_age)
        self.phone_tracker  = SimpleTracker(iou_thresh=0.30, max_age=phone_max_age)
        self.book_tracker   = SimpleTracker(iou_thresh=0.35, max_age=book_max_age)
        self.phone_temporal = TemporalWindow(window=phone_window, min_positives=phone_min_pos, cooldown_sec=phone_cooldown)
        self.book_temporal  = TemporalWindow(window=book_window,  min_positives=book_min_pos,  cooldown_sec=book_cooldown)

        self._frame_id = 0
        logger.info(
            f"ObjectDetectionPipeline ready: model={yolo_model_path}, "
            f"device={self.device}, imgsz={self.imgsz}, "
            f"phone_conf={self.phone_conf}, phone_max_age={phone_max_age}, "
            f"phone_window={phone_window}/{phone_min_pos}"
        )

    def _run_yolo(self, frame: np.ndarray, classes: List[int], conf: float) -> List[Dict]:
        """Run YOLO11 inference and return [{bbox, confidence, class_id, class_name}]."""
        results = self.model.predict(
            source=frame,
            conf=conf,
            classes=classes,
            imgsz=self.imgsz,
            device=self.device,
            verbose=False
        )
        detections = []
        if results and results[0].boxes is not None:
            boxes = results[0].boxes
            names = self.model.names

            # Batch-extract all tensors in one .cpu().numpy() call each —
            # eliminates 3×N per-box device-sync round-trips.
            all_cls  = boxes.cls.cpu().numpy().astype(int)
            all_conf = boxes.conf.cpu().numpy()
            all_xyxy = boxes.xyxy.cpu().numpy().astype(int)

            for i in range(len(all_cls)):
                cls_id = int(all_cls[i])
                c      = float(all_conf[i])
                x1, y1, x2, y2 = all_xyxy[i]
                detections.append({
                    "bbox":       (int(x1), int(y1), int(x2 - x1), int(y2 - y1)),
                    "confidence": round(c, 3),
                    "class_id":   cls_id,
                    "class_name": names.get(cls_id, str(cls_id)),
                    "source":     "yolo11"
                })
        return detections

    def _filter_person(self, dets: List[Dict], frame_area: int) -> List[Dict]:
        """Remove person detections that are too small (likely false positives)."""
        return [
            d for d in dets
            if (d["bbox"][2] * d["bbox"][3]) >= (self.min_person_area * frame_area)
        ]

    def _filter_phone(self, dets: List[Dict], frame_area: int,
                      fw: int, fh: int) -> List[Dict]:
        """Remove phone detections that are implausibly large or tiny."""
        kept = []
        for d in dets:
            x, y, w, h = d["bbox"]
            area = w * h
            if area < 150:                                  # too small (< 150 px²)
                continue
            if area > self.max_phone_area * frame_area:     # takes up >50% of frame
                continue
            if w > fw * 0.85 or h > fh * 0.90:             # nearly full frame
                continue
            kept.append(d)
        return kept

    def process(self, frame: np.ndarray) -> Dict[str, Any]:
        """
        Run full detection on a frame.

        Returns:
        {
          "persons"      : List[Dict],   # [{bbox, confidence, id, hits, age, source}]
          "phones"       : List[Dict],   # tracked phone detections
          "books"        : List[Dict],   # tracked book detections
          "phone_state"  : Dict,         # {confirmed, positive_frames, window_size, score}
          "book_state"   : Dict,
          "frame_id"     : int,
          "latency_ms"   : float
        }
        """
        t_start = time.perf_counter()
        self._frame_id += 1
        fid = self._frame_id

        if frame is None or frame.size == 0:
            return self._empty(fid, 0.0)

        fh, fw = frame.shape[:2]
        frame_area = fh * fw

        # ── Single YOLO11 pass: detect all classes at once ──────────────────
        # Use the pre-computed floor conf (min of all per-class thresholds) so
        # YOLO's internal NMS doesn't discard boxes that per-class filters need.
        all_classes = [CLS_PERSON, CLS_CELL_PHONE, CLS_REMOTE, CLS_BOOK]
        raw = self._run_yolo(frame, classes=all_classes, conf=self._yolo_pass_conf)

        # ── Split by class ───────────────────────────────────────────────────
        raw_persons = [d for d in raw if d["class_id"] == CLS_PERSON]
        raw_phones  = [d for d in raw if d["class_id"] in (CLS_CELL_PHONE, CLS_REMOTE)]
        raw_books   = [d for d in raw if d["class_id"] == CLS_BOOK]

        # ── Filter persons by area and confidence ────────────────────────────
        raw_persons = [d for d in raw_persons if d["confidence"] >= self.person_conf]
        person_dets = _nms(self._filter_person(raw_persons, frame_area), iou_thresh=0.45)

        # ── Filter phones by confidence + geometry ───────────────────────────
        raw_phones = [d for d in raw_phones if d["confidence"] >= self.phone_conf]
        raw_phones = self._filter_phone(raw_phones, frame_area, fw, fh)
        phone_dets = _nms(raw_phones, iou_thresh=0.40)

        # ── Filter books by confidence ───────────────────────────────────────
        raw_books = [d for d in raw_books if d["confidence"] >= self.book_conf]
        book_dets = _nms(raw_books, iou_thresh=0.40)

        # ── Track objects ─────────────────────────────────────────────────────
        person_tracks = self.person_tracker.update(person_dets)
        phone_tracks  = self.phone_tracker.update(phone_dets)
        book_tracks   = self.book_tracker.update(book_dets)

        # ── Temporal confirmation ────────────────────────────────────────────
        max_phone_conf = max((t["confidence"] for t in phone_tracks), default=0.0)
        max_book_conf  = max((t["confidence"] for t in book_tracks),  default=0.0)

        phone_state = self.phone_temporal.update(len(phone_tracks) > 0, max_phone_conf)
        book_state  = self.book_temporal.update(len(book_tracks) > 0,   max_book_conf)

        latency = (time.perf_counter() - t_start) * 1000.0

        return {
            "persons":     person_tracks,
            "phones":      phone_tracks,
            "books":       book_tracks,
            "phone_state": phone_state,
            "book_state":  book_state,
            "frame_id":    fid,
            "latency_ms":  round(latency, 1)
        }

    @staticmethod
    def _empty(fid: int, latency: float) -> Dict[str, Any]:
        return {
            "persons":     [],
            "phones":      [],
            "books":       [],
            "phone_state": {"confirmed": False, "positive_frames": 0, "window_size": 0, "score": 0.0},
            "book_state":  {"confirmed": False, "positive_frames": 0, "window_size": 0, "score": 0.0},
            "frame_id":    fid,
            "latency_ms":  latency
        }

    def render_debug_frame(self, frame: np.ndarray, output: Dict[str, Any]) -> np.ndarray:
        """Draws bounding boxes and HUD onto a copy of the frame for debug inspection."""
        out = frame.copy()
        font = cv2.FONT_HERSHEY_SIMPLEX

        def _box(img, bbox, color, label, thickness=2):
            x, y, w, h = bbox
            cv2.rectangle(img, (x, y), (x + w, y + h), color, thickness)
            lbl_w, lbl_h = cv2.getTextSize(label, font, 0.50, 1)[0]
            cv2.rectangle(img, (x, max(0, y - lbl_h - 8)), (x + lbl_w + 8, y), color, -1)
            cv2.putText(img, label, (x + 4, y - 4), font, 0.50, (0, 0, 0), 1)

        for p in output.get("persons", []):
            _box(out, p["bbox"], COLOR_PERSON, f"PERSON {p['confidence']:.2f}", 2)

        ph_confirmed = output.get("phone_state", {}).get("confirmed", False)
        for t in output.get("phones", []):
            color = (0, 0, 230) if ph_confirmed else COLOR_PHONE
            label = f"PHONE {t['confidence']:.2f} [#{t['id']}]"
            _box(out, t["bbox"], color, label, 3 if ph_confirmed else 2)

        bk_confirmed = output.get("book_state", {}).get("confirmed", False)
        for t in output.get("books", []):
            color = (0, 0, 200) if bk_confirmed else COLOR_BOOK
            label = f"BOOK {t['confidence']:.2f} [#{t['id']}]"
            _box(out, t["bbox"], color, label, 3 if bk_confirmed else 2)

        # HUD
        ph_s = output.get("phone_state", {})
        bk_s = output.get("book_state",  {})
        lat  = output.get("latency_ms", 0)
        hud  = [
            f"Frame #{output.get('frame_id',0)} | Latency: {lat:.0f}ms",
            f"Persons: {len(output.get('persons',[]))}  |  Phones: {len(output.get('phones',[]))} [confirmed={ph_s.get('confirmed',False)}] ({ph_s.get('positive_frames',0)}/{ph_s.get('window_size',0)})",
            f"Books:   {len(output.get('books',[]))}  [confirmed={bk_s.get('confirmed',False)}] ({bk_s.get('positive_frames',0)}/{bk_s.get('window_size',0)})"
        ]
        bg_h = len(hud) * 20 + 10
        cv2.rectangle(out, (5, 5), (580, bg_h + 10), (20, 20, 20), -1)
        for i, line in enumerate(hud):
            cv2.putText(out, line, (10, 24 + i * 20), font, 0.48, (200, 255, 200), 1)

        return out
