# AI-Proctored Online Examination System (Version 2)

An enterprise-grade, full-stack online examination platform integrated with a real-time multimodal computer vision and audio AI proctoring engine.

---

## 🌟 Overview & Key Capabilities

This repository unifies the **MERN Web Examination Platform** (`Web/`) and the **Multimodal AI Proctoring Engine** (`AI/`) into a single, cohesive, production-ready system.

### 1. Multimodal AI Proctoring (`AI/AI-proctoring-system`)
- **Deep Face Verification**: Uses InsightFace ArcFace (`buffalo_sc`) deep embeddings (512 dimensions) to continuously match the test candidate against their enrolled registration photo.
- **YOLOv11 Real-Time Object Detection**: Detects cell phones (`PHONE_DETECTED`), books/notes (`BOOK_DETECTED`), and unauthorized persons in frame (`MULTIPLE_PEOPLE`).
- **3D Head Pose & Gaze Deviation Estimation**: Uses facial landmark geometry and Perspective-n-Point (`solvePnP`) to detect prolonged gaze shifts away from the monitor (`LOOKING_AWAY`).
- **Speaker Diarization**: 20-second rolling audio analysis with Mel-spectral cepstral feature clustering detecting multiple distinct voices (`MULTIPLE_SPEAKERS`).
- **Automated Evidence Capture & Telemetry Hook**: Automatically captures annotated violation screenshots and streams alerts in real-time to the Node.js backend.

### 2. Comprehensive Examination Platform (`Web/`)
- **Interactive MCQ & LeetCode-Style Coding Environment**:
  - Split-pane layout with question prompt and Monaco code editor.
  - Interactive "Run Code" execution with custom input/output powered by Judge0.
  - "Submit Solution" validating hidden test cases, execution time, and auto-grading.
- **Anti-Cheating Window Enforcement**:
  - Fullscreen lock with escape detection.
  - Tab-switch and window-blur tracking with progressive warning modals.
- **Real-Time AI Proctoring Live HUD**:
  - Embedded live video stream with AI telemetry overlays.
  - Status pills displaying face match confidence, gaze direction, audio status, and detected objects.
- **Examiner Hub & Dynamic Administration**:
  - Custom test builder supporting MCQ + Coding questions and custom registration forms.
  - Dynamic shareable test links and SVG QR codes.
  - Real-time candidate roster with student removal capability.
  - **Permanent Test Deletion**: Examiners can permanently delete tests along with cascaded removal of registrations, answers, submissions, and proctoring telemetry.
  - Comprehensive reporting with risk categorization (`High`, `Medium`, `Low`), violation timelines, screenshot evidence review, examiner marks override, and downloadable official PDF reports.

---

## 🏗️ Project Architecture

```
AI-Proctoring System Web Part/
├── run_all.py                 # Unified runner orchestrating all 3 services concurrently
├── package.json               # Root scripts (e.g. npm start)
├── .gitignore                 # Root gitignore for unified stack
│
├── AI/
│   └── AI-proctoring-system/  # FastAPI Multimodal AI Proctoring Engine (Port 8000)
│       ├── proctor_service.py # FastAPI service endpoints & background proctoring worker
│       ├── config.py          # Thresholds, model weights & backend integration configs
│       ├── main.py            # Standalone proctoring engine runner
│       ├── detectors/         # InsightFace, YOLOv11 & Head Pose estimation detectors
│       ├── audio/             # Live microphone capture & speaker diarization
│       ├── camera/            # Webcam thread management
│       ├── violations/        # Violation manager, logger & evidence capture
│       └── requirements.txt   # Python AI dependencies
│
└── Web/
    ├── client/                # React Vite Frontend (Port 5173)
    │   ├── src/
    │   │   ├── pages/         # Examiner Dashboard, Pre-Test Panel, Exam Environment, etc.
    │   │   ├── components/    # Shared components (Navbar, ProtectedRoute)
    │   │   └── services/      # Unified REST & AI API service client
    │   └── package.json
    │
    └── server/                # Node.js Express Backend (Port 5000)
        ├── controllers/       # Test, submission, proctoring & report controllers
        ├── models/            # MongoDB Mongoose schemas (User, Test, Registration, Submission)
        ├── routes/            # REST API endpoints
        ├── services/          # Judge0 code execution & PDFKit report generator
        └── server.js          # Express entrypoint
```

---

## 🚀 Quick Start Guide

### Prerequisites
- **Node.js**: v18+ and `npm`
- **Python**: v3.10 - v3.13
- **MongoDB**: Local instance running on `mongodb://localhost:27017` or MongoDB Atlas URI

### 1. Installation

Install Node.js dependencies:
```bash
# Install root dependencies
npm install

# Install Web server dependencies
cd Web/server && npm install

# Install Web client dependencies
cd ../client && npm install
```

Install Python AI dependencies:
```bash
cd AI/AI-proctoring-system
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Create `Web/server/.env` (see `Web/server/.env.example`):
```env
PORT=5000
MONGO_URI=mongodb://localhost:27017/ai-proctoring
JWT_SECRET=ai_proctor_jwt_super_secret_key_2026
JUDGE0_API_URL=https://judge0-ce.p.rapidapi.com
JUDGE0_API_KEY=your_optional_judge0_api_key
```

### 3. Run All Services Concurrently

From the root directory:
```bash
npm start
```
*(Or directly: `python run_all.py`)*

This launches:
- **Node.js Express Backend**: `http://localhost:5000`
- **React Vite Frontend**: `http://localhost:5173`
- **FastAPI AI Proctoring Engine**: `http://localhost:8000`

---

## 🧪 Testing & Verification

The repository includes complete test suites covering unit, API integration, and headless browser production workflows:

- **Full End-to-End System Audit**:
  ```bash
  cd Web/server && node test_full_suite.js
  ```
- **Real Chrome Browser Production Flow**:
  ```bash
  cd Web/server && node test_live_production.js
  ```

---

## 📄 License
MIT License.
