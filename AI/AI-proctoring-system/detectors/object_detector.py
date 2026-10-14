"""
object_detector.py — Adapter between ObjectDetectionPipeline and the proctoring pipeline.

Wraps the clean YOLO11-based ObjectDetectionPipeline and converts its output
into the standard DetectorResult dict that main.py and violation_manager expect.
"""

import logging
import threading
from typing import Dict, Optional
import numpy as np

import config
from detectors.base_detector import BaseDetector, DetectorResult
from detectors.object_detection.pipeline import ObjectDetectionPipeline

logger = logging.getLogger(__name__)


class ObjectDetector(BaseDetector):
    """
    Clean adapter for the YOLO11-based object detection pipeline.
    Returns the standard {person, cell_phone, book} DetectorResult dict.
    """

    def __init__(self,
                 model_name: str = None,
                 img_size: int = None,
                 device: str = None,
                 num_threads: int = None,
                 use_onnx: bool = None):

        model_name  = model_name  or getattr(config, "YOLO_MODEL", "yolo11n.onnx")
        img_size    = img_size    or getattr(config, "YOLO_IMAGE_SIZE", 640)
        device      = device      or getattr(config, "DEVICE", "cpu")
        num_threads = num_threads or getattr(config, "YOLO_NUM_THREADS", 4)
        use_onnx    = use_onnx if use_onnx is not None else getattr(config, "YOLO_USE_ONNX", True)

        phone_cfg  = getattr(config, "PHONE_DETECTION_CONFIG", {})

        pipeline_config = {
            # Confidence thresholds
            "person_conf":     getattr(config, "PERSON_CONFIDENCE_THRESHOLD", 0.45),
            "phone_conf":      phone_cfg.get("candidate_confidence", 0.20),
            "book_conf":       getattr(config, "BOOK_CONFIDENCE_THRESHOLD", 0.35),

            # Temporal windows
            "phone_window":    phone_cfg.get("temporal_window",   8),
            "phone_min_pos":   phone_cfg.get("min_positive_frames", 1),
            "book_window":     6,
            "book_min_pos":    2,

            # Inference settings
            "imgsz":           img_size,
            "device":          device,
            "num_threads":     num_threads,
            "use_onnx":        use_onnx,

            # Geometry filters
            "min_person_area": getattr(config, "MIN_PERSON_BOX_AREA", 0.02),
            "max_phone_area":  0.50,
        }

        self.pipeline = ObjectDetectionPipeline(
            yolo_model_path=model_name,
            config=pipeline_config
        )
        self.detector_name = "ObjectDetector"

        # Thread-safe persistent worker infrastructure (bounded latest-frame buffer)
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._pending_frame: Optional[np.ndarray] = None
        self._stop_event = threading.Event()
        self._is_ready = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._latest_results: Dict[str, DetectorResult] = self._get_empty_results()

        logger.info(f"ObjectDetector initialized successfully (backend: {'ONNX Runtime' if getattr(self.pipeline, 'is_onnx', False) else 'PyTorch'}).")

    def _get_empty_results(self) -> Dict[str, DetectorResult]:
        """Returns standard default empty detection results with NORMAL states."""
        return {
            "person":     DetectorResult(detector_name="PersonDetector",
                                         state=config.STATE_NORMAL, message="No person detected"),
            "cell_phone": DetectorResult(detector_name="PhoneDetector",
                                         state=config.STATE_NORMAL, message="No phone detected"),
            "book":       DetectorResult(detector_name="BookDetector",
                                         state=config.STATE_NORMAL, message="No book detected"),
        }

    def start_worker(self) -> "ObjectDetector":
        """Start the persistent background YOLO inference worker thread."""
        with self._lock:
            if self._worker_thread is None or not self._worker_thread.is_alive():
                self._stop_event.clear()
                self._worker_thread = threading.Thread(
                    target=self._worker_loop,
                    name="PersistentYoloWorker",
                    daemon=True
                )
                self._worker_thread.start()
                logger.info("Persistent YOLO worker thread started.")
        return self

    def stop_worker(self, timeout: float = 2.0):
        """Cleanly terminate the persistent background worker thread."""
        self._stop_event.set()
        with self._condition:
            self._condition.notify_all()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=timeout)
            logger.info("Persistent YOLO worker thread stopped.")

    def submit_frame(self, frame: np.ndarray):
        """
        Thread-safe, non-blocking frame submission to bounded 1-frame buffer.
        Overwrites any unconsumed older frame to eliminate lag and stale buildup.
        """
        if frame is None or frame.size == 0 or self._stop_event.is_set():
            return
        with self._condition:
            self._pending_frame = frame
            self._condition.notify()

    def get_latest_results(self) -> Dict[str, DetectorResult]:
        """Thread-safe retrieval of latest inference results."""
        with self._lock:
            return self._latest_results

    def is_ready(self) -> bool:
        """Returns True if detector has completed pre-warming/initialization."""
        return self._is_ready.is_set()

    def wait_until_ready(self, timeout: float = 10.0) -> bool:
        """Wait until background warmup completes."""
        return self._is_ready.wait(timeout=timeout)

    def warmup(self, dummy_frame: Optional[np.ndarray] = None):
        """Synchronously pre-warm the detector."""
        if dummy_frame is None:
            h = getattr(config, "WEBCAM_HEIGHT", 720)
            w = getattr(config, "WEBCAM_WIDTH", 1280)
            dummy_frame = np.zeros((h, w, 3), dtype=np.uint8)
        try:
            self.process(dummy_frame)
            logger.info("YOLO ObjectDetector warmup completed successfully.")
        except Exception as e:
            logger.warning(f"ObjectDetector warmup warning: {e}")
        finally:
            self._is_ready.set()

    def start_background_warmup(self, dummy_frame: Optional[np.ndarray] = None):
        """Launch warmup asynchronously in background without blocking caller."""
        threading.Thread(
            target=self.warmup,
            args=(dummy_frame,),
            name="YoloWarmupWorker",
            daemon=True
        ).start()

    def _worker_loop(self):
        """Persistent worker loop pulling freshest frames and executing inference."""
        while not self._stop_event.is_set():
            with self._condition:
                while self._pending_frame is None and not self._stop_event.is_set():
                    self._condition.wait(timeout=0.1)
                if self._stop_event.is_set():
                    break
                frame = self._pending_frame
                self._pending_frame = None

            if frame is not None:
                try:
                    res = self.process(frame)
                    with self._lock:
                        self._latest_results = res
                except Exception as e:
                    logger.error(f"Error in persistent YOLO worker loop: {e}", exc_info=True)

    def process(self, frame: np.ndarray) -> Dict[str, DetectorResult]:
        """
        Process a frame and return standard DetectorResult dict:
        {
            "person":     DetectorResult,
            "cell_phone": DetectorResult,
            "book":       DetectorResult
        }
        """
        empty = self._get_empty_results()

        if frame is None or frame.size == 0:
            return empty

        try:
            out = self.pipeline.process(frame)
        except Exception as e:
            logger.error(f"ObjectDetectionPipeline.process() failed: {e}", exc_info=True)
            return empty

        persons      = out.get("persons",     [])
        phone_tracks = out.get("phones",      [])
        book_tracks  = out.get("books",       [])
        phone_state  = out.get("phone_state", {})
        book_state   = out.get("book_state",  {})
        latency      = out.get("latency_ms",  0.0)

        # ── 1. Person result ─────────────────────────────────────────────────
        p_count   = len(persons)
        p_max_conf = max((p["confidence"] for p in persons), default=0.0)
        is_multi  = p_count > 1
        p_state   = config.STATE_MULTIPLE_PEOPLE if is_multi else config.STATE_NORMAL

        person_res = DetectorResult(
            detector_name="PersonDetector",
            state=p_state,
            similarity_score=round(p_max_conf, 2),
            verified=not is_multi,
            bounding_box=persons[0]["bbox"] if p_count > 0 else None,
            message=(f"Multiple people detected (Count: {p_count})"
                     if is_multi else f"{p_count} person(s) detected"),
            raw_data={
                "person_count": p_count,
                "max_confidence": round(p_max_conf, 2),
                # Keep same format so _draw_diagnostics can render cyan person boxes
                "detections": [
                    {
                        "type": "person",
                        "bbox": p["bbox"],
                        "confidence": p["confidence"],
                        "source": p.get("source", "yolo11"),
                        "frame_id": out.get("frame_id", 0),
                        "timestamp": 0.0,
                        "person_id": i + 1,
                        "hand_proximity": 0.0,
                        "track_id": p.get("id"),
                        "metadata": {}
                    }
                    for i, p in enumerate(persons)
                ]
            }
        )

        # ── 2. Book result ────────────────────────────────────────────────────
        b_count    = len(book_tracks)
        b_max_conf = max((b["confidence"] for b in book_tracks), default=0.0)
        b_confirmed = book_state.get("confirmed", False)
        b_state     = config.STATE_BOOK_DETECTED if b_confirmed else config.STATE_NORMAL

        book_res = DetectorResult(
            detector_name="BookDetector",
            state=b_state,
            similarity_score=round(b_max_conf, 2),
            verified=not b_confirmed,
            bounding_box=book_tracks[0]["bbox"] if b_count > 0 else None,
            message=(f"Book/material detected (Count: {b_count})"
                     if b_count > 0 else "No book detected"),
            raw_data={
                "book_count": b_count,
                "max_confidence": round(b_max_conf, 2),
                "detections": [
                    {
                        "type": "book",
                        "bbox": b["bbox"],
                        "confidence": b["confidence"],
                        "source": b.get("source", "yolo11"),
                        "frame_id": out.get("frame_id", 0),
                        "timestamp": 0.0,
                        "person_id": None,
                        "hand_proximity": 0.0,
                        "track_id": b.get("id"),
                        "metadata": {}
                    }
                    for b in book_tracks
                ]
            }
        )

        # ── 3. Phone result ───────────────────────────────────────────────────
        ph_confirmed = phone_state.get("confirmed", False)
        ph_score     = phone_state.get("score",     0.0)
        ph_pos       = phone_state.get("positive_frames", 0)
        ph_win       = phone_state.get("window_size",     0)
        ph_state_val = config.STATE_PHONE_DETECTED if ph_confirmed else config.STATE_NORMAL
        max_ph_conf  = max((t["confidence"] for t in phone_tracks), default=0.0)

        if ph_confirmed:
            ph_msg = (f"Mobile phone detected "
                      f"(Count: {len(phone_tracks)}, "
                      f"Conf: {max_ph_conf:.2f}, "
                      f"Frames: {ph_pos}/{ph_win})")
        elif phone_tracks:
            ph_msg = (f"Phone suspected "
                      f"({ph_pos}/{ph_win} frames, Conf: {max_ph_conf:.2f})")
        else:
            ph_msg = "No phone detected"

        # Build detections list in the format _draw_diagnostics expects
        phone_detections = [
            {
                "type": "phone",
                "bbox": t["bbox"],
                "confidence": t["confidence"],
                "source": t.get("source", "yolo11"),
                "frame_id": out.get("frame_id", 0),
                "timestamp": 0.0,
                "person_id": None,
                "hand_proximity": 0.0,
                "track_id": t.get("id"),
                "state": "PHONE_CONFIRMED" if ph_confirmed else "PHONE_CANDIDATE",
                "positive_count": t.get("hits", 1),
                "metadata": {}
            }
            for t in phone_tracks
        ]

        phone_res = DetectorResult(
            detector_name="PhoneDetector",
            state=ph_state_val,
            similarity_score=round(max(max_ph_conf, ph_score), 2),
            verified=not ph_confirmed,
            bounding_box=phone_tracks[0]["bbox"] if phone_tracks else None,
            message=ph_msg,
            raw_data={
                "count":          len(phone_tracks),
                "max_confidence": round(max_ph_conf, 2),
                "confidence":     round(ph_score, 2),
                "detections":     phone_detections,
                "all_tracks":     phone_tracks,
                "confirmed_tracks": phone_tracks if ph_confirmed else [],
                "roi_box":        None,
                "pipeline_state": "PHONE_CONFIRMED" if ph_confirmed else (
                                  "PHONE_CANDIDATE" if phone_tracks else "NO_PHONE"),
                "final_score":    round(max_ph_conf, 2),
                "telemetry": {
                    "full_frame_ms":  latency,
                    "roi_ms":         0.0,
                    "sahi_ms":        0.0,
                    "tracking_ms":    0.0,
                    "total_ms":       latency,
                    "fps":            round(1000.0 / max(1.0, latency), 1),
                    "sahi_triggered": False
                }
            }
        )

        results = {
            "person":     person_res,
            "cell_phone": phone_res,
            "book":       book_res
        }
        with self._lock:
            self._latest_results = results
        self._is_ready.set()

        return results
