import sys
import os
import platform
import subprocess
import tkinter as tk
from tkinter import messagebox

def check_module(module_name):
    try:
        __import__(module_name)
        return True, "✅ Instalado"
    except ImportError as e:
        return False, f"❌ No encontrado ({str(e)})"

def is_venv():
    return sys.prefix != sys.base_prefix

def get_diagnostics():
    report = []
    report.append("=== Vault Ingestor: Diagnóstico de Entorno (Desktop) ===")
    report.append(f"Sistema Operativo: {platform.system()} {platform.release()}")
    report.append(f"Versión de Python: {sys.version.split()[0]}")
    report.append(f"Ejecutable Python: {sys.executable}")
    report.append(f"Entorno Virtual: {'✅ Sí' if is_venv() else '⚠️  No (Sistema)'}")
    report.append(f"Directorio de Trabajo: {os.getcwd()}")
    report.append("-" * 40)
    
    modules = [
        "dotenv",           # python-dotenv
        "requests",         # requests
        "webview",          # pywebview
        "uvicorn",          # uvicorn
        "pystray",          # pystray
        "fastapi"           # fastapi
    ]
    
    report.append("Módulos Críticos:")
    all_found = True
    for mod in modules:
        found, status = check_module(mod)
        report.append(f"  - {mod:20}: {status}")
        if not found:
            all_found = False
            
    report.append("-" * 40)
    if not all_found:
        report.append("⚠️  Faltan dependencias. Por favor, asegúrate de haber ejecutado el 'launcher.py' para instalar todo.")
        report.append(f"O instala manualmente usando:\n  {sys.executable} -m pip install -r requirements.txt")
    else:
        report.append("✅ Todas las dependencias críticas parecen estar instaladas.")
        
    report.append("-" * 40)
    return "\n".join(report), all_found

def main():
    report_text, all_found = get_diagnostics()
    
    # Intenta imprimir a consola de forma segura con UTF-8
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        print(report_text)
    except Exception:
        # Fallback sin emojis o ignorando errores de codificación
        print(report_text.encode(sys.stdout.encoding or 'ascii', errors='replace').decode(sys.stdout.encoding or 'ascii'))
    
    # También muestra una ventana de Tkinter
    try:
        root = tk.Tk()
        root.withdraw() # Oculta la ventana principal
        
        if all_found:
            messagebox.showinfo("Diagnóstico - Vault Ingestor", report_text)
        else:
            messagebox.showwarning("Diagnóstico (Faltan Dependencias) - Vault Ingestor", report_text)
        
        root.destroy()
    except Exception as e:
        print(f"No se pudo mostrar la interfaz gráfica: {e}")

if __name__ == "__main__":
    main()
