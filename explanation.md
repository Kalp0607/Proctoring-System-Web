# AI Proctoring Architecture: Multi-Student Wi-Fi & Remote Frame Transfer

## 1. Overview: Zero AI Requirements on Student Devices

A major design principle of this architecture is **Zero Client-Side Setup**:
* **Students do NOT install anything**: No Python, no PyTorch, no ONNX, and no AI models run on the students' laptops.
* **Standard Web Browser Only**: Students simply open Google Chrome, Edge, or Firefox and navigate to the examination URL (e.g., `http://192.168.1.50:5173/test/enter/XYZ`).
* **Single AI Host**: Only **ONE laptop** (the teacher's or host's machine) runs the FastAPI AI Engine, Node Express Backend, and Vite Web Server.

```
+-----------------------------------------------------------------------------------------------------------+
|                                  TEACHER / SERVER HOST LAPTOP                                             |
|                                                                                                           |
|  Runs all heavy services:                                                                                 |
|  - Node.js Express Backend (:5000)                                                                        |
|  - FastAPI AI Proctoring Engine (:8000) [InsightFace + YOLOv11 ONNX + 3D Head Pose + Diarization]          |
|  - Vite React Web Application (:5173)                                                                     |
+-----------------------------------------------------------------------------------------------------------+
                                   ^                                           ^
                       Local Wi-Fi |                               Local Wi-Fi |
                       HTTP POST   |                               HTTP POST   |
                                   v                                           v
+-----------------------------------------------------+     +-----------------------------------------------------+
|                STUDENT 1 (LAPTOP A)                 |     |                STUDENT 2 (LAPTOP B)                 |
|  (No Python, No AI, Just a Browser)                |     |  (No Python, No AI, Just a Browser)                 |
|                                                     |     |                                                     |
|  1. HTML5 getUserMedia() opens student webcam       |     |  1. HTML5 getUserMedia() opens student webcam        |
|  2. Hidden Canvas captures JPEG snapshot            |     |  2. Hidden Canvas captures JPEG snapshot             |
|  3. Sends frame via HTTP POST to Server:            |     |  3. Sends frame via HTTP POST to Server:             |
|     /api/ai/session/frame                           |     |     /api/ai/session/frame                            |
|     Payload: { testId, studentId, frameBase64 }     |     |     Payload: { testId, studentId, frameBase64 }      |
|  4. Receives AI Telemetry & Violation Warnings      |     |  4. Receives AI Telemetry & Violation Warnings       |
+-----------------------------------------------------+     +-----------------------------------------------------+
```

---

## 2. End-to-End Workflow: How Frames are Transferred & Violations Logged

### Step 1: Local Webcam Capture in the Student's Browser
When a student enters the exam page (`ExamEnvironment.jsx`):
1. The browser requests access to the student's webcam using the standard Web API:
   ```javascript
   const stream = await navigator.mediaDevices.getUserMedia({
     video: { width: 480, height: 360, facingMode: "user" },
     audio: false
   });
   videoRef.current.srcObject = stream;
   ```
2. The student's camera stream is rendered **locally** in the in-browser Heads-Up Display (HUD) video element. This gives the student instantaneous 60 FPS feedback with zero latency.

---

### Step 2: Frame Compression & Transfer Over Wi-Fi
Instead of streaming massive raw uncompressed video (which would choke a Wi-Fi router), the client captures lightweight JPEG snapshots:
1. An off-screen HTML5 `<canvas>` grabs a frame every **400 ms** (~2.5 frames per second):
   ```javascript
   ctx.drawImage(videoRef.current, 0, 0, 480, 360);
   const frameBase64 = canvas.toDataURL("image/jpeg", 0.65);
   ```
2. The browser sends this lightweight JPEG string (~15–20 KB) over the local Wi-Fi to the server via an HTTP POST request:
   ```json
   POST http://192.168.1.50:8000/api/ai/session/frame
   {
     "testId": "TEST-8BERBG",
     "studentId": "6ae4ef1de73c1519dcc570c5",
     "frameBase64": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQ..."
   }
   ```
3. **Bandwidth Impact**:
   * ~20 KB per frame $\times$ 2.5 frames/sec = **~50 KB/sec per student**.
   * 20 concurrent students consume only **~1.0 MB/sec total bandwidth**, well within any standard 2.4 GHz or 5 GHz Wi-Fi router capacity.

---

### Step 3: Server-Side AI Processing & Session Lookup
When the host laptop receives the frame at `POST /api/ai/session/frame`:
1. **Isolated Session Lookup**:
   The server extracts `testId` and `studentId` and retrieves that candidate's isolated `SessionState` object from memory:
   ```python
   session_key = f"{test_id.upper()}_{student_id}"
   sess = sessions[session_key]
   ```
2. **AI Inference Pipeline**:
   The frame is passed through the 4 multimodal detection stages:
   * **Stage 1 (Face Verification)**:
     `sess.face_verifier.process(frame)` checks if the face matches the reference photo enrolled during registration.
   * **Stage 2 (YOLO Object Detection)**:
     `shared_object_detector.process(frame)` detects objects (mobile phone, book/notes, multiple persons). Inference runs on a **shared pre-warmed YOLO model singleton** to prevent server RAM overload.
   * **Stage 3 (3D Head Pose Estimation)**:
     `sess.head_pose_detector.process(frame)` computes 3D Euler angles (Yaw, Pitch, Roll) to determine if the candidate is looking away from their screen.
   * **Stage 4 (Temporal Confirmation & Debouncing)**:
     `sess.violation_mgr.update(...)` applies rolling-window thresholds to ensure transient twitches or false blinks do not trigger false alarms.

---

### Step 4: How Violations are Isolated, Stamped, and Logged
If a violation is confirmed (e.g., a phone is detected in the student's frame):
1. **Evidence Screenshot Capture**:
   `ViolationManager` stamps an evidence banner directly on that student's frame:
   ```
   +------------------------------------------------------------------------------------+
   | PROCTORING VIOLATION: PHONE_DETECTED | Candidate: Alice | Time: 2026-10-31T00:55:16 |
   +------------------------------------------------------------------------------------+
   ```
   The screenshot is saved with an isolated filename:
   ```
   violations/screenshots/TEST-8BERBG_6ae4ef1de73c1519dcc570c5_1793388317_PHONE_DETECTED.jpg
   ```
2. **Asynchronous Backend Ingestion**:
   The AI service posts the infraction directly to the Node.js Express backend:
   ```
   POST http://localhost:5000/api/proctoring/violation
   Data: {
     testId: "TEST-8BERBG",
     studentId: "6ae4ef1de73c1519dcc570c5",
     type: "PHONE_DETECTED",
     message: "AI detected: Mobile phone in examination area"
   }
   Files: { screenshot: <binary_jpeg> }
   ```
3. **Database Attribution Guarantee**:
   In `proctoringController.js`, `findStudentSubmission` matches the submission strictly by `testId` and `studentId` (or `registrationId`).
   * **Zero Fallback Leakage**: The server never guesses or falls back to recent submissions. Alice's violation is saved **exclusively** into Alice's MongoDB document. Bob's record remains 100% clean.

---

### Step 5: Real-Time Feedback to the Student
The HTTP POST response from `/api/ai/session/frame` returns immediately to the student's browser with the latest telemetry:
```json
{
  "success": true,
  "active": true,
  "telemetry": {
    "face_detected": true,
    "face_verified": true,
    "similarity": 0.88,
    "looking_away": false,
    "phone_detected": true,
    "multiple_people": false,
    "violations_count": 1
  },
  "events": [
    {
      "id": "viol_1793388317_PHONE_DETECTED",
      "type": "PHONE_DETECTED",
      "message": "Phone detected",
      "severity": "critical"
    }
  ]
}
```
* The student's React application receives this response, updates HUD telemetry badges, and shows a non-intrusive warning toast: `"Phone detected"`.

---

### Step 6: Teacher Visibility & Examiner Dashboard
1. The teacher visits `http://localhost:5173/examiner/test/TEST-8BERBG/report` (or `http://<WIFI_IP>:5173`).
2. The report fetches all submissions for the exam:
   * **Student 1 (Alice)**: Shows 1 violation (`PHONE_DETECTED`), High Risk score, and the stamped screenshot evidence.
   * **Student 2 (Bob)**: Shows 0 violations, Low Risk score, and a clean session report.
3. The teacher can download a formal PDF summary where each student's log and screenshots are clearly separated.

---

## 3. Data Isolation Summary Matrix

| Data Item | Student 1 (e.g., Alice) | Student 2 (e.g., Bob) | Isolation Mechanism |
| :--- | :--- | :--- | :--- |
| **Hardware** | Laptop A Webcam | Laptop B Webcam | Browser `getUserMedia()` on student device |
| **Reference Photo** | Alice's registered image | Bob's registered image | Enrolled in separate `FaceVerifier` instances |
| **Head Pose Baseline** | Alice's screen calibration | Bob's screen calibration | Separate `HeadPoseDetector` instances |
| **Violation Episodes** | Alice's violations | Bob's violations | Separate `ViolationManager` state machines |
| **Screenshots** | `TEST_Alice_<timestamp>.jpg` | `TEST_Bob_<timestamp>.jpg` | Prefixed with student ID & stored independently |
| **MongoDB Document** | Alice's `Submission` ID | Bob's `Submission` ID | Strict `findStudentSubmission()` by candidate ID |
| **Session Shutdown** | Stop session cleans Alice | Bob continues unimpacted | Independent `sessions[key]` entries |

---

## 4. Wi-Fi Browser Camera Security Context (Why HTTPS is Essential)

Modern web browsers (Google Chrome, Microsoft Edge, Safari, Firefox) enforce a strict security policy according to W3C specifications:
* **`navigator.mediaDevices.getUserMedia()` is ONLY available in Secure Contexts (`isSecureContext === true`)**.
* `http://localhost` and `http://127.0.0.1` are automatically treated as secure contexts.
* However, when a student accesses the host server over local Wi-Fi via an IP address (e.g. `192.168.x.x`), plain HTTP (`http://192.168.x.x:5173`) is classified as an **insecure context**, and the browser completely disables `navigator.mediaDevices`.
* To provide seamless webcam access across all devices on the Wi-Fi network:
  1. The Vite dev server is pre-configured with **HTTPS** via `@vitejs/plugin-basic-ssl`.
  2. Students connect using `https://<teacher-ip>:5173` (embedded automatically in the test sharing QR code and links).
  3. When connecting to the local certificate for the first time, students click **Advanced -> Proceed** (a 1-time browser step), immediately granting access to the webcam.
  4. If a candidate ever arrives via `http://`, the application automatically upgrades them to `https://` and displays a non-blocking 1-click switch button.

---

## 5. Summary

* **No client installation needed**: Any device with a modern browser and webcam can join.
* **Low network overhead**: 2.5 FPS JPEG snapshots require negligible Wi-Fi bandwidth (~50 KB/s per student).
* **High server efficiency**: 1 shared YOLO ONNX model handles inference across all incoming frames, while session state, face verification, head pose, and violations remain completely isolated.
* **Guaranteed data integrity**: One student's violations or camera stream will never be attributed to another student.

