import os
from pathlib import Path
from dotenv import load_dotenv

from core.housekeeping import cleanup_part_files
from core.state import ChatStateStore
from core.dedup import HashIndex
from adapters.telegram_adapter import TelegramAdapter

def parse_allowed_chat_ids(raw: str) -> set[int] | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    out = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        out.add(int(part))
    return out or None

def parse_bool(raw: str, default: bool) -> bool:
    if raw is None:
        return default
    s = raw.strip().lower()
    if s in ("1", "true", "yes", "y", "on"):
        return True
    if s in ("0", "false", "no", "n", "off"):
        return False
    return default

def main():
    load_dotenv()

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("Falta TELEGRAM_BOT_TOKEN. Copia .env.example a .env y rellénalo.")

    storage_dir = Path(os.getenv("STORAGE_DIR", "./vault_storage")).resolve()
    meta_log = Path(os.getenv("META_LOG", str(storage_dir / "metadata.jsonl"))).resolve()

    max_bytes = int(os.getenv("MAX_BYTES", "0"))
    max_bytes = None if max_bytes <= 0 else max_bytes

    allowed_chat_ids = parse_allowed_chat_ids(os.getenv("ALLOWED_CHAT_IDS", ""))

    default_context = os.getenv("DEFAULT_CONTEXT", "default")

    # DEFAULT global:
    # ALLOW_COMPRESSED_PHOTOS=true  => require_original_default = False
    # ALLOW_COMPRESSED_PHOTOS=false => require_original_default = True
    allow_compressed_default = parse_bool(os.getenv("ALLOW_COMPRESSED_PHOTOS", "true"), True)
    require_original_default = not allow_compressed_default

    storage_dir.mkdir(parents=True, exist_ok=True)
    cleaned = cleanup_part_files(storage_dir)
    if cleaned:
        print(f"[startup] Limpieza: eliminados {cleaned} .part antiguos")

    # Estado por chat (carpeta + original on/off)
    state_path = storage_dir / "state" / "chat_settings.json"
    state_store = ChatStateStore(state_path)

    # Índice dedup
    hash_index = HashIndex(storage_dir / "dedup" / "hash_index.json")

    adapter = TelegramAdapter(
        token=token,
        base_dir=storage_dir,
        meta_log=meta_log,
        state_store=state_store,
        hash_index=hash_index,
        default_context=default_context,
        require_original_default=require_original_default,
        allowed_chat_ids=allowed_chat_ids,
        max_bytes=max_bytes,
    )
    adapter.run()

if __name__ == "__main__":
    main()