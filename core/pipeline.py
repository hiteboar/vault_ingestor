from __future__ import annotations
from pathlib import Path
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
) -> tuple[Path, bool, str | None, str | None]:
    """
    Devuelve:
      (path_to_report, is_duplicate, existing_path_if_duplicate, sha256_hex)
    - Si es duplicado: el archivo recién descargado se borra y path_to_report apunta al existente.
    """

    if not any(media.content_type.startswith(p) for p in ALLOWED_PREFIXES):
        raise ValueError(f"Tipo no permitido: {media.content_type}")

    if max_bytes is not None and max_bytes > 0:
        if media.size_bytes is not None and media.size_bytes > max_bytes:
            raise ValueError(f"Archivo demasiado grande: {media.size_bytes} > {max_bytes}")

    # Guardamos primero
    saved_path = save_media(base_dir, media, context=context, fsync=True)

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