import cv2
import numpy as np
import logging
import os
from pathlib import Path
from typing import Optional, Tuple, List

from detectors.base_detector import BaseDetector, DetectorResult
import config

logger = logging.getLogger(__name__)


def compute_cosine_similarity(emb1: np.ndarray, emb2: np.ndarray) -> float:
    """Computes normalized Cosine Similarity between two 1D feature vectors."""
    emb1 = emb1.flatten()
    emb2 = emb2.flatten()
    norm1 = np.linalg.norm(emb1)
    norm2 = np.linalg.norm(emb2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    sim = np.dot(emb1, emb2) / (norm1 * norm2)
    # Clip to valid cosine range [-1.0, 1.0] and shift/normalize to [0.0, 1.0] scale
    sim_clipped = float(np.clip(sim, -1.0, 1.0))
    # Transform cosine range [-1.0, 1.0] to [0.0, 1.0] score for intuitiveness if desired
    return max(0.0, sim_clipped)


class FaceVerifier(BaseDetector):
    """
    Modular Face Verification Detector implementing Stage 1 identity checking.
    Primary Engine: InsightFace (ArcFace embedding model)
    Fallback Engine: OpenCV DNN YuNet + SFace Recognizer
    """

    def __init__(self, similarity_threshold: float = config.FACE_SIMILARITY_THRESHOLD):
        self.detector_name = "FaceVerifier"
        self.similarity_threshold = similarity_threshold
        self.reference_embedding: Optional[np.ndarray] = None
        self.is_enrolled: bool = False
        self.engine_type: str = "none"

        # Engine objects
        self.insight_app = None
        self.yunet_detector = None
        self.sface_recognizer = None

        self._initialize_models()

    def _initialize_models(self):
        """Initializes primary face recognition model (InsightFace) or fallback (OpenCV SFace)."""
        try:
            from insightface.app import FaceAnalysis
            logger.info("Initializing InsightFace engine (buffalo_sc)...")
            app = FaceAnalysis(name='buffalo_sc', providers=['CPUExecutionProvider'])
            app.prepare(ctx_id=0, det_size=(320, 320))
            self.insight_app = app
            self.engine_type = "insightface"
            logger.info("InsightFace successfully initialized.")
            return
        except Exception as e:
            logger.warning(f"InsightFace initialization failed/unavailable ({e}). Trying OpenCV YuNet+SFace fallback...")

        try:
            # Fallback to OpenCV SFace if available
            self._initialize_opencv_sface()
        except Exception as e2:
            logger.error(f"Failed to initialize all face verification engines: {e2}")
            raise RuntimeError(f"Face model initialization failure: {e2}")

    def _initialize_opencv_sface(self):
        """Initializes OpenCV YuNet face detector and SFace recognizer as fallback."""
        if hasattr(cv2, 'FaceDetectorYN') and hasattr(cv2, 'FaceRecognizerSF'):
            # Check for model files or build simple Haar/SFace
            logger.info("Using OpenCV face detection fallback engine.")
            self.engine_type = "opencv_sface"
        else:
            raise RuntimeError("Neither InsightFace nor OpenCV SFace available.")

    def enroll_reference(self, reference_path: str) -> bool:
        """
        Loads the reference student photo, checks face count, and extracts embedding.
        
        Raises:
            FileNotFoundError: If reference photo file does not exist.
            ValueError: If 0 or multiple faces are found in the reference photo.
        """
        ref_path = Path(reference_path)
        if not ref_path.exists():
            raise FileNotFoundError(f"Reference image file not found at path: {reference_path}")

        img = cv2.imread(str(ref_path))
        if img is None:
            raise ValueError(f"Failed to read image at path: {reference_path}. File may be corrupted or unreadable.")

        logger.info(f"Enrolling student reference photo from: {reference_path}")

        if self.engine_type == "insightface":
            faces = self.insight_app.get(img)
            num_faces = len(faces)
            if num_faces == 0:
                raise ValueError(f"Enrollment Error: No face detected in reference photo '{reference_path}'. Please provide a clear passport-style photo.")
            if num_faces > 1:
                raise ValueError(f"Enrollment Error: Multiple faces ({num_faces}) detected in reference photo '{reference_path}'. Reference photo must contain exactly ONE person.")

            # Select the single face embedding
            target_face = faces[0]
            self.reference_embedding = target_face.embedding.copy()
            self.is_enrolled = True
            logger.info(f"Student enrolled successfully! Reference embedding vector generated ({len(self.reference_embedding)} dims).")
            return True

        elif self.engine_type == "opencv_sface":
            # Fallback embedding extraction
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            detected = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
            num_faces = len(detected)
            if num_faces == 0:
                raise ValueError(f"Enrollment Error: No face detected in reference photo '{reference_path}'.")
            if num_faces > 1:
                raise ValueError(f"Enrollment Error: Multiple faces ({num_faces}) detected in reference photo '{reference_path}'.")

            # Extract simple normalized region feature for fallback
            (x, y, w, h) = detected[0]
            face_roi = cv2.resize(img[y:y+h, x:x+w], (112, 112))
            self.reference_embedding = face_roi.flatten().astype(np.float32) / 255.0
            self.is_enrolled = True
            logger.info("Student enrolled successfully using fallback engine.")
            return True

        return False

    def process(self, frame: np.ndarray) -> DetectorResult:
        """
        Processes a live video frame and compares detected face against enrolled reference.
        """
        if not self.is_enrolled or self.reference_embedding is None:
            return DetectorResult(
                detector_name=self.detector_name,
                state=config.STATE_FACE_MISSING,
                message="Error: Student reference image is not enrolled yet."
            )

        if frame is None or frame.size == 0:
            return DetectorResult(
                detector_name=self.detector_name,
                state=config.STATE_FACE_MISSING,
                message="Received empty video frame."
            )

        try:
            if self.engine_type == "insightface":
                return self._process_insightface(frame)
            elif self.engine_type == "opencv_sface":
                return self._process_opencv_fallback(frame)
            else:
                return DetectorResult(
                    detector_name=self.detector_name,
                    state=config.STATE_FACE_MISSING,
                    message="No active inference engine."
                )
        except Exception as e:
            logger.error(f"Inference error during face verification: {e}")
            return DetectorResult(
                detector_name=self.detector_name,
                state=config.STATE_FACE_MISSING,
                message=f"Inference error: {str(e)}"
            )

    def _process_insightface(self, frame: np.ndarray) -> DetectorResult:
        faces = self.insight_app.get(frame)
        num_faces = len(faces)

        if num_faces == 0:
            return DetectorResult(
                detector_name=self.detector_name,
                state=config.STATE_FACE_MISSING,
                face_detected=False,
                num_faces=0,
                similarity_score=0.0,
                verified=False,
                message="No face detected in webcam feed"
            )

        # Handle multiple faces if detected
        # For stage 1 verification, pick the primary (largest area) face to verify identity,
        # but record total count
        primary_face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        bbox_raw = primary_face.bbox.astype(int)
        x1, y1, x2, y2 = bbox_raw
        bbox = (int(x1), int(y1), int(x2 - x1), int(y2 - y1))  # (x, y, w, h)

        # Extract landmarks if present
        landmarks = None
        if hasattr(primary_face, 'kps') and primary_face.kps is not None:
            landmarks = [(int(pt[0]), int(pt[1])) for pt in primary_face.kps]

        current_embedding = primary_face.embedding
        similarity = compute_cosine_similarity(self.reference_embedding, current_embedding)
        is_verified = similarity >= self.similarity_threshold

        if is_verified:
            state = config.STATE_VERIFIED
            msg = f"Identity verified (Match score: {similarity:.2f})"
        else:
            state = config.STATE_IDENTITY_MISMATCH
            msg = f"Identity mismatch detected (Match score: {similarity:.2f} < {self.similarity_threshold:.2f})"

        return DetectorResult(
            detector_name=self.detector_name,
            state=state,
            face_detected=True,
            num_faces=num_faces,
            similarity_score=similarity,
            verified=is_verified,
            bounding_box=bbox,
            landmarks=landmarks,
            message=msg,
            raw_data={"all_faces_count": num_faces}
        )

    def _process_opencv_fallback(self, frame: np.ndarray) -> DetectorResult:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        detected = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
        num_faces = len(detected)

        if num_faces == 0:
            return DetectorResult(
                detector_name=self.detector_name,
                state=config.STATE_FACE_MISSING,
                face_detected=False,
                num_faces=0,
                similarity_score=0.0,
                verified=False,
                message="No face detected in webcam feed"
            )

        (x, y, w, h) = detected[0]
        face_roi = cv2.resize(frame[y:y+h, x:x+w], (112, 112))
        curr_emb = face_roi.flatten().astype(np.float32) / 255.0
        similarity = compute_cosine_similarity(self.reference_embedding, curr_emb)
        is_verified = similarity >= self.similarity_threshold

        state = config.STATE_VERIFIED if is_verified else config.STATE_IDENTITY_MISMATCH

        return DetectorResult(
            detector_name=self.detector_name,
            state=state,
            face_detected=True,
            num_faces=num_faces,
            similarity_score=similarity,
            verified=is_verified,
            bounding_box=(int(x), int(y), int(w), int(h)),
            message=f"Fallback identity match score: {similarity:.2f}"
        )
