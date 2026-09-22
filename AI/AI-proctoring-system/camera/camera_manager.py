import cv2
import threading
import time
import logging
import numpy as np
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class CameraManager:
    """
    Threaded Camera Manager for high-FPS video streaming.
    Decouples webcam frame reading from main thread execution / AI inference.
    """

    def __init__(self, camera_index: int = 0, width: int = 1280, height: int = 720):
        self.camera_index = camera_index
        self.width = width
        self.height = height

        self.cap: Optional[cv2.VideoCapture] = None
        self.latest_frame: Optional[np.ndarray] = None
        self.stopped: bool = True
        self.lock = threading.Lock()
        self.thread: Optional[threading.Thread] = None

    def start(self) -> bool:
        """
        Initializes the video capture device and starts the background capture thread.
        Returns True if successful, False if camera fails to open.
        """
        if not self.stopped:
            logger.warning("Camera is already running.")
            return True

        # Use CAP_DSHOW on Windows for fast webcam initialization if needed, or default backend
        self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            logger.warning("Failed to open camera with CAP_DSHOW, retrying with default backend...")
            self.cap = cv2.VideoCapture(self.camera_index)

        if not self.cap.isOpened():
            logger.error(f"Cannot access webcam at index {self.camera_index}.")
            return False

        # Set camera parameters
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        # Read initial frames to warm up webcam auto-exposure and gain
        for _ in range(10):
            self.cap.read()
            time.sleep(0.02)

        ret, frame = self.cap.read()
        if not ret or frame is None:
            logger.error("Opened camera but failed to read initial frame.")
            self.cap.release()
            return False

        with self.lock:
            self.latest_frame = frame

        self.stopped = False
        self.thread = threading.Thread(target=self._update_loop, daemon=True)
        self.thread.start()
        logger.info(f"Webcam {self.camera_index} started successfully.")
        return True

    def _update_loop(self):
        """Continuous frame grab loop running in background daemon thread."""
        while not self.stopped and self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret or frame is None:
                logger.warning("Failed to capture frame from webcam stream.")
                time.sleep(0.01)
                continue

            with self.lock:
                self.latest_frame = frame

    def get_frame(self) -> Optional[np.ndarray]:
        """Returns a copy of the latest captured frame."""
        with self.lock:
            if self.latest_frame is None:
                return None
            return self.latest_frame.copy()

    def is_running(self) -> bool:
        """Checks if camera thread is active."""
        return not self.stopped and self.cap is not None and self.cap.isOpened()

    def stop(self):
        """Stops capture thread and releases webcam hardware resources safely."""
        self.stopped = True
        if self.thread is not None and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        logger.info("Webcam released.")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
