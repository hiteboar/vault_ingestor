from __future__ import annotations
import json
import hashlib
from pathlib import Path
from typing import Dict, Optional

def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

class HashIndex:
    """
    Índice simple hash -> ruta guardada en JSON.
    Para MVP es suficiente. Si crece, migramos a SQLite.
    """
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data: Dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._data = {}
            return
        try:
            obj = json.loads(self.path.read_text(encoding="utf-8"))
            self._data = obj if isinstance(obj, dict) else {}
        except Exception:
            self._data = {}

    def _save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def exists(self, hash_hex: str) -> Optional[str]:
        return self._data.get(hash_hex)

    def add(self, hash_hex: str, stored_path: Path) -> None:
        self._data[hash_hex] = str(stored_path)
        self._save()