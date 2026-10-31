"""
AI Online Examination & Multimodal AI Proctoring System
Unified Full-Stack Runner (Node Backend + Vite Client + FastAPI AI Proctoring Engine)
Supports Simultaneous Multi-Student Examinations over Local Wi-Fi Network
"""

import os
import sys
import time
import signal
import socket
import subprocess
import threading
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
if (ROOT_DIR / "Proctoring-System-Web").exists():
    ROOT_DIR = ROOT_DIR / "Proctoring-System-Web"
SERVER_DIR = ROOT_DIR / "Web" / "server"
CLIENT_DIR = ROOT_DIR / "Web" / "client"
AI_DIR = ROOT_DIR / "AI" / "AI-proctoring-system"

# ANSI Colors for terminal output
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
RESET = "\033[0m"

processes = []
shutting_down = False


def get_local_wifi_ip():
    """Detects primary local IPv4 address on Wi-Fi/LAN."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


def log_stream(proc, prefix, color):
    """Streams stdout/stderr lines with service prefix."""
    try:
        for line in iter(proc.stdout.readline, ""):
            if shutting_down:
                break
            text = line.rstrip()
            if text:
                print(f"{color}{BOLD}[{prefix}]{RESET} {text}", flush=True)
    except Exception:
        pass


def start_service(cmd, cwd, prefix, color):
    """Starts a subprocess and spawns a thread to stream its logs."""
    is_windows = sys.platform.startswith("win")
    import shutil
    if is_windows and isinstance(cmd, list) and cmd[0] == "npm":
        npm_bin = shutil.which("npm.cmd") or "npm"
        cmd = [npm_bin] + cmd[1:]

    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=is_windows,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1
    )
    processes.append((prefix, proc))
    t = threading.Thread(target=log_stream, args=(proc, prefix, color), daemon=True)
    t.start()
    return proc


def shutdown_all(signum=None, frame=None):
    global shutting_down
    if shutting_down:
        return
    shutting_down = True
    print(f"\n{YELLOW}{BOLD}>>> Shutting down all AI-Proctoring services...{RESET}")

    for prefix, proc in processes:
        try:
            print(f"Stopping {prefix} (PID {proc.pid})...")
            if sys.platform.startswith("win"):
                subprocess.run(f"taskkill /F /T /PID {proc.pid}", shell=True, capture_output=True)
            else:
                proc.terminate()
        except Exception as e:
            pass

    print(f"{GREEN}{BOLD}All services stopped cleanly. Goodbye!{RESET}")
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, shutdown_all)
    signal.signal(signal.SIGTERM, shutdown_all)

    local_ip = get_local_wifi_ip()

    print(f"""
======================================================================
     AI-PROCTORED ONLINE EXAMINATION SYSTEM - MULTI-STUDENT WI-FI
  MERN Web Platform + Multimodal Computer Vision & Audio AI Engine
======================================================================
  [Host Machine Access]
  * Node Express Backend  : http://localhost:5000
  * Vite React Frontend   : https://localhost:5173
  * FastAPI AI Proctoring : http://localhost:8000

  {GREEN}{BOLD}[Local Wi-Fi Network Access for Students & Teacher]{RESET}
  * Students Exam Portal  : {GREEN}{BOLD}https://{local_ip}:5173{RESET}
  * Teacher Dashboard     : {GREEN}{BOLD}https://{local_ip}:5173/examiner/dashboard{RESET}
  * Backend API (LAN)     : http://{local_ip}:5000/api
  * AI Proctoring (LAN)   : http://{local_ip}:8000/api/ai
======================================================================
  Note: When connecting over Wi-Fi via https://, browsers will show a one-time
  local certificate notice. Click 'Advanced' -> 'Proceed' to enable full camera access.
======================================================================
""")

    # 1. Start Node.js Backend Server
    print(">>> Launching Backend Server on port 5000 (0.0.0.0)...")
    start_service(["npm", "run", "dev"], SERVER_DIR, "SERVER", CYAN)
    time.sleep(2)

    # 2. Start FastAPI AI Proctoring Service
    print(">>> Launching Multimodal AI Proctoring Service on port 8000 (0.0.0.0)...")
    ai_cmd = [sys.executable, "-m", "uvicorn", "proctor_service:app", "--host", "0.0.0.0", "--port", "8000"]
    start_service(ai_cmd, AI_DIR, "AI-ENGINE", MAGENTA)
    time.sleep(2)

    # 3. Start Vite React Frontend
    print(">>> Launching React Frontend on port 5173 (0.0.0.0)...")
    start_service(["npm", "run", "dev"], CLIENT_DIR, "FRONTEND", GREEN)

    print(f"\n{GREEN}{BOLD}[OK] All 3 services are active and ready!{RESET}")
    print(f"Teacher local browser : http://localhost:5173")
    print(f"Students Wi-Fi link   : {CYAN}{BOLD}http://{local_ip}:5173{RESET}")
    print("Press Ctrl+C at any time to cleanly stop all services.\n")

    try:
        while True:
            time.sleep(1)
            # Check if any process terminated unexpectedly
            for prefix, proc in processes:
                if proc.poll() is not None and not shutting_down:
                    print(f"{RED}{BOLD}Notice: {prefix} exited with code {proc.returncode}{RESET}")
    except KeyboardInterrupt:
        shutdown_all()


if __name__ == "__main__":
    main()
