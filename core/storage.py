import os
import hashlib
from pathlib import Path
from typing import Optional, Dict
from .models import IncomingMedia

CONTENT_TYPE_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
}

def ext_from_content_type(ct: str, formats_dict: Optional[Dict[str, str]] = None) -> str:
    ct = (ct or "").split(";")[0].strip().lower()
    mapping = formats_dict if formats_dict is not None else CONTENT_TYPE_EXT
    return mapping.get(ct, ".bin")

def atomic_write(dest: Path, stream, fsync: bool = True) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.parent.mkdir(parents=True, exist_ok=True)

    with open(tmp, "wb") as f:
        for chunk in stream:
            if not chunk:
                continue
            f.write(chunk)
        f.flush()
        if fsync:
            os.fsync(f.fileno())

    os.replace(tmp, dest)  # rename atómico

def sanitize_context(name: str) -> str:
    # permite letras, números, guiones y underscores; espacios -> "_"
    out = []
    for ch in (name or "").strip():
        if ch.isalnum() or ch in ("-", "_"):
            out.append(ch)
        elif ch.isspace():
            out.append("_")
        else:
            out.append("_")
    s = "".join(out).strip("_")
    return s or "default"

def build_destination(base_dir: Path, media: IncomingMedia, context: str = "default", formats_dict: Optional[Dict[str, str]] = None) -> Path:
    dt = media.received_at
    ctx = sanitize_context(context)

    if ctx == "default":
        bucket_path = Path(f"{dt.year:04d}") / f"{dt.month:02d}"
    else:
        bucket_path = Path(ctx)

    ext = ext_from_content_type(media.content_type, formats_dict=formats_dict)

    # id estable por mensaje/archivo
    seed = f"{media.source}|{media.sender_id}|{media.external_ids}".encode("utf-8", errors="ignore")
    h = hashlib.sha256(seed).hexdigest()[:12]

    filename = f"{h}{ext}"
    return base_dir / bucket_path / filename

def save_media(base_dir: Path, media: IncomingMedia, context: str = "default", fsync: bool = True, formats_dict: Optional[Dict[str, str]] = None) -> Path:
    dest = build_destination(base_dir, media, context=context, formats_dict=formats_dict)
    atomic_write(dest, media.stream, fsync=fsync)
    return dest