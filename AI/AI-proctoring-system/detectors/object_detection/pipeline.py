"""
pipeline.py — Clean, reliable object detection pipeline.

Uses YOLO11 directly for all detections (person, phone, book).
YOLO11 achieves 0.7-0.99 confidence on phones (cls=67), 0.9+ on persons (cls=0),
and reliable book detection (cls=73, 84).

Architecture: Single-pass YOLO11 → NMS → temporal window → state output.
No Sentinel dependency for primary detection. Simple, testable, reliable.
"""

import time
import logging
from collections import deque
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import cv2
import os
import ast
from pathlib import Path

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


# ─── Simple Letterbox helper ────────────────────────────────────────────────
def _letterbox(im: np.ndarray, new_shape: Tuple[int, int] = (640, 640),
               color: Tuple[int, int, int] = (114, 114, 114)) -> Tuple[np.ndarray, float, Tuple[float, float]]:
    """Standard YOLO letterbox resizing preserving aspect ratio with padding."""
    shape = im.shape[:2]  # [height, width]
    r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
    new_unpad = int(round(shape[1] * r)), int(round(shape[0] * r))
    dw, dh = (new_shape[1] - new_unpad[0]) / 2, (new_shape[0] - new_unpad[1]) / 2
    top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
    left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
    im_resized = cv2.resize(im, new_unpad, interpolation=cv2.INTER_LINEAR)
    im_padded = cv2.copyMakeBorder(im_resized, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)
    return im_padded, r, (dw, dh)


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

    def __init__(self, iou_thresh: float = 0.30, max_age: int = 8):
        self.tracks: List[Dict] = []
        self.next_id = 1
        self.iou_thresh = iou_thresh
        self.max_age = max_age

    def update(self, detections: List[Dict]) -> List[Dict]:
        """Match detections to existing tracks; age out stale ones."""
        matched = set()
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
                matched.add(id(best_track))
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

        self.tracks = [t for t in self.tracks if t["age"] <= self.max_age]
        return list(self.tracks)


# ─── Rolling temporal window ─────────────────────────────────────────────────
class TemporalWindow:
    """Tracks positive/negative detections over a rolling window."""

    def __init__(self, window: int = 8, min_positives: int = 3):
        self.window = deque(maxlen=window)
        self.min_positives = min_positives
        self.confirmed = False
        self.cooldown_until = 0.0
        self.cooldown_sec = 3.0

    def update(self, detected: bool, confidence: float) -> Dict:
        self.window.append(1 if detected else 0)
        pos = sum(self.window)
        now = time.time()

        if now < self.cooldown_until:
            self.confirmed = False
        elif pos >= self.min_positives:
            self.confirmed = True
        else:
            if self.confirmed:
                # Grace: stay confirmed until window drops below half
                if pos < max(1, self.min_positives // 2):
                    self.confirmed = False
                    self.cooldown_until = now + self.cooldown_sec

        return {
            "confirmed": self.confirmed,
            "positive_frames": pos,
            "window_size": len(self.window),
            "score": confidence
        }

    def reset(self):
        self.window.clear()
        self.confirmed = False


# ─── Main Pipeline ───────────────────────────────────────────────────────────
class ObjectDetectionPipeline:
    """
    Clean YOLO11-based detection pipeline.

    Single-pass YOLO11 inference detects persons (cls=0), phones (cls=67),
    and books (cls=73/84). Results flow through NMS → tracker → temporal window.

    Config keys (all optional with safe defaults):
        person_conf       : float  (default 0.45)
        phone_conf        : float  (default 0.20)
        book_conf         : float  (default 0.35)
        phone_window      : int    (default 8)
        phone_min_pos     : int    (default 3)
        book_window       : int    (default 6)
        book_min_pos      : int    (default 2)
        imgsz             : int    (default 640)
        device            : str    (default 'cpu')
        min_person_area   : float  (default 0.02, fraction of frame area)
        max_phone_area    : float  (default 0.50, fraction of frame area)
    """

    def __init__(self, yolo_model_path: str, config: Dict[str, Any] = None):
        cfg = config or {}

        self.person_conf     = cfg.get("person_conf",     0.45)
        self.phone_conf      = cfg.get("phone_conf",      0.20)
        self.book_conf       = cfg.get("book_conf",       0.35)
        self.imgsz           = cfg.get("imgsz",           640)
        self.device          = cfg.get("device",          "cpu")
        self.num_threads     = cfg.get("num_threads",     4)
        self.use_onnx        = cfg.get("use_onnx",        True)
        self.min_person_area = cfg.get("min_person_area", 0.02)
        self.max_phone_area  = cfg.get("max_phone_area",  0.50)

        phone_window  = cfg.get("phone_window",  8)
        phone_min_pos = cfg.get("phone_min_pos", 3)
        book_window   = cfg.get("book_window",   6)
        book_min_pos  = cfg.get("book_min_pos",  2)

        self.person_tracker = SimpleTracker(iou_thresh=0.40, max_age=15)
        self.phone_tracker  = SimpleTracker(iou_thresh=0.30, max_age=8)
        self.book_tracker   = SimpleTracker(iou_thresh=0.35, max_age=6)
        self.phone_temporal = TemporalWindow(window=phone_window, min_positives=phone_min_pos)
        self.book_temporal  = TemporalWindow(window=book_window,  min_positives=book_min_pos)

        self._frame_id = 0
        self.is_onnx = False
        self.session = None
        self.input_name = None
        self.model = None

        # Standard COCO class names fallback
        self.class_names = {
            CLS_PERSON: "person",
            CLS_REMOTE: "remote",
            CLS_CELL_PHONE: "cell phone",
            CLS_BOOK: "book"
        }

        # Resolve model path & runtime engine
        resolved_path = Path(yolo_model_path)
        onnx_candidate = resolved_path if resolved_path.suffix.lower() == ".onnx" else resolved_path.with_suffix(".onnx")

        if self.use_onnx:
            # 1. Attempt loading ONNX Runtime model
            if not onnx_candidate.exists() and resolved_path.exists() and resolved_path.suffix.lower() == ".pt":
                logger.info(f"ONNX model '{onnx_candidate}' not found. Exporting from '{resolved_path}'...")
                try:
                    from ultralytics import YOLO
                    pt_temp = YOLO(str(resolved_path))
                    pt_temp.export(format="onnx", imgsz=self.imgsz, dynamic=False, opset=12)
                    logger.info(f"Successfully auto-exported ONNX model to '{onnx_candidate}'.")
                except Exception as exp_err:
                    logger.warning(f"Auto-export to ONNX failed: {exp_err}. Will fallback to PyTorch.")

            if onnx_candidate.exists():
                try:
                    import onnxruntime as ort
                    sess_opts = ort.SessionOptions()
                    sess_opts.intra_op_num_threads = self.num_threads
                    sess_opts.inter_op_num_threads = 1
                    sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                    self.session = ort.InferenceSession(str(onnx_candidate), sess_options=sess_opts, providers=["CPUExecutionProvider"])
                    self.input_name = self.session.get_inputs()[0].name
                    self.is_onnx = True

                    # Try extracting metadata class names from ONNX model
                    try:
                        meta_names = self.session.get_modelmeta().custom_metadata_map.get("names")
                        if meta_names:
                            parsed_names = ast.literal_eval(meta_names)
                            if isinstance(parsed_names, dict):
                                self.class_names.update(parsed_names)
                    except Exception:
                        pass

                    logger.info(f"ObjectDetectionPipeline initialized using ONNX Runtime ({onnx_candidate}) on CPUExecutionProvider with {self.num_threads} threads.")
                except Exception as ort_err:
                    logger.warning(f"Failed to load ONNX Runtime session: {ort_err}. Falling back to PyTorch.")
                    self.is_onnx = False

        if not self.is_onnx:
            # 2. PyTorch fallback with configurable threads (lazy import)
            import torch
            torch.set_num_threads(self.num_threads)
            from ultralytics import YOLO
            self.model = YOLO(str(resolved_path))
            if hasattr(self.model, "names") and isinstance(self.model.names, dict):
                self.class_names.update(self.model.names)
            logger.info(f"ObjectDetectionPipeline initialized using PyTorch ({resolved_path}) with {self.num_threads} threads.")

    def _run_yolo(self, frame: np.ndarray, classes: List[int], conf: float) -> List[Dict]:
        """Run YOLO inference via ONNX Runtime or PyTorch."""
        if self.is_onnx and self.session is not None:
            return self._run_onnx(frame, classes, conf)
        return self._run_pytorch(frame, classes, conf)

    def _run_onnx(self, frame: np.ndarray, classes: List[int], conf: float) -> List[Dict]:
        """High-performance ONNX Runtime inference with letterboxing, coordinate unscaling, and NMS."""
        orig_h, orig_w = frame.shape[:2]
        lb_img, ratio, (dw, dh) = _letterbox(frame, (self.imgsz, self.imgsz))
        blob = lb_img[..., ::-1].transpose(2, 0, 1).astype(np.float32) / 255.0
        blob = np.expand_dims(blob, axis=0)

        out = self.session.run(None, {self.input_name: blob})[0]
        preds = out[0].T  # Shape: [8400, 84]
        boxes = preds[:, :4]
        scores = preds[:, 4:]

        detections = []
        for cls_id in classes:
            if cls_id >= scores.shape[1]:
                continue
            cls_scores = scores[:, cls_id]
            mask = cls_scores >= conf
            if not np.any(mask):
                continue
            c_boxes = boxes[mask]
            c_scores = cls_scores[mask]

            x1 = (c_boxes[:, 0] - c_boxes[:, 2] / 2.0 - dw) / ratio
            y1 = (c_boxes[:, 1] - c_boxes[:, 3] / 2.0 - dh) / ratio
            x2 = (c_boxes[:, 0] + c_boxes[:, 2] / 2.0 - dw) / ratio
            y2 = (c_boxes[:, 1] + c_boxes[:, 3] / 2.0 - dh) / ratio

            x1 = np.clip(x1, 0, orig_w)
            y1 = np.clip(y1, 0, orig_h)
            x2 = np.clip(x2, 0, orig_w)
            y2 = np.clip(y2, 0, orig_h)

            nms_boxes = [[float(x), float(y), float(x2[i] - x), float(y2[i] - y)] for i, (x, y) in enumerate(zip(x1, y1))]
            nms_scores = [float(s) for s in c_scores]
            indices = cv2.dnn.NMSBoxes(nms_boxes, nms_scores, score_threshold=conf, nms_threshold=0.45)
            if len(indices) > 0:
                for idx in indices.flatten():
                    bx = int(round(x1[idx]))
                    by = int(round(y1[idx]))
                    bw = int(round(x2[idx] - x1[idx]))
                    bh = int(round(y2[idx] - y1[idx]))
                    detections.append({
                        "bbox": (bx, by, bw, bh),
                        "confidence": round(float(c_scores[idx]), 3),
                        "class_id": cls_id,
                        "class_name": self.class_names.get(cls_id, str(cls_id)),
                        "source": "yolo11"
                    })
        return detections

    def _run_pytorch(self, frame: np.ndarray, classes: List[int], conf: float) -> List[Dict]:
        """Fallback PyTorch inference."""
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
            names = self.model.names if hasattr(self.model, "names") else self.class_names
            for box in boxes:
                cls_id = int(box.cls[0].cpu().numpy())
                c      = float(box.conf[0].cpu().numpy())
                xyxy   = box.xyxy[0].cpu().numpy().astype(int)
                x1, y1, x2, y2 = xyxy
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
          "persons"      : List[Dict],   # [{bbox, confidence, ...}]
          "phones"       : List[Dict],   # tracked phone detections
          "books"        : List[Dict],   # tracked book detections
          "phone_state"  : Dict,         # {confirmed, positive_frames, score}
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
        all_classes = [CLS_PERSON, CLS_CELL_PHONE, CLS_REMOTE, CLS_BOOK]
        raw = self._run_yolo(frame, classes=all_classes, conf=self.phone_conf)

        # ── Split by class ───────────────────────────────────────────────────
        raw_persons = [d for d in raw if d["class_id"] == CLS_PERSON]
        raw_phones  = [d for d in raw if d["class_id"] in (CLS_CELL_PHONE, CLS_REMOTE)]
        raw_books   = [d for d in raw if d["class_id"] == CLS_BOOK]

        # ── Filter persons by area and confidence ────────────────────────────
        raw_persons = [d for d in raw_persons if d["confidence"] >= self.person_conf]
        person_dets = _nms(self._filter_person(raw_persons, frame_area), iou_thresh=0.45)

        # ── Filter phones by geometry ────────────────────────────────────────
        raw_phones = self._filter_phone(raw_phones, frame_area, fw, fh)
        phone_dets = _nms(raw_phones, iou_thresh=0.40)

        # ── Filter books by confidence ───────────────────────────────────────
        raw_books = [d for d in raw_books if d["confidence"] >= self.book_conf]
        book_dets = _nms(raw_books, iou_thresh=0.40)

        # ── Track objects ─────────────────────────────────────────────
        person_tracks = self.person_tracker.update(person_dets)
        phone_tracks  = self.phone_tracker.update(phone_dets)
        book_tracks   = self.book_tracker.update(book_dets)

        # ── Temporal confirmation ────────────────────────────────────────────
        max_phone_conf = max((t["confidence"] for t in phone_tracks), default=0.0)
        max_book_conf  = max((t["confidence"] for t in book_tracks),  default=0.0)

        phone_state = self.phone_temporal.update(len(phone_tracks) > 0, max_phone_conf)
        book_state  = self.book_temporal.update( len(book_tracks)  > 0, max_book_conf)

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
        fh, fw = out.shape[:2]
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
