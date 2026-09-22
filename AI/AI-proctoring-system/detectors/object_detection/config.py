from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from pathlib import Path


@dataclass
class PersonConfig:
    confidence: float = 0.60
    imgsz: int = 640
    min_area_ratio: float = 0.03
    iou_nms_threshold: float = 0.40
    max_containment_ratio: float = 0.50


@dataclass
class ROIConfig:
    padding_x: float = 0.20
    padding_y: float = 0.20
    min_width: int = 64
    min_height: int = 64


@dataclass
class PhoneConfig:
    candidate_confidence: float = 0.15    # Lowered from 0.22: catch low-conf Sentinel detections
    violation_confidence: float = 0.35
    full_frame_imgsz: int = 640
    roi_imgsz: int = 640
    temporal_window: int = 8
    min_positive_frames: int = 4
    cooldown_seconds: float = 3.0
    tracking_enabled: bool = True
    track_max_age: int = 8              # Increased from 5: retain tracks through confidence dips
    track_iou_threshold: float = 0.25
    track_center_dist_threshold: float = 120.0  # Increased from 90: allow more phone movement
    # Geometry Constraints
    min_pixel_area: int = 200           # Lowered from 250
    max_area_ratio: float = 0.30        # Increased from 0.25
    max_width_ratio: float = 0.65       # Increased from 0.60
    max_height_ratio: float = 0.80      # Increased from 0.75
    min_aspect_ratio: float = 0.8       # Lowered from 1.0: allow landscape-held phones
    max_aspect_ratio: float = 6.0       # Increased from 5.0
    # Static Background Suppression
    static_consecutive_cycles: int = 8  # Increased from 6
    static_iou_threshold: float = 0.50  # Increased from 0.40


@dataclass
class BookConfig:
    confidence: float = 0.40
    imgsz: int = 640
    temporal_window: int = 5
    min_positive_frames: int = 3


@dataclass
class SAHIConfig:
    enabled: bool = True
    slice_size: int = 384
    overlap: float = 0.30               # Increased from 0.25 for better edge coverage
    trigger_min_conf: float = 0.10      # Lowered from 0.18: trigger on very low-conf candidates
    trigger_max_conf: float = 0.40
    min_person_area_ratio: float = 0.15


@dataclass
class HandContextConfig:
    enabled: bool = True
    proximity_radius: int = 160
    proximity_boost: float = 0.15
    detection_confidence: float = 0.40


@dataclass
class DetectionPipelineConfig:
    device: str = "cpu"
    # Model Paths
    person_model_path: str = "yolo11s.pt"
    book_model_path: str = "yolo11s.pt"
    phone_model_path: str = "models/sentinelvision_yolov8n.pt"
    
    person: PersonConfig = field(default_factory=PersonConfig)
    roi: ROIConfig = field(default_factory=ROIConfig)
    phone: PhoneConfig = field(default_factory=PhoneConfig)
    book: BookConfig = field(default_factory=BookConfig)
    sahi: SAHIConfig = field(default_factory=SAHIConfig)
    hand: HandContextConfig = field(default_factory=HandContextConfig)


# Default global instance
DEFAULT_DETECTION_CONFIG = DetectionPipelineConfig()
