"""
object_detector.py — Adapter between ObjectDetectionPipeline and the proctoring pipeline.

Wraps the clean YOLO11-based ObjectDetectionPipeline and converts its output
into the standard DetectorResult dict that main.py and violation_manager expect.
"""

import logging
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
                 device: str = None):

        model_name = model_name or getattr(config, "YOLO_MODEL", "yolo11s.pt")
        img_size   = img_size   or getattr(config, "YOLO_IMAGE_SIZE", 640)
        device     = device     or getattr(config, "DEVICE", "cpu")

        phone_cfg  = getattr(config, "PHONE_DETECTION_CONFIG", {})

        pipeline_config = {
            # Confidence thresholds
            "person_conf":     getattr(config, "PERSON_CONFIDENCE_THRESHOLD", 0.45),
            "phone_conf":      phone_cfg.get("candidate_confidence", 0.20),
            "book_conf":       getattr(config, "BOOK_CONFIDENCE_THRESHOLD", 0.35),

            # Temporal windows
            "phone_window":    phone_cfg.get("temporal_window",   8),
            "phone_min_pos":   phone_cfg.get("min_positive_frames", 3),
            "book_window":     6,
            "book_min_pos":    2,

            # Inference settings
            "imgsz":           img_size,
            "device":          device,

            # Geometry filters
            "min_person_area": getattr(config, "MIN_PERSON_BOX_AREA", 0.02),
            "max_phone_area":  0.50,
        }

        self.pipeline = ObjectDetectionPipeline(
            yolo_model_path=model_name,
            config=pipeline_config
        )
        self.detector_name = "ObjectDetector"
        logger.info("ObjectDetector (clean YOLO11 pipeline) initialized successfully.")

    def process(self, frame: np.ndarray) -> Dict[str, DetectorResult]:
        """
        Process a frame and return standard DetectorResult dict:
        {
            "person":     DetectorResult,
            "cell_phone": DetectorResult,
            "book":       DetectorResult
        }
        """
        empty = {
            "person":     DetectorResult(detector_name="PersonDetector",
                                         state=config.STATE_NORMAL, message="No person detected"),
            "cell_phone": DetectorResult(detector_name="PhoneDetector",
                                         state=config.STATE_NORMAL, message="No phone detected"),
            "book":       DetectorResult(detector_name="BookDetector",
                                         state=config.STATE_NORMAL, message="No book detected"),
        }

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

        return {
            "person":     person_res,
            "cell_phone": phone_res,
            "book":       book_res
        }
