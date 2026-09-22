from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Tuple, Dict, Any, List
import numpy as np


@dataclass
class DetectorResult:
    """
    Standardized result structure returned by all proctoring AI detectors.
    """
    detector_name: str
    state: str                             # VERIFIED, IDENTITY_MISMATCH, FACE_MISSING, MULTIPLE_FACES, etc.
    face_detected: bool = False
    num_faces: int = 0
    similarity_score: float = 0.0          # Range 0.0 to 1.0
    verified: bool = False
    bounding_box: Optional[Tuple[int, int, int, int]] = None  # (x, y, w, h)
    landmarks: Optional[List[Tuple[int, int]]] = None
    message: str = ""
    raw_data: Dict[str, Any] = field(default_factory=dict)     # Extensible payload for future features


class BaseDetector(ABC):
    """
    Abstract Base Class for modular AI detectors in the proctoring pipeline.
    """

    @abstractmethod
    def process(self, frame: np.ndarray) -> DetectorResult:
        """
        Process a single image frame and return structured detection results.
        
        Args:
            frame: BGR numpy image frame from video feed.
            
        Returns:
            DetectorResult object containing detection status, scores, and bounding boxes.
        """
        pass
