
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

def get_pip_list():
    try:
        result = subprocess.run([sys.executable, "-m", "pip", "list"], capture_output=True, text=True)
        return result.stdout
    except Exception as e:
        return f"Error ejecutando pip list: {str(e)}"

def main():
    print("=== Vault Ingestor: Diagnóstico de Entorno ===")
    print(f"Sistema Operativo: {platform.system()} {platform.release()}")
    print(f"Versión de Python: {sys.version}")
    print(f"Ejecutable Python: {sys.executable}")
    print(f"Directorio de Trabajo: {os.getcwd()}")
    print("-" * 40)
    
    modules = [
        "dotenv",
        "telegram",
        "requests",
        "google.generativeai"
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
        print("⚠️  Faltan dependencias. Por favor, instala las dependencias usando:")
        print(f"  {sys.executable} -m pip install -r requirements.txt")
    else:
        print("✅ Todas las dependencias críticas parecen estar instaladas.")
        
    print("-" * 40)
    # print("\nLista de paquetes instalados (pip list):")
    # print(get_pip_list())

if __name__ == "__main__":
    main()
