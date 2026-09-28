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
    Includes robust Windows multi-backend opening retries and fallback simulated frames.
    """

    def __init__(self, camera_index: int = 0, width: int = 1280, height: int = 720):
        self.camera_index = camera_index
        self.width = width
        self.height = height

        self.cap: Optional[cv2.VideoCapture] = None
        self.latest_frame: Optional[np.ndarray] = None
        self.stopped: bool = True
        self.is_synthetic: bool = False
        self.lock = threading.Lock()
        self.thread: Optional[threading.Thread] = None

    def _generate_fallback_frame(self, message: str = "Webcam Initializing...") -> np.ndarray:
        """Generates an aesthetic diagnostic frame when hardware capture is establishing."""
        f = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        # Deep dark blue background
        cv2.rectangle(f, (0, 0), (self.width, self.height), (22, 28, 42), -1)
        # Grid line accents
        for y in range(0, self.height, 60):
            cv2.line(f, (0, y), (self.width, y), (30, 38, 58), 1)
        for x in range(0, self.width, 60):
            cv2.line(f, (x, 0), (x, self.height), (30, 38, 58), 1)

        # Center card
        cx, cy = self.width // 2, self.height // 2
        card_w, card_h = min(680, self.width - 40), min(220, self.height - 40)
        cv2.rectangle(f, (cx - card_w // 2, cy - card_h // 2), (cx + card_w // 2, cy + card_h // 2), (36, 46, 70), -1)
        cv2.rectangle(f, (cx - card_w // 2, cy - card_h // 2), (cx + card_w // 2, cy + card_h // 2), (59, 130, 246), 2)

        # Live status header
        timestamp = time.strftime("%H:%M:%S")
        cv2.putText(f, "AI PROCTOR MONITOR - LIVE FEED", (cx - card_w // 2 + 25, cy - 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.75, (56, 189, 248), 2)
        cv2.putText(f, f"Status: {message} [{timestamp}]", (cx - card_w // 2 + 25, cy + 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (241, 245, 249), 1)
        cv2.putText(f, f"Device Index: {self.camera_index} | Resolution: {self.width}x{self.height}",
                    (cx - card_w // 2 + 25, cy + 55), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (148, 163, 184), 1)
        return f

    def start(self) -> bool:
        """
        Initializes the video capture device with retries and starts the background capture thread.
        Always starts capture thread so downstream consumers and MJPEG streams stay alive.
        """
        if not self.stopped:
            logger.warning("Camera is already running.")
            return True

        # Candidate backends to attempt on Windows
        backends = [
            (cv2.CAP_DSHOW, "DirectShow"),
            (cv2.CAP_MSMF, "MediaFoundation"),
            (cv2.CAP_ANY, "DefaultBackend")
        ]

        opened = False
        # Retry up to 4 attempts with short backoff (e.g. while browser is releasing webcam)
        for attempt in range(1, 5):
            for backend_flag, backend_name in backends:
                try:
                    cap = cv2.VideoCapture(self.camera_index, backend_flag)
                    if cap.isOpened():
                        # Set resolution
                        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                        # Warm-up reads
                        success_read = False
                        for _ in range(5):
                            ret, test_frame = cap.read()
                            if ret and test_frame is not None and test_frame.size > 0:
                                success_read = True
                                with self.lock:
                                    self.latest_frame = test_frame
                                break
                            time.sleep(0.04)

                        if success_read:
                            self.cap = cap
                            self.is_synthetic = False
                            opened = True
                            logger.info(f"Webcam opened via {backend_name} on attempt {attempt}.")
                            break
                        else:
                            cap.release()
                except Exception as e:
                    logger.debug(f"Error opening camera with {backend_name}: {e}")

            if opened:
                break
            time.sleep(0.35)

        if not opened:
            logger.warning(
                f"Webcam at index {self.camera_index} in use or unavailable. "
                f"Initializing synthetic fallback video stream."
            )
            self.is_synthetic = True
            with self.lock:
                self.latest_frame = self._generate_fallback_frame("Hardware Camera In Use - Standby")

        self.stopped = False
        self.thread = threading.Thread(target=self._update_loop, daemon=True)
        self.thread.start()
        return True

    def _update_loop(self):
        """Continuous frame grab loop running in background daemon thread."""
        consecutive_read_failures = 0

        while not self.stopped:
            if not self.is_synthetic and self.cap and self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret and frame is not None and frame.size > 0:
                    consecutive_read_failures = 0
                    with self.lock:
                        self.latest_frame = frame
                else:
                    consecutive_read_failures += 1
                    time.sleep(0.02)

                    # If too many consecutive failures, switch to fallback frame briefly
                    if consecutive_read_failures > 30:
                        with self.lock:
                            self.latest_frame = self._generate_fallback_frame("Re-syncing Camera Stream...")
            else:
                # Synthetic animated fallback loop
                with self.lock:
                    self.latest_frame = self._generate_fallback_frame("Camera Standby (Device Held By Browser/System)")
                time.sleep(0.05)

    def get_frame(self) -> Optional[np.ndarray]:
        """Returns a copy of the latest captured frame."""
        with self.lock:
            if self.latest_frame is None:
                return self._generate_fallback_frame("Initializing Frame...")
            return self.latest_frame.copy()

    def is_running(self) -> bool:
        """Checks if camera manager is active."""
        return not self.stopped

    def stop(self):
        """Stops capture thread and releases webcam hardware resources safely."""
        self.stopped = True
        if self.thread is not None and self.thread.is_alive():
            self.thread.join(timeout=1.0)

        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
        logger.info("Webcam released.")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

