import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.manager import UpdateManager
from app import is_storage_ready, bootstrap

def main():
    print("==========================================")
    print("   Vault Ingestor: Boot Updater & Health Check")
    print("==========================================")
    
    bootstrap()
    
    storage_dir_str = os.getenv("STORAGE_DIR", "./vault_storage")
    storage_dir = Path(storage_dir_str).resolve()
    
    # 1. Validar Almacenamiento
    storage_ready, storage_error = is_storage_ready(storage_dir)
    if not storage_ready:
        print(f"[!] ADVERTENCIA: El almacenamiento no está listo o montado.")
        print(f"    Razón: {storage_error}")
        print("    Saltando comprobación de actualizaciones para proteger los datos.")
        sys.exit(0)
        
    print(f"[*] Almacenamiento validado correctamente: {storage_dir}")
    
    # 2. Inicializar Gestor de Actualizaciones
    manager = UpdateManager(PROJECT_ROOT, storage_dir)
    
    # 3. Comprobar si hay un test de salud pendiente por un reinicio de actualización
    manager.verify_health_or_rollback()
    
    # 4. Intentar realizar una actualización si hay nuevas versiones en GitHub (Releases)
    manager.perform_boot_update()
    
    print("[*] Proceso de arranque y actualización finalizado.")

if __name__ == "__main__":
    main()
