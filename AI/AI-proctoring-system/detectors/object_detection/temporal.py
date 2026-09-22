import logging
from typing import List, Dict, Any, Optional
from collections import deque
import numpy as np

from detectors.object_detection.schema import TrackedObject
from detectors.object_detection.config import PhoneConfig

logger = logging.getLogger(__name__)


class TemporalEvidenceAccumulator:
    """
    Accumulates temporal evidence across rolling frame windows to prevent false positives from single-frame noise.
    Computes a composite Final Evidence Score.
    """

    def __init__(self, config: PhoneConfig):
        self.config = config
        self.window_size = config.temporal_window
        self.min_positive = config.min_positive_frames
        # Rolling frame detection history: deque of booleans
        self.history: deque = deque(maxlen=self.window_size)
        self.scores_history: deque = deque(maxlen=self.window_size)

    def update(self, active_tracks: List[TrackedObject]) -> Dict[str, Any]:
        """
        Updates temporal history and evaluates composite evidence score.
        
        Formula:
            FINAL_SCORE = 0.45 * max_conf + 0.30 * persistence_ratio + 0.15 * track_stability + 0.10 * hand_prox
        """
        has_positive = any(t.missed_frames == 0 and t.confidence >= self.config.candidate_confidence for t in active_tracks)
        
        max_conf = max([t.confidence for t in active_tracks if t.missed_frames == 0], default=0.0)
        max_hand_prox = max([t.hand_proximity for t in active_tracks if t.missed_frames == 0], default=0.0)
        max_hits = max([t.positive_count for t in active_tracks], default=0)

        self.history.append(has_positive)
        self.scores_history.append(max_conf)

        positive_count = sum(1 for h in self.history if h)
        persistence_ratio = positive_count / float(max(1, len(self.history)))
        track_stability = min(1.0, max_hits / 5.0)

        final_score = (
            0.45 * max_conf +
            0.30 * persistence_ratio +
            0.15 * track_stability +
            0.10 * max_hand_prox
        )
        final_score = round(float(final_score), 2)

        is_confirmed = (positive_count >= self.min_positive and max_conf >= self.config.violation_confidence) or (positive_count >= 2 and max_conf >= 0.70)
        is_candidate = (positive_count >= 1 and max_conf >= self.config.candidate_confidence)

        return {
            "is_confirmed": is_confirmed,
            "is_candidate": is_candidate,
            "final_score": final_score,
            "positive_count": positive_count,
            "window_len": len(self.history),
            "max_confidence": round(max_conf, 2),
            "persistence_ratio": round(persistence_ratio, 2)
        }
