import os
from pathlib import Path
from dotenv import load_dotenv

from core.housekeeping import cleanup_part_files
from core.state import ChatStateStore
from core.dedup import HashIndex
from core.agent import VaultAgent
from core.manager import UpdateManager
from adapters.telegram_adapter import TelegramAdapter

def is_storage_ready(path: Path) -> tuple[bool, str]:
    """
    Verifica si el directorio de almacenamiento es válido y está montado
    si se detecta que es una ruta absoluta fuera del home (típico de /mnt o /media).
    """
    path_str = str(path.resolve())
    
    # 1. Verificar si existe la carpeta básica
    if not path.exists():
        try:
            path.mkdir(parents=True, exist_ok=True)
            return True, "✅ Carpeta creada (no parece un montaje externo)."
        except Exception as e:
            return False, f"❌ No se pudo crear la carpeta: {e}"

    # 2. Si es una ruta de montaje típica (/mnt, /media, o discos en Windows como D:\)
    # verificamos si realmente hay un disco montado.
    is_external = any(path_str.startswith(p) for p in ["/mnt/", "/media/", "/run/media/"])
    # En Windows, una ruta absoluta que no sea C: podría considerarse externa
    if os.name == 'nt' and not path_str.lower().startswith("c:"):
        is_external = True

    if is_external:
        # os.path.ismount no siempre es fiable con FUSE/Network drives, 
        # pero es la mejor opción estándar.
        if hasattr(os.path, 'ismount') and not os.path.ismount(path_str):
            # Verificación extra: si la carpeta está totalmente vacía y es un punto de montaje,
            # es muy probable que el disco no esté montado.
            try:
                if not any(path.iterdir()):
                    return False, f"⚠️ ERROR: La ruta {path_str} parece un disco externo pero NO está montado."
            except Exception:
                return False, f"⚠️ ERROR: No se puede acceder a la ruta de montaje {path_str}."
    
    return True, "✅ Almacenamiento listo."

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

    # Validación de Almacenamiento y Modo Reducido
    storage_ok, storage_msg = is_storage_ready(storage_dir)
    reduced_mode = not storage_ok
    print(f"[startup] {storage_msg}")
    if reduced_mode:
        print("[warning] Iniciando en MODO REDUCIDO. El bot solo informará del error.")

    if not reduced_mode:
        storage_dir.mkdir(parents=True, exist_ok=True)
        cleaned = cleanup_part_files(storage_dir)
        if cleaned:
            print(f"[startup] Limpieza: eliminados {cleaned} .part antiguos")

    # Estado por chat (carpeta + original on/off)
    state_path = storage_dir / "state" / "chat_settings.json"
    state_store = ChatStateStore(state_path)

    # Índice dedup
    hash_index = HashIndex(storage_dir / "dedup" / "hash_index.json")

    # Agente IA (Opcional si hay API KEY)
    from core.agent import DEFAULT_MODEL
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    ai_model = os.getenv("AI_MODEL", "").strip() or DEFAULT_MODEL
    stored_model = state_store.get_global_setting("agent_model", ai_model)
    
    agent = None
    if gemini_key:
        agent = VaultAgent(gemini_key, model_name=stored_model, storage_dir=str(storage_dir))
        # Validar el modelo actual
        if not agent.test_model():
            print(f"[warning] Modelo '{stored_model}' no disponible. Reintentando con default...")
            agent.set_model(DEFAULT_MODEL)
            if agent.test_model():
                print(f"[startup] Agente IA reconfigurado con default ({DEFAULT_MODEL}).")
                state_store.set_global_setting("agent_model", DEFAULT_MODEL)
            else:
                print("[error] Ni siquiera el modelo default funciona. Desactivando agente.")
                agent = None
        
        if agent:
            print(f"[startup] Agente IA configurado ({agent.model_name}).")
    else:
        print("[startup] Agente IA no disponible (falta GEMINI_API_KEY).")

    # Gestor de actualizaciones
    update_manager = UpdateManager(Path(".").resolve(), storage_dir)

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
        agent=agent,
        update_manager=update_manager,
        env_path=Path(".env").resolve(),
        reduced_mode=reduced_mode,
        reduced_mode_error=storage_msg if reduced_mode else None
    )
    adapter.run()

if __name__ == "__main__":
    main()