import os
from pathlib import Path
from dotenv import load_dotenv
import uvicorn

def main():
    load_dotenv()

    # Cargar configuración básica
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    storage_dir = Path(os.getenv("STORAGE_DIR", "./vault_storage")).resolve()

    print("==========================================")
    print("   Vault Ingestor - API Service")
    print("==========================================")
    print(f"[*] Storage: {storage_dir}")
    print(f"[*] API: http://{host}:{port}")
    
    # Asegurar que el directorio de almacenamiento existe
    storage_dir.mkdir(parents=True, exist_ok=True)

    # Iniciar el servidor FastAPI
    # El servidor se encuentra en api/main.py bajo el nombre 'app'
    uvicorn.run("api.main:app", host=host, port=port, reload=True)

if __name__ == "__main__":
    main()