import os
import sys
import subprocess
import threading
from pathlib import Path
from dotenv import load_dotenv
import uvicorn
import time

def is_storage_ready(path: Path) -> tuple[bool, str]:
    """
    Checks if the storage path is valid, mounted (if applicable), and writable.
    Returns (True, "") or (False, "Error message").
    """
    try:
        # 1. Existence check
        if not path.exists():
            try:
                path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                return False, f"La carpeta no existe y no pudo crearse: {e}"

        # 2. Mount check (Linux only, for paths in /mnt or /media)
        if os.name == "posix":
            p_str = str(path.resolve())
            if p_str.startswith("/mnt/") or p_str.startswith("/media/"):
                if not os.path.ismount(p_str):
                    # Check if it's empty. If it's not empty, maybe it IS the drive but ismount fails?
                    # Usually better to trust ismount or check for a hidden .vault file.
                    if not any(path.iterdir()):
                        return False, f"El punto de montaje {p_str} existe pero NO está montado."

        # 3. Writable check
        test_file = path / ".write_test"
        try:
            test_file.touch()
            test_file.unlink()
        except Exception as e:
            return False, f"El almacenamiento no tiene permisos de escritura: {e}"

        return True, ""
    except Exception as e:
        return False, f"Error validando almacenamiento: {e}"

def bootstrap():
    """Ensures the environment is ready before starting."""
    project_dir = Path(__file__).resolve().parent
    env_file = project_dir / ".env"
    example_file = project_dir / ".env.example"

    # 1. Create .env if it doesn't exist
    if not env_file.exists() and example_file.exists():
        print("[*] Initial configuration: Creating .env...")
        with open(example_file, "r") as f:
            content = f.read()
        # Enable remote access by default
        content = content.replace("ENABLE_REMOTE_ACCESS=false", "ENABLE_REMOTE_ACCESS=true")
        if "ENABLE_REMOTE_ACCESS" not in content:
            content += "\nENABLE_REMOTE_ACCESS=true"
        with open(env_file, "w") as f:
            f.write(content)

    load_dotenv()

    # 2. Check critical dependencies
    if not getattr(sys, 'frozen', False):
        if os.getenv("VAULT_NO_AUTOINSTALL", "false").lower() == "true":
            return

        try:
            import fastapi
            import pycloudflared
            import telegram
        except ImportError:
            # Prevent multiple processes from installing at the same time
            lock_file = project_dir / ".pip_install.lock"
            if lock_file.exists():
                print("[*] Another process is installing dependencies. Waiting...")
                for _ in range(30):
                    time.sleep(2)
                    if not lock_file.exists():
                        return
                print("[!] Timeout waiting for other installation. Proceeding with caution.")

            try:
                lock_file.touch()
                print("[*] Installing necessary dependencies...")
                subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
                print("[✔] Installation completed.")
            except Exception as e:
                print(f"[!] Error installing dependencies: {e}")
            finally:
                if lock_file.exists():
                    lock_file.unlink()

def run_telegram_bot(storage_dir, meta_log, reduced_mode=False, reduced_mode_error=None):
    """Initializes and runs the Telegram Bot in a separate thread."""
    import asyncio
    # Create and set a new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        from core.housekeeping import cleanup_part_files
        from core.state import ChatStateStore
        from core.dedup import HashIndex
        from core.manager import UpdateManager
        from adapters.telegram_adapter import TelegramAdapter

        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            print("[telegram] Skip: No TELEGRAM_BOT_TOKEN found.")
            return

        # Configuration
        max_bytes = int(os.getenv("MAX_BYTES", "0"))
        max_bytes = None if max_bytes <= 0 else max_bytes

        def parse_allowed_chat_ids(raw: str) -> set[int] | None:
            raw = (raw or "").strip()
            if not raw: return None
            return {int(part.strip()) for part in raw.split(",") if part.strip()}

        allowed_chat_ids = parse_allowed_chat_ids(os.getenv("ALLOWED_CHAT_IDS", ""))
        default_context = os.getenv("DEFAULT_CONTEXT", "root") # Align with MobileApp 'root'

        def parse_bool(raw: str, default: bool) -> bool:
            if raw is None: return default
            s = raw.strip().lower()
            if s in ("1", "true", "yes", "on"): return True
            if s in ("0", "false", "no", "off"): return False
            return default

        allow_compressed_default = parse_bool(os.getenv("ALLOW_COMPRESSED_PHOTOS", "true"), True)
        require_original_default = not allow_compressed_default

        # Initialize components
        storage_dir.mkdir(parents=True, exist_ok=True)
        cleanup_part_files(storage_dir)

        state_path = storage_dir / "state" / "chat_settings.json"
        state_store = ChatStateStore(state_path)
        hash_index = HashIndex(storage_dir / "dedup" / "hash_index.json")


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
            update_manager=update_manager,
            env_path=Path(".env").resolve(),
            reduced_mode=reduced_mode,
            reduced_mode_error=reduced_mode_error
        )
        print("[telegram] Bot starting...")
        adapter.run()
    except Exception as e:
        print(f"[telegram] Critical error: {e}")

def main():
    bootstrap()
    
    import argparse
    parser = argparse.ArgumentParser(description="Vault Ingestor Dual System")
    parser.add_argument("--mode", choices=["api", "bot", "both"], default="both", help="Execution mode")
    args_parsed = parser.parse_args()

    # Load basic configuration
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8001"))
    storage_dir = Path(os.getenv("STORAGE_DIR", "./vault_storage")).resolve()
    meta_log = Path(os.getenv("META_LOG", str(storage_dir / "metadata.jsonl"))).resolve()

    print("\n" + "="*42)
    print(f"      Vault Ingestor - Mode: {args_parsed.mode.upper()}")
    print("="*42)
    print(f"[*] Storage: {storage_dir}")
    
    # Validate storage
    storage_ready, storage_error = is_storage_ready(storage_dir)
    reduced_mode = not storage_ready
    
    if reduced_mode:
        print(f"\n[!] STORAGE WARNING: {storage_error}")
        print("[!] Bot will start in REDUCED MODE.")

    if args_parsed.mode == "bot":
        print(f"[*] Starting Telegram Bot (Main Thread)...")
        run_telegram_bot(storage_dir, meta_log, reduced_mode, storage_error)
    elif args_parsed.mode == "both":
        print(f"[*] Starting Telegram Bot (Background Thread)...")
        threading.Thread(target=run_telegram_bot, args=(storage_dir, meta_log, reduced_mode, storage_error), daemon=True).start()
        
        print(f"[*] Starting Local API: http://{host}:{port}")
        try:
            uvicorn.run("api.main:app", host=host, port=port, reload=False)
        except KeyboardInterrupt:
            print("\n[*] API stopped by user.")
        except Exception as e:
            print(f"\n[!] API Critical error: {e}")
    elif args_parsed.mode == "api":
        print(f"[*] Starting Local API: http://{host}:{port}")
        try:
            uvicorn.run("api.main:app", host=host, port=port, reload=False)
        except KeyboardInterrupt:
            print("\n[*] API stopped by user.")
        except Exception as e:
            print(f"\n[!] API Critical error: {e}")

if __name__ == "__main__":
    main()