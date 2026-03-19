
import sys
import os
import platform
import subprocess

def check_module(module_name):
    try:
        __import__(module_name)
        return True, "✅ Instalado"
    except ImportError as e:
        return False, f"❌ No encontrado ({str(e)})"

def is_venv():
    return sys.prefix != sys.base_prefix

def main():
    print("=== Vault Ingestor: Diagnóstico de Entorno ===")
    print(f"Sistema Operativo: {platform.system()} {platform.release()}")
    print(f"Versión de Python: {sys.version.split()[0]}")
    print(f"Ejecutable Python: {sys.executable}")
    print(f"Entorno Virtual: {'✅ Sí' if is_venv() else '⚠️  No (Sistema)'}")
    print(f"Directorio de Trabajo: {os.getcwd()}")
    print("-" * 40)
    
    modules = [
        "dotenv",           # python-dotenv
        "telegram",         # python-telegram-bot
        "requests",         # requests
        "google.generativeai" # google-generativeai
    ]
    
    print("Módulos Críticos:")
    all_found = True
    for mod in modules:
        found, status = check_module(mod)
        print(f"  - {mod:20}: {status}")
        if not found:
            all_found = False
            
    print("-" * 40)
    if not all_found:
        if platform.system() == "Linux":
            print("💡 RECOMENDACIÓN PARA RASPBERRY PI:")
            print("Para instalar las dependencias correctamente en Raspberry Pi OS,")
            print("se recomienda usar un entorno virtual (venv) para evitar conflictos:")
            print("\n  1. Crear venv: python -m venv .venv")
            print("  2. Activar:    source .venv/bin/activate")
            print(f"  3. Instalar:   pip install -r requirements.txt")
        else:
            print("⚠️  Faltan dependencias. Por favor, instala las dependencias usando:")
            print(f"  {sys.executable} -m pip install -r requirements.txt")
    else:
        print("✅ Todas las dependencias críticas parecen estar instaladas.")
        
    print("-" * 40)

if __name__ == "__main__":
    main()
