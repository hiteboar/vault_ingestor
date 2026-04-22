import os
import sys
import subprocess
from pathlib import Path
from dotenv import load_dotenv
import uvicorn

def bootstrap():
    """Asegura que el entorno esté listo antes de arrancar."""
    project_dir = Path(__file__).resolve().parent
    env_file = project_dir / ".env"
    example_file = project_dir / ".env.example"

    # 1. Crear .env si no existe
    if not env_file.exists() and example_file.exists():
        print("[*] Configuración inicial: Creando .env...")
        with open(example_file, "r") as f:
            content = f.read()
        # Activar acceso remoto por defecto
        content = content.replace("ENABLE_REMOTE_ACCESS=false", "ENABLE_REMOTE_ACCESS=true")
        if "ENABLE_REMOTE_ACCESS" not in content:
            content += "\nENABLE_REMOTE_ACCESS=true"
        with open(env_file, "w") as f:
            f.write(content)

    load_dotenv()

    # 2. Verificar dependencias críticas (solo si no estamos en modo frozen/EXE)
    if not getattr(sys, 'frozen', False):
        try:
            import fastapi
            import pycloudflared
        except ImportError:
            print("[*] Instalando dependencias necesarias...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
                print("[✔] Instalación completada.")
            except Exception as e:
                print(f"[!] Error instalando dependencias: {e}")

def main():
    bootstrap()
    
    # Cargar configuración básica
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8001"))
    storage_dir = Path(os.getenv("STORAGE_DIR", "./vault_storage")).resolve()

    print("\n" + "="*42)
    print("      Vault Ingestor - Sistema de Almacenaje")
    print("="*42)
    print(f"[*] Almacenamiento: {storage_dir}")
    print(f"[*] Servidor Local: http://{host}:{port}")
    
    # Asegurar que el directorio de almacenamiento existe
    storage_dir.mkdir(parents=True, exist_ok=True)

    # Iniciar el servidor FastAPI
    # El servidor se encuentra en api/main.py bajo el nombre 'app'
    try:
        uvicorn.run("api.main:app", host=host, port=port, reload=False)
    except KeyboardInterrupt:
        print("\n[*] Sistema detenido por el usuario.")
    except Exception as e:
        print(f"\n[!] Error crítico: {e}")

if __name__ == "__main__":
    main()