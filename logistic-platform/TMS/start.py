"""
FreightBid + eKYC — Single startup script
Run this from the TMS folder:
    python start.py
"""
import subprocess
import sys
import os
import time
import socket
from pathlib import Path

TMS_DIR  = Path(__file__).resolve().parent          # TMS/
PORT_TMS  = 8000
PORT_EKYC = 8002

# ── Find eKYC directory ───────────────────────────────────────────────────────
EKYC_DIR = None
for candidate in [
    Path.home() / "OneDrive" / "Desktop" / "ekyc" / "AI-Native-E-KYC" / "backend",
    Path(f"C:/Users/{os.getenv('USERNAME','hp')}/OneDrive/Desktop/ekyc/AI-Native-E-KYC/backend"),
    TMS_DIR.parent.parent.parent.parent / "ekyc" / "AI-Native-E-KYC" / "backend",
]:
    if candidate.exists():
        EKYC_DIR = candidate
        break

# ── Helper ────────────────────────────────────────────────────────────────────
def port_free(port):
    s = socket.socket()
    result = s.connect_ex(("127.0.0.1", port)) != 0
    s.close()
    return result

def wait_for_port(port, timeout=30):
    for _ in range(timeout * 2):
        s = socket.socket()
        if s.connect_ex(("127.0.0.1", port)) == 0:
            s.close()
            return True
        s.close()
        time.sleep(0.5)
    return False

# ── Start eKYC ────────────────────────────────────────────────────────────────
ekyc_proc = None
if EKYC_DIR:
    if not port_free(PORT_EKYC):
        print(f"[eKYC] Already running on port {PORT_EKYC}")
    else:
        print(f"[eKYC] Starting on port {PORT_EKYC}...")
        ekyc_proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app",
             "--port", str(PORT_EKYC), "--host", "127.0.0.1"],
            cwd=str(EKYC_DIR),
        )
        if wait_for_port(PORT_EKYC, timeout=30):
            print(f"[eKYC] ✅ Ready at http://127.0.0.1:{PORT_EKYC}")
        else:
            print(f"[eKYC] ⚠ Slow to start — TMS will retry via proxy")
else:
    print("[eKYC] Directory not found — skipping")

# ── Start TMS ─────────────────────────────────────────────────────────────────
print(f"\n[TMS]  Starting FreightBid on port {PORT_TMS}...")
print(f"[TMS]  Open browser at: http://localhost:{PORT_TMS}\n")

try:
    tms_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app",
         "--port", str(PORT_TMS), "--host", "127.0.0.1", "--reload"],
        cwd=str(TMS_DIR),
    )
    tms_proc.wait()   # Block until TMS is stopped (Ctrl+C)
except KeyboardInterrupt:
    print("\n[INFO] Shutting down...")
finally:
    if ekyc_proc and ekyc_proc.poll() is None:
        ekyc_proc.terminate()
        print("[eKYC] Stopped")
