# Proctoring-System-Web

Full-featured, production-ready MERN stack web application for an **AI-Proctored Online Examination Platform**.

---

## 🌟 Key Features

### 👨‍🏫 Examiner Portal
- **Test Authoring**: Create exams with both Multiple Choice Questions (MCQ) and Coding Challenges (with public & hidden test cases).
- **Dynamic Candidate Registration**: Configure custom registration fields (College, Roll No, Branch) and require candidate webcam photo upload.
- **Passcode & Timing Control**: Strict start time, end time, and registration deadline enforcement with passcodes, direct links, and QR codes.
- **Candidate Roster Management**: Real-time view of registered students with submitted verification photos and one-click candidate removal.
- **Proctoring Analytics & Reports**: Live risk categorization (High, Medium, Low Risk), infraction timeline review, 0-marks cheating penalty action, and official PDF report export (PDFKit).

### 🎓 Examinee / Student Portal
- **Passcode-Protected Registration**: Enter test via passcode or QR code, fill dynamic registration fields, and submit webcam photo before deadline.
- **Pre-Test Waiting Room (15-Minute Panel)**: Automatic system checks (webcam feed, full-screen readiness, audio) and live countdown to exam start.
- **Anti-Cheating Enforcement**:
  - Full-screen lock and focus-loss detection.
  - **1-Warning Policy**: Immediate warning on 1st tab-switch / minimize; automatic submission with locked answers on 2nd violation.
- **LeetCode-Style Coding Workspace**:
  - Split-pane layout with formatted problem descriptions, examples, and execution constraints.
  - Multi-language support (**JavaScript**, **Python 3**, **C++**, **Java**) with idiomatic boilerplate templates and per-language state memory.
  - **Run Code**: Execute against sample test cases or custom stdin.
  - **Submit Code**: Run against **all test cases (including hidden test cases)** with real-time pass/fail breakdown just like LeetCode.
  - Adjustable screen split presets (`40/60`, `Wide`, `50/50`, `Code Only`), full-screen code editor mode, and collapsible question palette sidebar.
- **Question Palette & Navigation**: Color-coded tracking for Answered (Green), Visited/Unanswered (Amber), Marked for Review (Purple), Not Visited, and Current Question.

---

## 🛠️ Technology Stack

- **Frontend**: React 19, Vite, React Router v7, Lucide Icons, QRCode.react, Vanilla CSS Design System.
- **Backend**: Node.js, Express.js, MongoDB (Mongoose), JWT, Bcrypt.js, Multer, PDFKit.
- **Code Execution**: Dual-engine Judge0 API runner with built-in safe local fallback runner for JavaScript, Python, C++, and Java.

---

## 🚀 Getting Started

### 1. Prerequisites
- **Node.js** (v18+)
- **MongoDB** running locally (`mongodb://127.0.0.1:27017`) or MongoDB Atlas URI

### 2. Backend Setup
```bash
cd server
npm install
cp .env.example .env
npm run dev
```
*(Backend runs on `http://127.0.0.1:5000`)*

### 3. Frontend Setup
```bash
cd ../client
npm install
npm run dev
```
*(Frontend runs on `http://localhost:5173`)*

---

## 🔒 Environment Configuration

Create a `.env` file in `server/` using `.env.example`:

```env
PORT=5000
MONGO_URI=mongodb://127.0.0.1:27017/ai_proctor_db
JWT_SECRET=your_jwt_secret_key_here
CLIENT_URL=http://localhost:5173

# Optional: Judge0 Remote API (leave blank to use local fallback execution)
JUDGE0_API_URL=
JUDGE0_API_KEY=
JUDGE0_API_HOST=judge0-ce.p.rapidapi.com
```

---

## 📜 License
ISC License
