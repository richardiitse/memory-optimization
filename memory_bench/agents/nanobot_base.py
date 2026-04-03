"""nanobot native memory baseline — no skills loaded."""

import subprocess
import time
import tempfile
import shutil


def run(task: str, timeout: int = 120) -> tuple[float, str]:
    """
    Run nanobot with native memory (no skills).
    Returns (duration_seconds, response_text).
    """
    workspace = tempfile.mkdtemp(prefix="benchmark_base_")
    try:
        start = time.time()
        result = subprocess.run(
            ["python3", "-m", "nanobot", "agent", "-m", task, "-w", workspace],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        duration = time.time() - start
        if result.returncode != 0:
            stderr = result.stderr.strip()
            response = f"[nanobot error {result.returncode}]: {stderr}" if stderr else f"[nanobot error {result.returncode}]"
            return duration, response
        return duration, result.stdout
    finally:
        shutil.rmtree(workspace, onexc=lambda *_: None)
