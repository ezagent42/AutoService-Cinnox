"""
Core utility functions shared across all layers.
"""

import hashlib
import re
from datetime import datetime
from pathlib import Path


def generate_id(name: str) -> str:
    """Generate a short unique ID (8 characters) based on name and timestamp."""
    content = f"{name}{datetime.now().isoformat()}"
    return hashlib.md5(content.encode()).hexdigest()[:8]


def sanitize_name(name: str) -> str:
    """Convert name to filesystem-safe format.

    Keeps alphanumeric, Chinese characters, and hyphens.
    Replaces other characters with underscores.
    """
    # Remove special characters, keep alphanumeric and Chinese characters
    safe = re.sub(r'[^\w\u4e00-\u9fff-]', '_', name)
    # Remove multiple underscores
    safe = re.sub(r'_+', '_', safe)
    return safe.strip('_')[:30]


def ensure_dir(path: Path) -> Path:
    """Ensure directory exists and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path
