"""
AI Online Examination & Multimodal AI Proctoring System
Unified Full-Stack Runner (Node Backend + Vite Client + FastAPI AI Proctoring Engine)
"""

import os
import sys
import time
import signal
import subprocess
import threading
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
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


import socket


def get_local_ip():
    """Detects local LAN/Wi-Fi IPv4 address for multi-device network access."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


def main():
    signal.signal(signal.SIGINT, shutdown_all)
    signal.signal(signal.SIGTERM, shutdown_all)

    local_ip = get_local_ip()

    print(f"""
======================================================================
     AI-PROCTORED ONLINE EXAMINATION SYSTEM - FULL APPLICATION
  MERN Web Platform + Multimodal Computer Vision & Audio AI Engine
======================================================================
  * Local Host Access    : https://localhost:5173
  * Wi-Fi / LAN Network  : https://{local_ip}:5173
  * Node Express Backend : http://localhost:5000 (Internal)
  * FastAPI AI Proctoring: http://localhost:8000 (Internal)
======================================================================
  [MULTI-DEVICE WI-FI INSTRUCTIONS]
  1. Ensure student devices (laptops, phones) are on the SAME Wi-Fi.
  2. On each candidate's browser, open:
     {BOLD}{GREEN}https://{local_ip}:5173{RESET}
  3. When the browser warns "Your connection is not private":
     Click {BOLD}Advanced{RESET} -> {BOLD}Proceed to {local_ip} (unsafe){RESET}.
     (This grants camera/microphone permissions natively on local Wi-Fi!)
  4. Multiple candidates can register and take exams simultaneously!
======================================================================
""")

    # 1. Start Node.js Backend Server
    print(">>> Launching Backend Server on port 5000...")
    start_service(["npm", "run", "dev"], SERVER_DIR, "SERVER", CYAN)
    time.sleep(2)

    # 2. Start FastAPI AI Proctoring Service
    print(">>> Launching Multimodal AI Proctoring Service on port 8000...")
    ai_cmd = [sys.executable, "-m", "uvicorn", "proctor_service:app", "--host", "0.0.0.0", "--port", "8000"]
    start_service(ai_cmd, AI_DIR, "AI-ENGINE", MAGENTA)
    time.sleep(2)

    # 3. Start Vite React Frontend
    print(">>> Launching React Frontend on port 5173 (HTTPS on 0.0.0.0)...")
    start_service(["npm", "run", "dev"], CLIENT_DIR, "FRONTEND", GREEN)

    print("\n[OK] All 3 services are running!")
    print(f"Host machine URL : https://localhost:5173")
    print(f"Wi-Fi student URL: https://{local_ip}:5173")
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
