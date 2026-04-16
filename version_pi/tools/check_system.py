import sys
import os
import platform
import subprocess
import socket

def check_module(module_name):
    try:
        __import__(module_name)
        return True, "✅ Instalado"
    except ImportError as e:
        return False, f"❌ No encontrado ({str(e)})"

def is_venv():
    return sys.prefix != sys.base_prefix

def test_port(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def main():
    print("=== Vault Ingestor: Diagnóstico de Entorno (Raspberry Pi) ===")
    print(f"Sistema Operativo: {platform.system()} {platform.release()}")
    print(f"Versión de Python: {sys.version.split()[0]}")
    print(f"Entorno Virtual: {'✅ Sí' if is_venv() else '⚠️  No (Sistema)'}")
    
    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    print(f"Directorio de Trabajo: {project_dir}")
    print("-" * 40)
    
    modules = [
        "dotenv",           
        "fastapi",
        "uvicorn",
        "PIL",               # Pillow requiere compilacion a veces
        "pycloudflared"      # Vital para el túnel exterior remoto
    ]
    
    print("Módulos Críticos y Dependencias de Red:")
    all_found = True
    for mod in modules:
        found, status = check_module(mod)
        print(f"  - {mod:20}: {status}")
        if not found:
            all_found = False
            
    print("-" * 40)
    print("Estado de Red y Procesos de Vault Ingestor:")
    
    # Comprobar puerto 8000 o 8001
    port_open = test_port(8000) or test_port(8001)
    if port_open:
        print("  - API (8000/8001)       : ✅ Escuchando y listo")
    else:
        print("  - API (8000/8001)       : ⚠️  Cerrado o No Disponible")
        
    print("-" * 40)
    
    if not all_found:
        print("⚠️  Faltan dependencias críticas.")
        print("Por favor, ejecuta ./version_pi/tools/repair_system.sh para dejar todo a punto.")
    else:
        print("✅ Las dependencias operativas clave están correctamente instaladas.")
        print("Para seguir la actividad de red o posibles fallos, revisa en el log maestro:")
        print(f"  tail -n 20 {os.path.join(project_dir, 'app.log')}")

if __name__ == "__main__":
    main()
