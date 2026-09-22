from detectors.object_detector import ObjectDetector
from detectors.base_detector import BaseDetector, DetectorResult
import numpy as np


class PersonDetector(BaseDetector):
    """
    Backward-compatibility wrapper for PersonDetector.
    Delegates to unified ObjectDetector.
    """

    def __init__(self, model_name: str = None, confidence_threshold: float = None, device: str = None):
        self.detector_name = "PersonDetector"
        self._shared_obj_detector = ObjectDetector()

    def process(self, frame: np.ndarray) -> DetectorResult:
        results_dict = self._shared_obj_detector.process(frame)
        return results_dict.get("person", DetectorResult(detector_name="PersonDetector", state="NORMAL"))
