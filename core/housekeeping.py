from __future__ import annotations
from pathlib import Path
import time

def cleanup_part_files(base_dir: Path, older_than_seconds: int = 24 * 3600) -> int:
    now = time.time()
    count = 0
    for p in base_dir.rglob("*.part"):
        try:
            if now - p.stat().st_mtime > older_than_seconds:
                p.unlink(missing_ok=True)
                count += 1
        except Exception:
            pass
    return count