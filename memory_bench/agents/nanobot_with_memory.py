"""nanobot with memory-optimization skill loaded."""

import subprocess
import time
import tempfile
import shutil
from pathlib import Path

MEMORY_OPT_PATH = Path(__file__).parent.parent.parent  # 项目根目录


def run(task: str, timeout: int = 120) -> tuple[float, str]:
    workspace = tempfile.mkdtemp(prefix="benchmark_mem_")
    workspace_path = Path(workspace)

    # Copy memory-optimization skill into workspace, excluding large/cached dirs
    skills_dir = workspace_path / "skills"
    skills_dir.mkdir()
    memory_skill_dir = skills_dir / "memory-optimization"
    shutil.copytree(
        MEMORY_OPT_PATH,
        memory_skill_dir,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("agents", ".git", "__pycache__", "memory", "tests"),
    )

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
        try:
            shutil.rmtree(workspace)
        except Exception:
            pass
