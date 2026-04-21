"""Shared utilities for memory optimization scripts."""

import logging
import math
import os
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b):
        logger.warning(
            "Dimension mismatch in cosine_similarity: %d vs %d", len(a), len(b)
        )
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def load_dotenv(env_path: Optional[str] = None) -> None:
    """Load environment variables from a .env file.

    Empty values (KEY=) are set to '' in os.environ to distinguish
    "explicitly empty" from "not set at all".

    Args:
        env_path: Explicit path to .env file. If None, searches upward
                  from the script directory to find a .env file.
    """
    if env_path:
        target = Path(env_path)
    else:
        # Walk upward from this file to find project root .env
        current = Path(__file__).resolve().parent
        target = None
        for _ in range(5):
            candidate = current / '.env'
            if candidate.exists():
                target = candidate
                break
            current = current.parent
        if target is None:
            return

    if not target.exists():
        return

    with open(target, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
