#!/usr/bin/env python3
"""One-command launcher for the Sovereign Hiring Agent demo.

Starts the FastAPI backend (uvicorn, port 8000) and the Next.js frontend
(port 3000) as subprocesses, waits for both to come up, and opens the
browser. Ctrl+C stops both cleanly.
"""
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
BACKEND_URL = "http://localhost:8000/api/job"
FRONTEND_URL = "http://localhost:3000"


def wait_for(url: str, timeout: float, label: str) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.5)
    print(f"[run.py] {label} did not respond within {timeout:.0f}s — check its terminal output above.")
    return False


def main() -> int:
    python = sys.executable
    procs = []
    try:
        print("[run.py] starting backend (uvicorn on :8000)...")
        backend = subprocess.Popen(
            [python, "-m", "uvicorn", "app.main:app", "--port", "8000"],
            cwd=str(BACKEND_DIR),
        )
        procs.append(backend)

        print("[run.py] starting frontend (next dev on :3000)...")
        npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
        frontend = subprocess.Popen([npm_cmd, "run", "dev"], cwd=str(FRONTEND_DIR))
        procs.append(frontend)

        backend_ready = wait_for(BACKEND_URL, 30, "backend")
        frontend_ready = wait_for(FRONTEND_URL, 45, "frontend")

        if backend_ready and frontend_ready:
            print(f"[run.py] both up — opening {FRONTEND_URL}")
            webbrowser.open(FRONTEND_URL)
        else:
            print("[run.py] one or both services didn't come up in time; open "
                  f"{FRONTEND_URL} manually once ready.")

        print("[run.py] press Ctrl+C to stop both.")
        while True:
            time.sleep(1)
            for p in procs:
                if p.poll() is not None:
                    print(f"[run.py] a process exited (code {p.returncode}) — shutting down.")
                    raise KeyboardInterrupt
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=5)
            except Exception:
                p.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
