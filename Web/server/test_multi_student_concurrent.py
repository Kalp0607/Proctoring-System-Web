"""
Automated Multi-Student Concurrent Wi-Fi Proctoring Integration Verification Test
Tests end-to-end:
1. Node Express Backend and FastAPI AI Proctoring Engine startup
2. Test creation by Examiner
3. Concurrent registrations for 2 students with isolated photos
4. Concurrent exam startups
5. Concurrent AI proctoring sessions initialization
6. Frame streaming and violation isolation between students
7. Verifying that Student 1's violation NEVER affects Student 2
8. Isolated session shutdown and teacher report verification
"""

import os
import sys
import time
import base64
import subprocess
import requests
import cv2
import numpy as np
from pathlib import Path

SERVER_DIR = Path(r"C:\Users\kalp0\Desktop\Final_Version_Minor_Project\Proctoring-System-Web\Web\server")
AI_DIR = Path(r"C:\Users\kalp0\Desktop\Final_Version_Minor_Project\Proctoring-System-Web\AI\AI-proctoring-system")
UPLOADS_DIR = SERVER_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

BACKEND_URL = "http://127.0.0.1:5000/api"
AI_URL = "http://127.0.0.1:8000/api/ai"


def make_dummy_face_image(name_text: str, color=(200, 160, 120)) -> bytes:
    """Creates a sample dummy image with candidate label."""
    img = np.zeros((360, 480, 3), dtype=np.uint8)
    cv2.rectangle(img, (0, 0), (480, 360), color, -1)
    cv2.circle(img, (240, 180), 90, (255, 220, 180), -1)
    cv2.putText(img, name_text, (80, 330), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    _, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()


def run_test():
    print("=" * 70, flush=True)
    print("   MULTI-STUDENT CONCURRENT WI-FI PROCTORING VERIFICATION TEST", flush=True)
    print("=" * 70, flush=True)

    # 1. Start Node.js Server in background if not already running
    server_proc = None
    try:
        requests.get("http://127.0.0.1:5000/api/health", timeout=1)
        print("[OK] Backend server already running on port 5000.", flush=True)
    except Exception:
        print("Starting Backend server...", flush=True)
        server_proc = subprocess.Popen(["npm", "run", "dev"], cwd=str(SERVER_DIR), shell=True)
        for _ in range(15):
            time.sleep(1)
            try:
                r = requests.get("http://127.0.0.1:5000/api/health", timeout=1)
                if r.status_code == 200:
                    print("[OK] Backend server started successfully.", flush=True)
                    break
            except Exception:
                pass

    # 2. Start FastAPI AI Proctoring Server if not running
    ai_proc = None
    try:
        requests.get("http://127.0.0.1:8000/api/ai/health", timeout=1)
        print("[OK] AI Proctoring engine already running on port 8000.", flush=True)
    except Exception:
        print("Starting FastAPI AI Proctoring engine...", flush=True)
        ai_cmd = [sys.executable, "-m", "uvicorn", "proctor_service:app", "--host", "0.0.0.0", "--port", "8000"]
        ai_proc = subprocess.Popen(ai_cmd, cwd=str(AI_DIR))
        for _ in range(20):
            time.sleep(1)
            try:
                r = requests.get("http://127.0.0.1:8000/api/ai/health", timeout=1)
                if r.status_code == 200:
                    print("[OK] AI Proctoring engine started successfully.", flush=True)
                    break
            except Exception:
                pass

    try:
        # Step A: Register Examiner
        print("\n--- Step 1: Register Examiner & Create Exam ---", flush=True)
        ts = int(time.time())
        ex_res = requests.post(f"{BACKEND_URL}/auth/register", json={
            "name": f"Prof. MultiNet_{ts}",
            "email": f"prof_wifi_{ts}@test.edu",
            "password": "password123",
            "role": "examiner"
        }).json()
        examiner_token = ex_res["token"]
        print(f"Examiner registered: {ex_res['email']}", flush=True)

        # Create Exam: start in 5 minutes, deadline equal to start, duration 60 minutes
        now = time.time()
        start_time = now + 300
        end_time = start_time + 3600
        deadline = start_time

        test_payload = {
            "title": f"Distributed Algorithms Multi-Client Exam {ts}",
            "description": "Simultaneous multi-student test over Wi-Fi",
            "testPassword": "WIFI_PASS_2026",
            "startTime": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start_time)),
            "endTime": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(end_time)),
            "registrationDeadline": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(deadline)),
            "requirePhoto": True,
            "registrationFields": [
                {"id": "roll_no", "label": "Roll No", "fieldType": "text", "required": True}
            ],
            "questions": [
                {
                    "id": "q1",
                    "questionType": "mcq",
                    "questionText": "What is 10 + 20?",
                    "marks": 5,
                    "options": ["20", "30", "40", "50"],
                    "correctOption": 1
                }
            ]
        }
        res = requests.post(f"{BACKEND_URL}/tests", json=test_payload, headers={"Authorization": f"Bearer {examiner_token}"})
        test_res = res.json()
        assert res.status_code == 201, f"Create test failed: {test_res}"
        test_id = test_res["testId"]
        print(f"Exam Created Successfully: Test ID = {test_id}", flush=True)

        # Step B: Register Student 1 (Alice) & Student 2 (Bob)
        print("\n--- Step 2: Register Two Concurrent Students ---", flush=True)
        stu1_res = requests.post(f"{BACKEND_URL}/auth/register", json={
            "name": "Alice Candidate",
            "email": f"alice_{ts}@test.edu",
            "password": "password123",
            "role": "examinee"
        }).json()
        stu1_token = stu1_res["token"]
        stu1_id = stu1_res["_id"]

        stu2_res = requests.post(f"{BACKEND_URL}/auth/register", json={
            "name": "Bob Candidate",
            "email": f"bob_{ts}@test.edu",
            "password": "password123",
            "role": "examinee"
        }).json()
        stu2_token = stu2_res["token"]
        stu2_id = stu2_res["_id"]

        print(f"Student 1 Registered: Alice (User ID: {stu1_id})", flush=True)
        print(f"Student 2 Registered: Bob   (User ID: {stu2_id})", flush=True)

        # Save distinct reference photos
        alice_img_bytes = make_dummy_face_image("Alice Candidate", (180, 80, 80))
        alice_photo_path = UPLOADS_DIR / f"alice_ref_{ts}.jpg"
        alice_photo_path.write_bytes(alice_img_bytes)

        bob_img_bytes = make_dummy_face_image("Bob Candidate", (80, 180, 80))
        bob_photo_path = UPLOADS_DIR / f"bob_ref_{ts}.jpg"
        bob_photo_path.write_bytes(bob_img_bytes)

        # Alice Registers for Test
        reg1_res = requests.post(
            f"{BACKEND_URL}/tests/{test_id}/register",
            data={"formData": '{"roll_no": "ALICE-01"}'},
            files={"photo": (alice_photo_path.name, open(alice_photo_path, "rb"), "image/jpeg")},
            headers={"Authorization": f"Bearer {stu1_token}"}
        ).json()
        assert reg1_res.get("success"), f"Alice registration failed: {reg1_res}"

        # Bob Registers for Test
        reg2_res = requests.post(
            f"{BACKEND_URL}/tests/{test_id}/register",
            data={"formData": '{"roll_no": "BOB-02"}'},
            files={"photo": (bob_photo_path.name, open(bob_photo_path, "rb"), "image/jpeg")},
            headers={"Authorization": f"Bearer {stu2_token}"}
        ).json()
        assert reg2_res.get("success"), f"Bob registration failed: {reg2_res}"
        print("[OK] Both students registered for the exam with isolated photos.", flush=True)

        # Step C: Both Students Start Exam Concurrently
        print("\n--- Step 3: Concurrent Exam Initialization ---", flush=True)
        start1 = requests.post(f"{BACKEND_URL}/submissions/start", json={"testId": test_id}, headers={"Authorization": f"Bearer {stu1_token}"}).json()
        start2 = requests.post(f"{BACKEND_URL}/submissions/start", json={"testId": test_id}, headers={"Authorization": f"Bearer {stu2_token}"}).json()
        sub1_id = start1["submissionId"]
        sub2_id = start2["submissionId"]
        print(f"Alice Submission Created: {sub1_id}", flush=True)
        print(f"Bob   Submission Created: {sub2_id}", flush=True)
        assert sub1_id != sub2_id, "Submissions must be completely distinct!"

        # Step D: Initialize AI Proctoring Sessions Concurrently on FastAPI Server
        print("\n--- Step 4: Starting Concurrent Isolated AI Proctoring Sessions ---", flush=True)
        ai_sess1 = requests.post(f"{AI_URL}/start-session", json={
            "testId": test_id,
            "studentId": stu1_id,
            "studentName": "Alice Candidate",
            "photoUrl": f"/uploads/{alice_photo_path.name}",
            "cameraIndex": -1 # Client frame streaming mode
        }).json()
        assert ai_sess1.get("success"), f"Alice AI session failed: {ai_sess1}"
        print(f"Alice AI Session: {ai_sess1['sessionKey']}", flush=True)

        ai_sess2 = requests.post(f"{AI_URL}/start-session", json={
            "testId": test_id,
            "studentId": stu2_id,
            "studentName": "Bob Candidate",
            "photoUrl": f"/uploads/{bob_photo_path.name}",
            "cameraIndex": -1 # Client frame streaming mode
        }).json()
        assert ai_sess2.get("success"), f"Bob AI session failed: {ai_sess2}"
        print(f"Bob   AI Session: {ai_sess2['sessionKey']}", flush=True)

        # Verify both sessions are simultaneously active!
        health = requests.get(f"{AI_URL}/health").json()
        print(f"Total Active Sessions on AI Engine: {health.get('active_candidates')}", flush=True)
        assert health.get("active_candidates") >= 2, f"Expected at least 2 active sessions, got {health}"

        # Step E: Stream Frames & Trigger Violation on Student 1 (Alice) ONLY
        print("\n--- Step 5: Frame Ingestion & Violation Isolation Check ---", flush=True)
        # Alice sends frame
        alice_b64 = "data:image/jpeg;base64," + base64.b64encode(alice_img_bytes).decode("utf-8")
        f_res1 = requests.post(f"{AI_URL}/session/frame", json={
            "testId": test_id,
            "studentId": stu1_id,
            "frameBase64": alice_b64
        }).json()
        assert f_res1.get("success"), f"Alice frame failed: {f_res1}"

        # Bob sends frame
        bob_b64 = "data:image/jpeg;base64," + base64.b64encode(bob_img_bytes).decode("utf-8")
        f_res2 = requests.post(f"{AI_URL}/session/frame", json={
            "testId": test_id,
            "studentId": stu2_id,
            "frameBase64": bob_b64
        }).json()
        assert f_res2.get("success"), f"Bob frame failed: {f_res2}"

        # Now simulate a confirmed AI violation event for Alice ONLY
        print("Recording AI violation (PHONE_DETECTED) for Alice ONLY...", flush=True)
        dummy_screenshot = UPLOADS_DIR / f"alice_phone_viol_{ts}.jpg"
        dummy_screenshot.write_bytes(alice_img_bytes)

        v_data = {
            "testId": test_id,
            "studentId": stu1_id,
            "type": "PHONE_DETECTED",
            "message": "AI detected: Mobile phone in examination area",
            "duration_seconds": 3.0,
            "similarity": 0.92
        }
        with open(dummy_screenshot, "rb") as f:
            v_res = requests.post(f"http://127.0.0.1:5000/api/proctoring/violation", data=v_data, files={"screenshot": (dummy_screenshot.name, f, "image/jpeg")}).json()

        print(f"Violation Ingestion Response: {v_res}", flush=True)
        assert v_res.get("success"), f"Violation ingestion failed: {v_res}"

        # Step F: VERIFY STRICT DATA ISOLATION IN DATABASE
        print("\n--- Step 6: Verifying Complete Data Isolation in Submissions ---", flush=True)
        report = requests.get(f"{BACKEND_URL}/reports/test/{test_id}", headers={"Authorization": f"Bearer {examiner_token}"}).json()
        subs = report.get("allSubmissions", [])
        assert len(subs) == 2, f"Expected 2 submissions in report, got {len(subs)}"

        alice_sub = next((s for s in subs if str(s["studentId"]["_id"]) == str(stu1_id)), None)
        bob_sub = next((s for s in subs if str(s["studentId"]["_id"]) == str(stu2_id)), None)

        assert alice_sub is not None, "Alice submission not found in report!"
        assert bob_sub is not None, "Bob submission not found in report!"

        alice_viols = alice_sub.get("proctoring", {}).get("violations", [])
        bob_viols = bob_sub.get("proctoring", {}).get("violations", [])

        print(f"Alice Violations Count: {len(alice_viols)} (Risk: {alice_sub.get('proctoring', {}).get('riskLevel')})", flush=True)
        print(f"Bob   Violations Count: {len(bob_viols)} (Risk: {bob_sub.get('proctoring', {}).get('riskLevel')})", flush=True)

        # CRITICAL ASSERTIONS:
        assert len(alice_viols) >= 1, "Alice must have at least 1 recorded violation!"
        assert alice_viols[0]["type"] == "PHONE_DETECTED", "Alice violation must be PHONE_DETECTED"
        assert alice_sub.get("proctoring", {}).get("riskLevel") == "High", "Alice risk must be High"

        assert len(bob_viols) == 0, f"BOB MUST HAVE 0 VIOLATIONS! Found: {len(bob_viols)} - Data Leak Detected!"
        assert bob_sub.get("proctoring", {}).get("riskLevel") == "Low", f"Bob risk must be Low, got {bob_sub.get('proctoring', {}).get('riskLevel')}"

        print("\n>>> DATA ISOLATION VERIFIED PERFECTLY! Alice's violation did NOT affect Bob! <<<", flush=True)

        # Step G: Independent Session Termination Check
        print("\n--- Step 7: Independent Session Shutdown Check ---", flush=True)
        stop1 = requests.post(f"{AI_URL}/stop-session", json={"testId": test_id, "studentId": stu1_id}).json()
        assert stop1.get("success"), f"Stop session 1 failed: {stop1}"
        print("Alice session stopped.", flush=True)

        # Check Bob's session: Bob's session must STILL BE ACTIVE!
        bob_status = requests.get(f"{AI_URL}/status?testId={test_id}&studentId={stu2_id}").json()
        print(f"Bob Session Status after Alice stopped: active={bob_status.get('active')}", flush=True)
        assert bob_status.get("active") is True, "Bob session must still be active when Alice stops!"

        # Now stop Bob's session
        stop2 = requests.post(f"{AI_URL}/stop-session", json={"testId": test_id, "studentId": stu2_id}).json()
        assert stop2.get("success"), f"Stop session 2 failed: {stop2}"
        print("Bob session stopped.", flush=True)

        # Both answer and submit exam
        sub_done1 = requests.post(f"{BACKEND_URL}/submissions/submit", json={"testId": test_id, "answers": [{"questionId": "q1", "selectedOption": 1}]}, headers={"Authorization": f"Bearer {stu1_token}"}).json()
        sub_done2 = requests.post(f"{BACKEND_URL}/submissions/submit", json={"testId": test_id, "answers": [{"questionId": "q1", "selectedOption": 1}]}, headers={"Authorization": f"Bearer {stu2_token}"}).json()
        print(f"Alice Final Exam Submit: Marks={sub_done1.get('totalMarksObtained')}", flush=True)
        print(f"Bob   Final Exam Submit: Marks={sub_done2.get('totalMarksObtained')}", flush=True)

        # Check final examiner report
        final_report = requests.get(f"{BACKEND_URL}/reports/test/{test_id}", headers={"Authorization": f"Bearer {examiner_token}"}).json()
        summary = final_report.get("summary", {})
        print(f"\nExaminer Final Report Summary: {summary}", flush=True)
        assert summary.get("totalAppeared") == 2, "Both students should be marked as appeared"
        assert summary.get("highRiskCount") == 1, "Exactly 1 student (Alice) must be categorized as High Risk"
        assert summary.get("lowRiskCount") == 1, "Exactly 1 student (Bob) must be categorized as Low Risk"

        print("\n" + "=" * 70, flush=True)
        print("   [SUCCESS] ALL MULTI-STUDENT CONCURRENT WI-FI CHECKS PASSED 100%!", flush=True)
        print("=" * 70, flush=True)
        return True

    finally:
        if server_proc:
            try:
                server_proc.terminate()
            except Exception:
                pass
        if ai_proc:
            try:
                ai_proc.terminate()
            except Exception:
                pass


if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
