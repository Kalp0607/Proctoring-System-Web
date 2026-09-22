import numpy as np
import scipy.signal as signal
try:
    from sklearn.cluster import AgglomerativeClustering
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    from scipy.spatial.distance import pdist
    from scipy.cluster.hierarchy import linkage, fcluster
import logging
import time
from collections import deque
from typing import Optional, List, Dict, Any, Tuple

from detectors.base_detector import BaseDetector, DetectorResult
import config

logger = logging.getLogger(__name__)


class SpeakerDiarizationTurn:
    """Represents a speaker-labelled turn segment within the rolling diarization window."""

    def __init__(self, start_sec: float, end_sec: float, speaker_label: str):
        self.start_sec = start_sec
        self.end_sec = end_sec
        self.duration = round(end_sec - start_sec, 1)
        self.speaker_label = speaker_label


class SpeakerDetector(BaseDetector):
    """
    Stage 5 Production-Grade 20-Second Rolling Speaker Diarization Engine.
    Performs speech turn segmentation, 1.0s sub-window sampling with 0.25s hop, 128D Mel-spectral & pitch F0 feature embedding extraction,
    Agglomerative Hierarchical Clustering (Cosine Distance threshold = 0.22), minimum credible speaker duration filtering (>= 1.0s),
    and multi-window temporal confirmation.
    """

    def __init__(self, sample_rate: int = config.AUDIO_SAMPLE_RATE):
        self.detector_name = "SpeakerDetector"
        self.sample_rate = sample_rate

        # Multi-window confirmation tracker (requires 2 consecutive windows indicating 2+ credible speakers)
        self.confirmation_history = deque(maxlen=config.MULTIPLE_SPEAKER_CONFIRM_WINDOWS)

        # Last analysis results for UI feedback
        self.last_diarization_time: float = 0.0
        self.last_credible_count: int = 0
        self.last_speaker_durations: Dict[str, float] = {}
        self.last_turns: List[SpeakerDiarizationTurn] = []
        self.is_analyzing: bool = False

    def extract_subwindow_embedding(self, pcm_chunk: np.ndarray) -> np.ndarray:
        """
        Extracts a 128-dimensional L2-normalized Mel-spectral cepstral & pitch F0 embedding vector.
        Captures fundamental pitch frequency, formant harmonics, and vocal tract timbre.
        """
        if len(pcm_chunk) < int(self.sample_rate * 0.15):  # Min 150ms
            return np.zeros(128, dtype=np.float32)

        # 1. Compute STFT Spectrogram (25ms window, 10ms hop)
        nperseg = int(self.sample_rate * 0.025)
        noverlap = int(self.sample_rate * 0.015)
        f, t, Sxx = signal.spectrogram(pcm_chunk, fs=self.sample_rate, nperseg=nperseg, noverlap=noverlap)

        log_spec = np.log(Sxx + 1e-6)

        # 2. Extract 32 Mel-frequency band energy means & stds (64D)
        num_bands = 32
        freq_bins = log_spec.shape[0]
        band_size = max(1, freq_bins // num_bands)
        
        band_means = []
        band_stds = []
        for i in range(num_bands):
            idx_start = i * band_size
            idx_end = min((i + 1) * band_size, freq_bins)
            sub_band = log_spec[idx_start:idx_end, :]
            band_means.append(float(np.mean(sub_band)))
            band_stds.append(float(np.std(sub_band)))

        # 3. Fundamental Pitch Frequency (F0) Estimation via Autocorrelation
        corr = signal.correlate(pcm_chunk, pcm_chunk, mode='full')
        corr = corr[len(corr)//2:]
        min_lag = int(self.sample_rate / 350)
        max_lag = int(self.sample_rate / 70)
        
        if max_lag < len(corr):
            pitch_lag = min_lag + int(np.argmax(corr[min_lag:max_lag]))
            pitch_f0 = float(self.sample_rate / pitch_lag) if pitch_lag > 0 else 0.0
        else:
            pitch_f0 = 0.0

        # Pitch feature vector (32D)
        pitch_vector = [pitch_f0 / 350.0, float(np.mean(corr[:100]) / (np.max(corr) + 1e-6))] * 32

        # Combine into 128D feature embedding
        raw_embedding = np.array(band_means + band_stds + pitch_vector, dtype=np.float32)

        # Z-score normalization per sub-window
        emb_std = float(np.std(raw_embedding))
        if emb_std > 0:
            raw_embedding = (raw_embedding - np.mean(raw_embedding)) / emb_std

        # Final L2 Normalization
        norm = float(np.linalg.norm(raw_embedding))
        if norm > 0:
            raw_embedding = raw_embedding / norm

        return raw_embedding

    def run_diarization(self, pcm_20s_audio: np.ndarray, is_audio_available: bool = True) -> DetectorResult:
        """
        Executes complete Speaker Diarization pipeline over rolling 20-second PCM audio buffer.
        """
        now = time.time()
        self.last_diarization_time = now

        if not is_audio_available or pcm_20s_audio is None or len(pcm_20s_audio) == 0:
            return DetectorResult(
                detector_name=self.detector_name,
                state=config.STATE_NORMAL,
                message="Audio monitoring unavailable",
                raw_data={"audio_available": False, "speech_detected": False, "credible_speaker_count": 0, "speaker_durations": {}}
            )

        window_duration = float(len(pcm_20s_audio) / self.sample_rate)

        # 1. Voice Activity Detection & Sub-window Extraction (1.0s window with 0.25s hop)
        sub_win_len = int(self.sample_rate * 1.0)   # 1.0s
        hop_len = int(self.sample_rate * 0.25)      # 0.25s hop

        embeddings: List[np.ndarray] = []
        sub_time_intervals: List[Tuple[float, float]] = []

        total_samples = len(pcm_20s_audio)
        for start_idx in range(0, total_samples - sub_win_len + 1, hop_len):
            chunk = pcm_20s_audio[start_idx : start_idx + sub_win_len]
            rms = float(np.sqrt(np.mean(chunk**2)))

            # Process sub-windows containing active speech
            if rms >= config.VAD_ENERGY_THRESHOLD:
                emb = self.extract_subwindow_embedding(chunk)
                if np.linalg.norm(emb) > 0:
                    start_sec = round(start_idx / self.sample_rate, 1)
                    end_sec = round((start_idx + sub_win_len) / self.sample_rate, 1)
                    embeddings.append(emb)
                    sub_time_intervals.append((start_sec, end_sec))

        speech_detected = len(embeddings) > 0

        # If no active speech present in the 20s window
        if not speech_detected:
            self.confirmation_history.append(0)
            self.last_credible_count = 0
            self.last_speaker_durations = {}
            self.last_turns = []

            return DetectorResult(
                detector_name=self.detector_name,
                state=config.STATE_NORMAL,
                message="No speech detected in recent 20s window",
                raw_data={
                    "audio_available": True,
                    "speech_detected": False,
                    "credible_speaker_count": 0,
                    "speaker_durations": {},
                    "turns": [],
                    "confirmed_windows": 0
                }
            )

        # 2. Agglomerative Hierarchical Clustering (Cosine Distance Threshold = 0.22)
        feats_matrix = np.array(embeddings, dtype=np.float32)
        if len(feats_matrix) == 1:
            labels = np.array([0])
        elif HAS_SKLEARN:
            clustering = AgglomerativeClustering(
                n_clusters=None,
                metric='cosine',
                linkage='average',
                distance_threshold=config.SPEAKER_DISTANCE_THRESHOLD
            )
            labels = clustering.fit_predict(feats_matrix)
        else:
            # Fallback using scipy.cluster.hierarchy
            # Normalize vectors to unit length for cosine distance
            norm = np.linalg.norm(feats_matrix, axis=1, keepdims=True)
            norm[norm == 0] = 1.0
            norm_feats = feats_matrix / norm
            dists = pdist(norm_feats, metric='cosine')
            Z = linkage(dists, method='average')
            # fcluster gives 1-based cluster IDs; map to 0-based
            c_labels = fcluster(Z, t=config.SPEAKER_DISTANCE_THRESHOLD, criterion='distance')
            labels = c_labels - 1

        # 3. Map Sub-windows to Speaker Turn Segments & Calculate Speaker Durations
        raw_durations: Dict[str, float] = {}
        turns: List[SpeakerDiarizationTurn] = []

        for (st, et), lbl in zip(sub_time_intervals, labels):
            spk_name = f"SPEAKER_{lbl:02d}"
            turns.append(SpeakerDiarizationTurn(st, et, spk_name))
            raw_durations[spk_name] = round(raw_durations.get(spk_name, 0.0) + 0.25, 1)

        # 4. Minimum Credible Speaker Duration Filtering (>= MIN_DIARIZED_SPEAKER_SECONDS)
        credible_speaker_durations = {
            spk: dur for spk, dur in raw_durations.items()
            if dur >= config.MIN_DIARIZED_SPEAKER_SECONDS
        }
        credible_speaker_count = len(credible_speaker_durations)

        self.last_credible_count = credible_speaker_count
        self.last_speaker_durations = credible_speaker_durations
        self.last_turns = turns

        # 5. Multi-Window Temporal Confirmation
        window_has_multiple = credible_speaker_count >= 2
        self.confirmation_history.append(1 if window_has_multiple else 0)

        confirmed_windows = sum(self.confirmation_history)
        is_confirmed_violation = confirmed_windows >= config.MULTIPLE_SPEAKER_CONFIRM_WINDOWS
        state = config.STATE_MULTIPLE_SPEAKERS if is_confirmed_violation else config.STATE_NORMAL

        # 6. Detailed Console Diagnostics Logging
        if config.SHOW_DIARIZATION_DEBUG:
            print("\n" + "=" * 60)
            print(f"[DIARIZATION RESULT] Window: {window_duration:.1f}s | Status: COMPLETE")
            for t in turns[:8]:
                print(f"  {t.start_sec:04.1f}s -> {t.end_sec:04.1f}s : {t.speaker_label} ({t.duration}s)")
            if len(turns) > 8:
                print(f"  ... (+ {len(turns) - 8} more turns)")
            print("-" * 60)
            print("Speaker Totals:")
            for spk, dur in raw_durations.items():
                is_cred = dur >= config.MIN_DIARIZED_SPEAKER_SECONDS
                print(f"  - {spk}: {dur:.1f} sec (Credible: {'YES' if is_cred else 'NO'})")
            print(f"Credible Speaker Count: {credible_speaker_count} | Confirmed Windows: {confirmed_windows}/{config.MULTIPLE_SPEAKER_CONFIRM_WINDOWS}")
            print("=" * 60 + "\n")

        msg = f"Diarized Speakers: {credible_speaker_count} (Confirmed Windows: {confirmed_windows}/{config.MULTIPLE_SPEAKER_CONFIRM_WINDOWS})"

        return DetectorResult(
            detector_name=self.detector_name,
            state=state,
            similarity_score=0.0,
            verified=not is_confirmed_violation,
            message=msg,
            raw_data={
                "audio_available": True,
                "speech_detected": speech_detected,
                "credible_speaker_count": credible_speaker_count,
                "raw_speaker_count": len(raw_durations),
                "speaker_durations": credible_speaker_durations,
                "raw_durations": raw_durations,
                "confirmed_windows": confirmed_windows,
                "window_has_multiple": window_has_multiple
            }
        )

    def process(self, frame: np.ndarray) -> DetectorResult:
        """BaseDetector interface placeholder."""
        return DetectorResult(detector_name=self.detector_name, state=config.STATE_NORMAL, message="Use run_diarization")
