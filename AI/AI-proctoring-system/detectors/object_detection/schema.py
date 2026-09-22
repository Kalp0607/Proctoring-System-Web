from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any
import time


@dataclass
class Detection:
    """
    Standard normalized detection output across all object types and detection sources.
    """
    type: str                                  # "person", "phone", "book"
    bbox: Tuple[int, int, int, int]           # (x, y, w, h) in original full-frame pixel coordinates
    confidence: float                          # Range 0.0 to 1.0
    source: str                                # "yolo11", "sentinel_full", "sentinel_roi", "sentinel_sahi"
    frame_id: int = 0
    timestamp: float = field(default_factory=time.time)
    person_id: Optional[int] = None           # Associated person ID if applicable
    hand_proximity: float = 0.0                # Range 0.0 to 1.0
    track_id: Optional[int] = None             # Assigned tracking ID
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def x1(self) -> int:
        return self.bbox[0]

    @property
    def y1(self) -> int:
        return self.bbox[1]

    @property
    def x2(self) -> int:
        return self.bbox[0] + self.bbox[2]

    @property
    def y2(self) -> int:
        return self.bbox[1] + self.bbox[3]

    @property
    def center(self) -> Tuple[float, float]:
        return (self.bbox[0] + self.bbox[2] / 2.0, self.bbox[1] + self.bbox[3] / 2.0)

    @property
    def area(self) -> int:
        return self.bbox[2] * self.bbox[3]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "bbox": list(self.bbox),
            "confidence": round(float(self.confidence), 2),
            "source": self.source,
            "frame_id": self.frame_id,
            "timestamp": self.timestamp,
            "person_id": self.person_id,
            "hand_proximity": round(float(self.hand_proximity), 2),
            "track_id": self.track_id,
            "metadata": self.metadata
        }


@dataclass
class TrackedObject:
    """
    Represents an object track across consecutive video frames.
    """
    track_id: int
    object_type: str                           # "phone", "person", "book"
    bbox: Tuple[int, int, int, int]           # (x, y, w, h)
    confidence: float
    source: str
    state: str = "CANDIDATE"                  # "CANDIDATE", "CONFIRMED", "LOST"
    person_id: Optional[int] = None
    hand_proximity: float = 0.0
    positive_count: int = 1
    total_age: int = 1
    missed_frames: int = 0
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    history: List[Tuple[int, int, int, int]] = field(default_factory=list)
    scores_history: List[float] = field(default_factory=list)

    @property
    def center(self) -> Tuple[float, float]:
        return (self.bbox[0] + self.bbox[2] / 2.0, self.bbox[1] + self.bbox[3] / 2.0)

    def update(self, detection: Detection):
        # Exponential moving average for smooth bounding box
        alpha = 0.70
        curr_x, curr_y, curr_w, curr_h = self.bbox
        det_x, det_y, det_w, det_h = detection.bbox
        
        smooth_x = int(alpha * det_x + (1.0 - alpha) * curr_x)
        smooth_y = int(alpha * det_y + (1.0 - alpha) * curr_y)
        smooth_w = int(alpha * det_w + (1.0 - alpha) * curr_w)
        smooth_h = int(alpha * det_h + (1.0 - alpha) * curr_h)

        self.bbox = (smooth_x, smooth_y, smooth_w, smooth_h)
        self.confidence = max(self.confidence * 0.3 + detection.confidence * 0.7, detection.confidence)
        self.source = detection.source
        self.hand_proximity = detection.hand_proximity
        if detection.person_id is not None:
            self.person_id = detection.person_id
            
        self.positive_count += 1
        self.missed_frames = 0
        self.last_seen = time.time()
        self.history.append(self.bbox)
        if len(self.history) > 30:
            self.history.pop(0)
        self.scores_history.append(detection.confidence)
        if len(self.scores_history) > 30:
            self.scores_history.pop(0)

    def mark_missed(self):
        self.missed_frames += 1
        self.total_age += 1


@dataclass
class TelemetryData:
    full_frame_ms: float = 0.0
    roi_ms: float = 0.0
    sahi_ms: float = 0.0
    sahi_triggered: bool = False
    tracking_ms: float = 0.0
    total_ms: float = 0.0
    fps: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "full_frame_ms": round(self.full_frame_ms, 1),
            "roi_ms": round(self.roi_ms, 1),
            "sahi_ms": round(self.sahi_ms, 1),
            "sahi_triggered": self.sahi_triggered,
            "tracking_ms": round(self.tracking_ms, 1),
            "total_ms": round(self.total_ms, 1),
            "fps": round(self.fps, 1)
        }
