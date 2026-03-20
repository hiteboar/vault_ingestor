import os
import shutil
import pathlib
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)

def get_disk_usage(path: str = ".") -> Dict[str, Any]:
    """Devuelve espacio total, usado y libre en el disco de la ruta especificada."""
    total, used, free = shutil.disk_usage(path)
    return {
        "total_gb": total // (2**30),
        "used_gb": used // (2**30),
        "free_gb": free // (2**30),
        "percent_used": round((used / total) * 100, 2)
    }

def list_vault_structure(base_dir: str) -> Dict[str, Any]:
    """Lista las carpetas de eventos y el número de archivos en cada una."""
    path = pathlib.Path(base_dir)
    if not path.exists():
        return {"error": "El directorio base no existe."}
    
    stats = {"folders": [], "total_files": 0}
    for item in path.iterdir():
        if item.is_dir() and not item.name.startswith((".", "_")):
            count = sum(1 for f in item.iterdir() if f.is_file())
            stats["folders"].append({"name": item.name, "file_count": count})
            stats["total_files"] += count
            
    return stats

def file_operation(operation: str, path: str, target: Optional[str] = None) -> str:
    """Ejecuta operaciones básicas de archivos: rename, delete, compress."""
    p = pathlib.Path(path)
    if not p.exists():
        return f"Error: {path} no existe."
    
    try:
        if operation == "delete":
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
            return f"✅ {path} eliminado con éxito."
            
        elif operation == "rename":
            if not target:
                return "Error: Se requiere un nombre de destino para renombrar."
            p.rename(target)
            return f"✅ {path} renombrado a {target}."
            
        elif operation == "compress":
            if not p.is_dir():
                return "Error: Solo se pueden comprimir carpetas."
            zip_name = target or f"{p.name}.zip"
            # shutil.make_archive añade .zip automáticamente si no está
            shutil.make_archive(zip_name.replace(".zip", ""), 'zip', p)
            return f"✅ {path} comprimido en {zip_name}."
            
        else:
            return f"Error: Operación {operation} no soportada."
            
    except Exception as e:
        return f"❌ Error en operación {operation}: {str(e)}"

def read_project_file(path: str, max_lines: int = 500) -> str:
    """Lee el contenido de un archivo del proyecto."""
    p = pathlib.Path(path)
    if not p.exists() or not p.is_file():
        return f"Error: {path} no es un archivo válido."
    
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
        content = "\n".join(lines[:max_lines])
        if len(lines) > max_lines:
            content += f"\n\n... (truncado, total {len(lines)} líneas)"
        return content
    except Exception as e:
        return f"❌ Error leyendo archivo: {str(e)}"

def write_project_file(path: str, content: str) -> str:
    """Escribe o sobreescribe un archivo en el proyecto."""
    p = pathlib.Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"✅ Archivo escrito con éxito en {path}"
    except Exception as e:
        return f"❌ Error escribiendo archivo: {str(e)}"

def run_system_command(command: str) -> str:
    """Ejecuta un comando de sistema. Úsalo para tareas de administración, ver logs, procesos, etc."""
    import subprocess
    
    # Lista de comandos bloqueados por seguridad crítica
    blocked_patterns = [">", "rm -rf /", ":(){ :|:& };:", "dd if=", "/dev/"]
    
    if any(p in command for p in blocked_patterns):
        return "❌ Error: El comando contiene patrones bloqueados por seguridad."
            
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            capture_output=True, 
            text=True, 
            timeout=60
        )
        output = result.stdout if result.returncode == 0 else result.stderr
        if not output and result.returncode == 0:
            output = "(Comando ejecutado sin salida)"
        return f"--- Output (code {result.returncode}) ---\n{output}"
    except Exception as e:
        return f"❌ Error ejecutando comando: {str(e)}"

def execute_app_command(command: str) -> str:
    """
    Ejecuta un comando interno de Telegram (ej: /invite, /list, /folders, /preview).
    Usa este comando para gestionar el Vault, invitaciones y visualización de archivos.
    """
    # Esta función es un placeholder. El adaptador registrará la implementación real.
    return "Error: Esta herramienta no ha sido enlazada correctamente."

def stage_file(relative_path: str, content: str) -> str:
    """
    Prepara un archivo para una actualización de código. 
    Usa esto para proponer cambios en el código de la aplicación.
    """
    return "Error: Esta herramienta no ha sido enlazada correctamente."

def verify_update() -> str:
    """
    Verifica que los archivos en staging no tengan errores de sintaxis.
    Úsalo después de `stage_file` para asegurar la calidad antes de aplicar.
    """
    return "Error: Esta herramienta no ha sido enlazada correctamente."

def apply_update() -> str:
    """
    Solicita la aplicación definitiva de los cambios de código y el reinicio del sistema.
    Iniciará un proceso de confirmación con el usuario.
    """
    return "Error: Esta herramienta no ha sido enlazada correctamente."
