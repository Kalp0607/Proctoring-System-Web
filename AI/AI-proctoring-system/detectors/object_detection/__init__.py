"""
Object Detection Package
Clean YOLO11-based pipeline: person, phone (cls=67), book detection.
"""

from detectors.object_detection.pipeline import ObjectDetectionPipeline

__all__ = [
    "ObjectDetectionPipeline",
]
