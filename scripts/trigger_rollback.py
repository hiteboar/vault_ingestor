#!/usr/bin/env python3
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.manager import UpdateManager

def main():
    print("==========================================")
    print("   Vault Ingestor: EMERGENCY ROLLBACK")
    print("==========================================")
    
    storage_dir_str = os.getenv("STORAGE_DIR", "./vault_storage")
    storage_dir = Path(storage_dir_str).resolve()
    
    manager = UpdateManager(PROJECT_ROOT, storage_dir)
    
    print("[!] Fallo crítico reportado por systemd (Crash Loop).")
    print("[*] Iniciando rollback a la última versión estable...")
    
    success, reason = manager.rollback_to_last_stable("Crash loop detectado por systemd (Systemd OnFailure triggered)")
    
    if success:
        print("[✔] Rollback completado.")
        # systemd will try to restart the services eventually if we configure vault_rollback.service correctly,
        # but to be sure, we can trigger a restart explicitly if we want, or just let systemd handle it.
        # It's better to let systemd handle it or we restart them explicitly here.
        import subprocess
        print("[*] Reiniciando servicios para aplicar la versión estable...")
        subprocess.run(["sudo", "systemctl", "reset-failed", "vault_bot", "vault_api"], check=False)
        subprocess.run(["sudo", "systemctl", "restart", "vault_api", "vault_bot"], check=False)
    else:
        print(f"[X] Fallo al hacer rollback: {reason}")
        sys.exit(1)

if __name__ == "__main__":
    main()
