import os
import shutil
import sys
import json
import logging
import subprocess
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

class UpdateManager:
    def __init__(self, base_dir: Path, storage_dir: Path):
        self.base_dir = base_dir
        self.storage_dir = storage_dir
        self.backups_dir = storage_dir / "backups"
        self.staging_dir = storage_dir / "staging"
        self.state_file = storage_dir / "state" / "update_state.json"
        
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

    def _get_state(self):
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text())
            except:
                pass
        return {"last_stable": None, "pending_update": None}

    def _set_state(self, state):
        self.state_file.write_text(json.dumps(state, indent=2))

    def create_backup(self, tag: str = None) -> str:
        """Crea un backup de la versión actual del código."""
        if not tag:
            tag = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        backup_path = self.backups_dir / f"backup_{tag}"
        backup_path.mkdir(parents=True, exist_ok=True)
        
        # Archivos/carpetas a incluir en el backup
        items_to_backup = ["core", "adapters", "app.py", "requirements.txt"]
        
        for item in items_to_backup:
            src = self.base_dir / item
            if src.exists():
                dst = backup_path / item
                if src.is_dir():
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dst)
        
        state = self._get_state()
        state["last_stable"] = str(backup_path)
        self._set_state(state)
        
        logger.info(f"Backup creado en: {backup_path}")
        return str(backup_path)

    def stage_file(self, relative_path: str, content: str):
        """Prepara un archivo en el área de staging."""
        dst = self.staging_dir / relative_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(content, encoding="utf-8")
        logger.info(f"Archivo estadiado: {relative_path}")

    def verify_staging(self) -> tuple[bool, str]:
        """Verifica que el código en staging sea válido (sintaxis)."""
        # Por ahora, check de sintaxis simple para archivos .py
        errors = []
        for p in self.staging_dir.rglob("*.py"):
            try:
                subprocess.run([sys.executable, "-m", "py_compile", str(p)], check=True, capture_output=True)
            except subprocess.CalledProcessError as e:
                errors.append(f"Error en {p.relative_to(self.staging_dir)}: {e.stderr.decode()}")
        
        if errors:
            return False, "\n".join(errors)
        return True, "Verificación exitosa."

    def apply_update(self) -> bool:
        """Aplica los archivos de staging al directorio principal y reinicia."""
        # 1. Crear backup de seguridad antes de aplicar
        self.create_backup("pre_update")
        
        # 2. Copiar archivos de staging al root
        for item in self.staging_dir.iterdir():
            dst = self.base_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dst)
        
        # 3. Limpiar staging
        shutil.rmtree(self.staging_dir)
        self.staging_dir.mkdir()
        
        logger.info("Update aplicado. Reiniciando...")
        return True

    def rollback(self) -> tuple[bool, str]:
        """Restaura la última versión estable."""
        state = self._get_state()
        backup_path_str = state.get("last_stable")
        
        if not backup_path_str:
            return False, "No hay backup estable registrado."
            
        backup_path = Path(backup_path_str)
        if not backup_path.exists():
            return False, f"El backup en {backup_path} no existe."
            
        # Restaurar
        for item in backup_path.iterdir():
            dst = self.base_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dst)
                
        logger.info("Rollback completado. Reiniciando...")
        return True, "Sistema restaurado a la versión estable."

    def restart(self):
        """Reinicia el proceso actual."""
        os.execv(sys.executable, [sys.executable] + sys.argv)
