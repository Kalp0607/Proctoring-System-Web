# AI Exam Proctoring System — Stage 5: Full Multimodal AI Proctoring (20s Speaker Diarization Engine)

Stage 5 of a modular, real-time AI online exam proctoring system built in Python 3.11.

It simultaneously performs:
1. **Live Face Verification** (ArcFace deep face embeddings matching enrolled student photo).
2. **Multiple-Person Detection** (COCO class `0` `person` with IoU NMS duplicate suppression).
3. **Mobile Phone Detection** (COCO class `67` `cell phone`).
4. **Book Detection** (COCO class `73` `book`).
5. **3D Head Pose Estimation & Looking-Away Detection** (Perspective-n-Point `solvePnP` 3D orientation).
6. **20-Second Rolling Speaker Diarization Engine** (128D Mel-spectral cepstral dynamics embeddings & Agglomerative Hierarchical Clustering).
7. **Per-Session Baseline Calibration** (2-second median posture calibration).
8. **Temporal Confirmation & Grace Period Debouncing** (Continuous violations create 1 episode, save 1 screenshot, and append 1 JSON record).
9. **Real-Time Split-Screen Dashboard** (Live webcam feed + proctoring control side panel with Audio Diarization telemetry).

---

## 🎙️ Stage 5 Speaker Diarization Architecture

```
LIVE MICROPHONE (16kHz Mono PCM)
        │
        ▼
Rolling Memory Audio Buffer (DIARIZATION_WINDOW_SECONDS = 20.0s)
        │
        ▼ (Periodic Non-Blocking Worker Thread every 4.0s)
Asynchronous Diarization Worker Thread
        │
        ▼
1. Speech Turn Segmentation (VAD Energy Thresholding)
        │
        ▼
2. Sliding Window Sub-segmentation (1.5s sub-windows with 0.5s hop)
        │
        ▼
3. 128D Mel-Spectral & Cepstral Feature Embedding Extraction
        │
        ▼
4. Agglomerative Hierarchical Clustering (Cosine Distance Threshold = 0.35)
        │
        ▼
5. Speaker Turn Accumulation & Duration Calculation (e.g., SPEAKER_00: 5.7s, SPEAKER_01: 3.6s)
        │
        ▼
6. Minimum Credible Speaker Duration Filter (MIN_DIARIZED_SPEAKER_SECONDS = 1.5s)
        │
        ▼
7. Multi-Window Temporal Confirmation (MULTIPLE_SPEAKER_CONFIRM_WINDOWS = 2)
        │
        ▼
MULTIPLE_SPEAKERS Violation (1 episode, 1 JSON log, 1 evidence screenshot)
```

### Key Technical Design Rules:
- **No Voice Identification & No Audio Files Saved**: Speaker Diarization estimates the number of distinct speakers ($1$ vs $2+$) over a rolling 20-second window without needing an enrolled student voice sample. Audio is processed purely in RAM; **no continuous audio or WAV files are recorded to disk**.
- **Periodic Non-Blocking Worker Thread**: Runs every 4.0s (`DIARIZATION_INTERVAL_SECONDS = 4.0s`) in a dedicated background worker thread. If an analysis pass is currently running, stale requests are skipped to guarantee zero webcam/UI display lag.
- **Minimum Credible Speaker Duration Filter (`MIN_DIARIZED_SPEAKER_SECONDS = 1.5s`)**: A speaker label must accumulate $\ge 1.5$ seconds of speech within the 20s window to count as a credible speaker.
- **Multimodal Independence**: Video `MULTIPLE_PEOPLE` (visual face count) and Audio `MULTIPLE_SPEAKERS` (audio speaker count) operate independently. An off-camera speaker triggers `MULTIPLE_SPEAKERS` even if only 1 person is in front of the webcam.

---

## 📁 Complete Folder Structure

```
ai-exam-proctoring-system/
├── config.py                         # Central configuration thresholds, FPS, & Diarization settings
├── main.py                           # Application runner & single-point webcam/mic initialization
├── requirements.txt                  # Python 3.11 package dependencies
├── README.md                         # Detailed documentation & instructions
│
├── audio/
│   ├── __init__.py                   # Package initialization
│   ├── audio_manager.py              # Threaded live microphone stream capture & 20s memory buffer
│   └── speaker_detector.py           # 20s Rolling Speaker Diarization Engine (Agglomerative Clustering)
│
├── camera/
│   └── camera_manager.py             # Threaded frame capture & safe hardware release
│
├── detectors/
│   ├── base_detector.py              # Modular abstract BaseDetector interface
│   ├── face_verifier.py              # Stage 1 Face Detection & ArcFace verifier
│   ├── object_detector.py            # Stage 3 Unified YOLO Detector (IoU NMS person deduplication)
│   ├── person_detector.py            # Backward-compatibility wrapper
│   └── head_pose_detector.py         # Stage 4 3D Geometric Head Pose Estimator (solvePnP)
│
├── violations/
│   ├── logger.py                     # Crash-safe JSON logger for violation records
│   └── violation_manager.py          # Temporal debouncing with intermittent grace period
│
├── ui/
│   └── proctoring_ui.py              # Split-screen dashboard with Diarization telemetry
│
├── models/
│   └── yolov8n.pt                    # Ultralytics YOLO model file
│
├── data/
│   └── reference/
│       └── student.jpg               # Enrolled student reference photo
│
└── violations/
    ├── screenshots/                  # Saved violation screenshots (1280x720 evidence)
    └── violations.json               # Persisted violation records log
```

---

## ⚙️ Configurable Thresholds (`config.py`)

| Parameter | Default | Description |
| :--- | :--- | :--- |
| `AUDIO_ENABLED` | `True` | Master toggle for live microphone audio monitoring. |
| `AUDIO_SAMPLE_RATE` | `16000` | Audio sampling rate in Hz. |
| `DIARIZATION_WINDOW_SECONDS` | `20.0s` | Rolling audio window duration for speaker diarization. |
| `DIARIZATION_INTERVAL_SECONDS` | `4.0s` | Periodic analysis interval for background worker. |
| `SPEAKER_DISTANCE_THRESHOLD` | `0.22` | Cosine Distance threshold for Agglomerative Linkage Clustering (separates distinct voices). |
| `MIN_DIARIZED_SPEAKER_SECONDS` | `1.0s` | Minimum accumulated speech duration in window for a speaker label to be credible. |
| `MULTIPLE_SPEAKER_CONFIRM_WINDOWS` | `2` | Required consecutive confirmed windows with 2+ credible speakers. |
| `SHOW_DIARIZATION_DEBUG` | `True` | Displays formatted console turn tables & UI telemetry. |

---

## 🏃 Running the Application

To start live proctoring (Stages 1–5 Active):

```bash
python main.py
```

### Keyboard Controls
- `Q` or `Esc`: Quit application and release hardware cleanly.
- `C`: Trigger manual baseline posture recalibration.
- `D`: Toggle visual bounding boxes, 3D nose vector, and diagnostic overlays.

---

## 🧪 Manual Stage 5 Diarization Testing Checklist

1. **TEST 1: Candidate Speaking Only**:
   - Candidate speaks multiple sentences into microphone.
   - **Expected Console Output**:
     ```
     [DIARIZATION RESULT] Window: 20.0s | Status: COMPLETE
     0.4s -> 4.8s  : SPEAKER_00 (4.4s)
     Speaker Totals:
       - SPEAKER_00: 4.4 sec (Credible: YES)
     Credible Speaker Count: 1
     ```
   - **Expected UI**: `Diarized window (20s): 1 speaker`, `Evidence: SPEAKER_00: 4.4s`, `Multiple speakers: NO`.

2. **TEST 2: Candidate + Phone Voice / Second Person**:
   - Candidate speaks naturally for 5 seconds (`SPEAKER_00: 5.0s`).
   - Play a distinct person's voice from phone near laptop for 5 seconds (`SPEAKER_01: 4.2s`).
   - **Expected Console Output**:
     ```
     [DIARIZATION RESULT] Window: 20.0s | Status: COMPLETE
     0.4s -> 5.2s  : SPEAKER_00 (4.8s)
     7.1s -> 11.5s : SPEAKER_01 (4.4s)
     ------------------------------------------------------------
     Speaker Totals:
       - SPEAKER_00: 4.8 sec (Credible: YES)
       - SPEAKER_01: 4.4 sec (Credible: YES)
     Credible Speaker Count: 2
     ```
   - Window 1 $\rightarrow$ `Multiple speakers: YES [Pending 1/2]`.
   - Window 2 $\rightarrow$ `Multiple speakers: YES [ACTIVE]` $\rightarrow$ Confirmed `MULTIPLE_SPEAKERS` violation triggers.

3. **TEST 3: Two Physical Humans**:
   - Candidate and a second person speak in turn into microphone.
   - **Expected**: Credible speaker count $\ge 2$, confirmed violation triggers after 2 windows.
