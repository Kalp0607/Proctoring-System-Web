import logging
import math
from typing import List, Tuple, Dict, Any, Optional
import numpy as np

from detectors.object_detection.schema import Detection, TrackedObject
from detectors.object_detection.person_detector import compute_iou
from detectors.object_detection.config import PhoneConfig

logger = logging.getLogger(__name__)


class ObjectTracker:
    """
    Lightweight Multi-Object Tracker with centroid distance gating, IoU association,
    exponential bbox smoothing, and dropout tolerance.
    """

    def __init__(self, config: PhoneConfig):
        self.config = config
        self.active_tracks: List[TrackedObject] = []
        self.next_track_id: int = 1

    def update(self, detections: List[Detection]) -> List[TrackedObject]:
        """
        Associates detections with active tracks and updates track state.
        Returns list of currently active confirmed/suspected tracks.
        """
        unmatched_dets = list(detections)
        matched_track_ids = set()

        # Step 1: Match detections to active tracks
        for track in self.active_tracks:
            best_det = None
            best_score = -1.0
            best_idx = -1

            tx, ty = track.center

            for idx, det in enumerate(unmatched_dets):
                dx, dy = det.center
                center_dist = math.hypot(tx - dx, ty - dy)
                
                # Spatial gating: reject sudden impossible jumps
                if center_dist > self.config.track_center_dist_threshold:
                    continue

                iou = compute_iou(track.bbox, det.bbox)
                
                # Combined association metric
                match_score = iou * 0.6 + max(0.0, 1.0 - (center_dist / self.config.track_center_dist_threshold)) * 0.4
                if match_score > best_score and (iou >= self.config.track_iou_threshold or center_dist < 40.0):
                    best_score = match_score
                    best_det = det
                    best_idx = idx

            if best_det is not None:
                track.update(best_det)
                best_det.track_id = track.track_id
                matched_track_ids.add(track.track_id)
                unmatched_dets.pop(best_idx)
            else:
                track.mark_missed()

        # Step 2: Create new tracks for remaining unmatched detections
        for det in unmatched_dets:
            new_track = TrackedObject(
                track_id=self.next_track_id,
                object_type=det.type,
                bbox=det.bbox,
                confidence=det.confidence,
                source=det.source,
                person_id=det.person_id,
                hand_proximity=det.hand_proximity,
                positive_count=1,
                total_age=1,
                missed_frames=0
            )
            self.next_track_id += 1
            det.track_id = new_track.track_id
            self.active_tracks.append(new_track)

        # Step 3: Remove expired tracks (missed > track_max_age)
        self.active_tracks = [t for t in self.active_tracks if t.missed_frames <= self.config.track_max_age]

        return self.active_tracks
