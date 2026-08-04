import os
import shutil
import sys
import json
import logging
import subprocess
import requests
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

class UpdateManager:
    def __init__(self, base_dir: Path, storage_dir: Path):
        self.base_dir = base_dir.resolve()
        self.storage_dir = storage_dir.resolve()
        
        # New safe offline backup location inside the Pi (not tracked by git)
        # Using a hidden folder in the base dir
        self.backups_dir = self.base_dir / ".vault_backup_last_good"
        self.state_file = self.storage_dir / "state" / "update_state.json"
        
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

    def _get_state(self) -> dict:
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "last_stable": "Ninguna", 
            "pending_verification": False,
            "verification_failed": False,
            "last_error": None,
            "current_version": "unknown"
        }

    def _set_state(self, state: dict):
        self.state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def create_local_backup(self) -> str:
        """Crea una copia de seguridad OFFLINE de todo el sistema (excluyendo almacenamiento de medios)."""
        logger.info("[Updater] Creando copia de seguridad local offline...")
        
        # Limpiar backup anterior
        if self.backups_dir.exists():
            for item in self.backups_dir.iterdir():
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink(missing_ok=True)
        else:
            self.backups_dir.mkdir(parents=True, exist_ok=True)

        items_to_backup = [
            "core", "api", "adapters", "scripts", "version_pi",
            "app.py", "requirements.txt", ".env", "run_vault.sh", "install_vault.sh",
            "vault_internal"
        ]

        for item_name in items_to_backup:
            src = self.base_dir / item_name
            dst = self.backups_dir / item_name
            if src.exists():
                try:
                    if src.is_dir():
                        shutil.copytree(src, dst, dirs_exist_ok=True)
                    else:
                        shutil.copy2(src, dst)
                except Exception as e:
                    logger.warning(f"[Updater] Fallo al respaldar {item_name}: {e}")

        state = self._get_state()
        state["last_stable"] = datetime.now().isoformat()
        self._set_state(state)
        
        logger.info(f"[Updater] Backup creado correctamente en {self.backups_dir}")
        return str(self.backups_dir)

    def check_git_updates(self, target_tag: str = None) -> tuple[bool, str]:
        """Comprueba si hay una nueva versión en GitHub.
        Si se especifica target_tag, comprueba la existencia de ese tag (sea o no Release).
        """
        if target_tag:
            logger.info(f"[Updater] Comprobando existencia del Git Tag: {target_tag}...")
            api_url = f"https://api.github.com/repos/hiteboar/vault_ingestor/git/refs/tags/{target_tag}"
        else:
            logger.info("[Updater] Comprobando última Release en GitHub...")
            api_url = "https://api.github.com/repos/hiteboar/vault_ingestor/releases/latest"
            
        try:
            response = requests.get(api_url, timeout=10)
            if response.status_code == 200:
                release_data = response.json()
                
                if target_tag:
                    remote_tag = target_tag
                else:
                    remote_tag = release_data.get("tag_name")
                
                state = self._get_state()
                local_tag = state.get("current_version", "unknown")
                
                if target_tag:
                    logger.info(f"[Updater] Tag '{remote_tag}' encontrado con éxito.")
                    return True, remote_tag
                elif remote_tag and remote_tag != local_tag:
                    logger.info(f"[Updater] Nueva versión detectada: {remote_tag} (Actual: {local_tag})")
                    return True, remote_tag
                else:
                    logger.info("[Updater] El sistema ya está en la última versión.")
                    return False, local_tag
            elif response.status_code == 404 and target_tag:
                logger.warning(f"[Updater] El tag {target_tag} no existe en el repositorio remoto.")
                return False, "not_found"
            else:
                logger.warning(f"[Updater] GitHub API devolvió status {response.status_code}")
        except Exception as e:
            logger.error(f"[Updater] Error comprobando actualizaciones en GitHub: {e}")
            
        return False, "unknown"

    def perform_boot_update(self):
        """Ejecuta el flujo de actualización al inicio del sistema."""
        has_updates, new_tag = self.check_git_updates()
        if not has_updates:
            return

        logger.info(f"[Updater] Iniciando actualización a la versión {new_tag}...")
        print(f"[*] Descargando nueva versión: {new_tag}")
        
        # 1. Backup local
        self.create_local_backup()
        
        # 2. Actualizar vía git fetch --tags y checkout
        try:
            # Traer tags
            subprocess.run(["git", "fetch", "--tags"], cwd=str(self.base_dir), check=True, capture_output=True)
            # Mover a la etiqueta específica (detached HEAD)
            subprocess.run(["git", "checkout", new_tag], cwd=str(self.base_dir), check=True, capture_output=True)
            
            # 3. Marcar estado para chequeo de salud
            state = self._get_state()
            state["pending_verification"] = True
            state["current_version"] = new_tag
            self._set_state(state)
            
            # 4. Actualizar dependencias si es necesario
            venv_pip = self.base_dir / ".venv" / "bin" / "pip"
            if venv_pip.exists():
                logger.info("[Updater] Actualizando dependencias de Python...")
                subprocess.run([str(venv_pip), "install", "-r", "requirements.txt"], cwd=str(self.base_dir), check=False)
                
            logger.info("[Updater] Actualización aplicada. Reiniciando para verificación de salud.")
            # Reiniciar de forma limpia saliendo con código que systemd detecta, o execv
            self.restart()
            
        except Exception as e:
            logger.error(f"[Updater] Error crítico durante git checkout: {e}")
            self.rollback_to_last_stable(f"Fallo al aplicar git checkout: {e}")

    def verify_health_or_rollback(self):
        """Si hay una actualización pendiente de verificar, realiza test de salud."""
        state = self._get_state()
        if not state.get("pending_verification"):
            return

        logger.info("[Updater] Ejecutando tests de salud post-actualización...")
        print("[*] Verificando estabilidad de la nueva versión...")
        try:
            # Test 1: Syntax check en archivos principales
            for py_file in ["app.py", "core/manager.py", "api/main.py"]:
                target = self.base_dir / py_file
                if target.exists():
                    subprocess.run([sys.executable, "-m", "py_compile", str(target)], check=True, capture_output=True)
            
            # Test 2: Intento de importación de módulos clave
            check_script = "import core.agent; import adapters.telegram_adapter; print('OK')"
            res = subprocess.run([sys.executable, "-c", check_script], cwd=str(self.base_dir), capture_output=True, text=True)
            if res.returncode != 0:
                raise Exception(f"Error de imports: {res.stderr}")
                
            # Si llegamos aquí, salud OK
            logger.info("[Updater] Tests de salud SUPERADOS. Actualización estable.")
            print("[✔] La nueva versión funciona correctamente.")
            state["pending_verification"] = False
            state["verification_failed"] = False
            self._set_state(state)
            
        except Exception as e:
            logger.error(f"[Updater] Tests de salud FALLARON. Iniciando auto-rollback. Razón: {e}")
            self.rollback_to_last_stable(f"Fallo en tests de salud: {str(e)}")

    def rollback_to_last_stable(self, reason: str = "Desconocida") -> tuple[bool, str]:
        """Restaura la última versión estable sin usar GitHub (OFFLINE)."""
        logger.warning(f"[Updater] ROLLBACK INICIADO. Motivo: {reason}")
        print(f"[!] Fallo crítico detectado: {reason}. Iniciando Rollback automático...")
        
        if not self.backups_dir.exists() or not any(self.backups_dir.iterdir()):
            err = "No hay copia de seguridad local disponible para restaurar."
            logger.error(err)
            return False, err
            
        try:
            # Sobrescribir archivos desde la copia de seguridad
            for item in self.backups_dir.iterdir():
                dst = self.base_dir / item.name
                if item.is_dir():
                    if dst.exists():
                        shutil.rmtree(dst, ignore_errors=True)
                    shutil.copytree(item, dst)
                else:
                    shutil.copy2(item, dst)
            
            # Restablecer dependencias si es necesario
            venv_pip = self.base_dir / ".venv" / "bin" / "pip"
            if venv_pip.exists():
                subprocess.run([str(venv_pip), "install", "-r", "requirements.txt"], cwd=str(self.base_dir), check=False)
                
            # Actualizar estado
            state = self._get_state()
            state["pending_verification"] = False
            state["verification_failed"] = True
            state["last_error"] = reason
            state["current_version"] = "unknown (rolled back)"
            self._set_state(state)
            
            logger.info("[Updater] Rollback completado con éxito.")
            print("[✔] Rollback exitoso. Sistema restaurado a versión estable.")
            return True, "Sistema restaurado a la versión estable."
            
        except Exception as e:
            err = f"Fallo crítico durante el rollback: {e}"
            logger.error(err)
            return False, err

    def restart(self):
        """Reinicia el proceso actual."""
        os.execv(sys.executable, [sys.executable] + sys.argv)

