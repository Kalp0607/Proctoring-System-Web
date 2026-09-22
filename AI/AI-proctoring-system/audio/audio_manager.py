import sounddevice as sd
import numpy as np
import threading
import logging
import time
from collections import deque
from typing import Optional, Tuple

import config

logger = logging.getLogger(__name__)


class AudioManager:
    """
    Threaded Live Microphone Audio Manager.
    Captures live microphone PCM audio stream into a thread-safe circular memory buffer.
    Buffers up to SPEAKER_ANALYSIS_WINDOW_SECONDS (30.0s) of 16kHz mono audio in RAM.
    Does NOT save continuous audio or WAV files to disk.
    """

    def __init__(self, sample_rate: int = config.AUDIO_SAMPLE_RATE,
                 buffer_duration: float = config.DIARIZATION_WINDOW_SECONDS):
        self.sample_rate = sample_rate
        self.buffer_duration = buffer_duration
        self.max_samples = int(sample_rate * buffer_duration)

        self.audio_buffer = deque(maxlen=self.max_samples)
        self.lock = threading.Lock()

        self.stream = None
        self.is_running = False
        self.is_available = False
        self.error_message = ""

    def start(self) -> bool:
        """Starts live microphone input stream."""
        if not config.AUDIO_ENABLED:
            logger.info("Audio monitoring disabled in config.")
            return False

        try:
            logger.info(f"Initializing live microphone audio stream ({self.sample_rate}Hz, mono)...")
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=config.AUDIO_CHANNELS,
                dtype='float32',
                blocksize=config.AUDIO_CHUNK_SIZE,
                callback=self._audio_callback
            )
            self.stream.start()
            self.is_running = True
            self.is_available = True
            logger.info("Live microphone audio monitoring started successfully.")
            return True
        except Exception as e:
            self.is_running = False
            self.is_available = False
            self.error_message = str(e)
            logger.warning(f"Microphone initialization failed/unavailable: {e}")
            return False

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status):
        """Callback function executed on audio hardware thread."""
        if status:
            logger.debug(f"Audio stream status: {status}")
        
        samples = indata[:, 0]
        with self.lock:
            self.audio_buffer.extend(samples)

    def get_recent_audio(self, duration_sec: Optional[float] = None) -> np.ndarray:
        """
        Returns recent recorded PCM float32 audio samples from memory buffer.
        """
        with self.lock:
            if not self.audio_buffer:
                return np.array([], dtype=np.float32)

            samples = np.array(self.audio_buffer, dtype=np.float32)

        if duration_sec and duration_sec > 0:
            num_samples = int(self.sample_rate * duration_sec)
            if len(samples) > num_samples:
                samples = samples[-num_samples:]

        return samples

    def get_latest_chunk(self, chunk_sec: float = 1.0) -> np.ndarray:
        """Returns the most recent N seconds of audio samples."""
        return self.get_recent_audio(duration_sec=chunk_sec)

    def stop(self):
        """Stops audio stream cleanly."""
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
                logger.info("Microphone audio stream stopped.")
            except Exception as e:
                logger.error(f"Error stopping audio stream: {e}")
        self.is_running = False
