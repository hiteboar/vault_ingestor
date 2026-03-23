from __future__ import annotations
from pathlib import Path
from typing import Optional, Dict, List
from .models import IncomingMedia
from .storage import save_media
from .metadata import append_jsonl
from .dedup import sha256_file, HashIndex

ALLOWED_PREFIXES = ("image/", "video/")

def process_one(
    base_dir: Path,
    meta_log: Path,
    media: IncomingMedia,
    context: str = "default",
    max_bytes: int | None = None,
    hash_index: HashIndex | None = None,
    formats_dict: Optional[Dict[str, str]] = None,
    allowed_prefixes: Optional[List[str]] = None,
) -> tuple[Path, bool, str | None, str | None]:
    """
    Devuelve:
      (path_to_report, is_duplicate, existing_path_if_duplicate, sha256_hex)
    - Si es duplicado: el archivo recién descargado se borra y path_to_report apunta al existente.
    """

    prefixes = allowed_prefixes if allowed_prefixes is not None else ALLOWED_PREFIXES
    if not any(media.content_type.startswith(p) for p in prefixes):
        # Si no está en los prefijos, checkeamos si está en el mapeo explícito
        valid_formats = formats_dict if formats_dict is not None else {}
        if media.content_type not in valid_formats:
            raise ValueError(f"Tipo no permitido: {media.content_type}")

    if max_bytes is not None and max_bytes > 0:
        if media.size_bytes is not None and media.size_bytes > max_bytes:
            raise ValueError(f"Archivo demasiado grande: {media.size_bytes} > {max_bytes}")

    # Guardamos primero
    saved_path = save_media(base_dir, media, context=context, fsync=True, formats_dict=formats_dict)

    is_dup = False
    existing = None
    file_hash = None
    path_to_report = saved_path

    if hash_index is not None:
        file_hash = sha256_file(saved_path)
        existing = hash_index.exists(file_hash)

        if existing:
            is_dup = True
            # No guardamos duplicado: borramos el recién guardado
            saved_path.unlink(missing_ok=True)
            path_to_report = Path(existing)
        else:
            hash_index.add(file_hash, saved_path)

    append_jsonl(meta_log, {
        "source": media.source,
        "sender_id": media.sender_id,
        "sender_name": media.sender_name,
        "content_type": media.content_type,
        "size_bytes": media.size_bytes,
        "saved_path": str(saved_path),
        "reported_path": str(path_to_report),
        "external_ids": media.external_ids,
        "suggested_filename": media.suggested_filename,
        "received_at": media.received_at.isoformat(),
        "context": context,
        "sha256": file_hash,
        "is_duplicate": is_dup,
        "duplicate_of": existing,
    })

    return path_to_report, is_dup, existing, file_hash