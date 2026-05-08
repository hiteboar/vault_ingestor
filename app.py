import os
import sys
import subprocess
from pathlib import Path
from dotenv import load_dotenv
import uvicorn

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

    # 2. Check critical dependencies (only if not in frozen/EXE mode)
    if not getattr(sys, 'frozen', False):
        try:
            import fastapi
            import pycloudflared
        except ImportError:
            print("[*] Installing necessary dependencies...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
                print("[✔] Installation completed.")
            except Exception as e:
                print(f"[!] Error installing dependencies: {e}")

def main():
    bootstrap()
    
    # Load basic configuration
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8001"))
    storage_dir = Path(os.getenv("STORAGE_DIR", "./vault_storage")).resolve()

    print("\n" + "="*42)
    print("      Vault Ingestor - Storage System")
    print("="*42)
    print(f"[*] Storage: {storage_dir}")
    print(f"[*] Local Server: http://{host}:{port}")
    
    # Ensure storage directory exists
    storage_dir.mkdir(parents=True, exist_ok=True)

    # Start FastAPI server
    # The server is located in api/main.py as 'app'
    try:
        uvicorn.run("api.main:app", host=host, port=port, reload=False)
    except KeyboardInterrupt:
        print("\n[*] System stopped by user.")
    except Exception as e:
        print(f"\n[!] Critical error: {e}")

if __name__ == "__main__":
    main()