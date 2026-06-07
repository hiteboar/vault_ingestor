import os
import sys
import shutil
import zipfile
import io
import json
import subprocess
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import simpledialog

import requests
import ctypes

def is_debug_mode():
    debug_file = BASE_DIR / ".debug"
    return debug_file.exists() or os.environ.get("DEBUG") == "1"

def hide_console():
    if os.name == "nt":
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0) # 0 = SW_HIDE

REPO_URL = "https://github.com/hiteboar/vault_ingestor"
ZIP_URL = f"{REPO_URL}/archive/refs/heads/main.zip"
API_URL = "https://api.github.com/repos/hiteboar/vault_ingestor/commits/main"

if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    # Since we are in a subfolder (version_desktop/), we point to the parent
    BASE_DIR = Path(__file__).resolve().parent.parent

# Ensure core is importable
sys.path.append(str(BASE_DIR))

PROJECT_DIR = BASE_DIR
VERSION_FILE = BASE_DIR / ".version"

def get_python_exe():
    """Returns the real python executable, even if we are in a bundle."""
    if getattr(sys, 'frozen', False):
        # On Windows, we try to use system 'python' or look for an active installation
        return "python" 
    return sys.executable

def log(msg):
    print(f"[*] {msg}")

def get_github_token():
    """Prompts the user for a GitHub token using a simple GUI if needed."""
    token_file = BASE_DIR / ".github_token"
    if token_file.exists():
        return token_file.read_text().strip()
    
    # DEV OVERRIDE: Skip the token prompt to prevent blocking local development testing
    return None

def get_headers():
    """Returns headers including auth if available."""
    headers = {'User-Agent': 'VaultIngestor-Installer'}
    token_file = BASE_DIR / ".github_token"
    if token_file.exists():
        token = token_file.read_text().strip()
        headers['Authorization'] = f"token {token}"
    return headers

def get_latest_remote_hash(retry_auth=True):
    try:
        response = requests.get(API_URL, headers=get_headers(), timeout=10)
        if response.status_code == 200:
            return response.json()["sha"]
        elif response.status_code in (401, 404) and retry_auth:
            log("Access denied (Private or does not exist). Requesting Token...")
            if get_github_token():
                return get_latest_remote_hash(retry_auth=False)
        log(f"GitHub API Error: {response.status_code}")
    except Exception as e:
        log(f"Error checking for updates: {e}")
    return None

def get_local_hash():
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text().strip()
    return None

def download_and_update(latest_hash):
    log("Starting repository download...")
    try:
        response = requests.get(ZIP_URL, headers=get_headers(), timeout=60)
        if response.status_code != 200:
            log(f"Error downloading repository: {response.status_code}")
            return False

        with zipfile.ZipFile(io.BytesIO(response.content)) as zip_ref:
            tmp_extract = BASE_DIR / "_update_tmp"
            if tmp_extract.exists():
                shutil.rmtree(tmp_extract)
            tmp_extract.mkdir(parents=True)
            
            zip_ref.extractall(tmp_extract)
            
            # The folder is usually named vault_ingestor-main
            extracted_roots = [d for d in tmp_extract.iterdir() if d.is_dir()]
            if not extracted_roots:
                log("Corrupt or empty ZIP.")
                return False
            
            extracted_root = extracted_roots[0]
            log(f"Extracting files from {extracted_root.name}...")
            
            IGNORE_LIST = [".env", "vault_storage", "test_data", "_vault", "state", "dedup", ".git", ".venv", "dist"]
            
            for item in extracted_root.iterdir():
                dest = BASE_DIR / item.name
                if item.name in IGNORE_LIST:
                    continue
                
                try:
                    if item.is_dir():
                        if dest.exists():
                            shutil.rmtree(dest)
                        shutil.copytree(item, dest)
                    else:
                        shutil.copy2(item, dest)
                except Exception as e:
                    log(f"Could not copy {item.name}: {e}")
            
            shutil.rmtree(tmp_extract)
            VERSION_FILE.write_text(latest_hash)
            log("Download and extraction completed.")
            return True
    except Exception as e:
        log(f"Critical failure in update: {e}")
    return False

def check_for_updates():
    local_hash = get_local_hash()
    log(f"Local Hash: {local_hash or 'Not installed'}")
    
    remote_hash = get_latest_remote_hash()
    if not remote_hash:
        log("Could not get remote version. Skipping update.")
        return False

    if local_hash != remote_hash:
        log(f"New version available: {remote_hash[:7]}")
        return download_and_update(remote_hash)
    else:
        log("You are already on the latest version.")
        return False

def setup_config():
    """Ensures .env file exists and has required values."""
    env_file = BASE_DIR / ".env"
    example_file = BASE_DIR / ".env.example"
    
    if not env_file.exists():
        if example_file.exists():
            log("Creating initial configuration from .env.example...")
            shutil.copy(example_file, env_file)
            
            # Force remote access enabled for new users
            content = env_file.read_text()
            if "ENABLE_REMOTE_ACCESS" not in content:
                env_file.write_text(content + "\nENABLE_REMOTE_ACCESS=true\n")
            else:
                new_content = content.replace("ENABLE_REMOTE_ACCESS=false", "ENABLE_REMOTE_ACCESS=true")
                env_file.write_text(new_content)
        else:
            log("WARNING: .env nor .env.example found. Using default values.")

def setup_environment():
    venv_dir = BASE_DIR / ".venv"
    req_file = BASE_DIR / "requirements.txt"
    
    if not req_file.exists():
        log("ERROR: requirements.txt not found. Download might have failed.")
        return False

    if not venv_dir.exists():
        log("Creating virtual environment...")
        try:
            subprocess.run([get_python_exe(), "-m", "venv", str(venv_dir)], check=True, capture_output=True, text=True)
        except Exception as e:
            log(f"Error creating venv: {e}")
            return False
    
    pip_exe = str(venv_dir / ("Scripts" if os.name == "nt" else "bin") / "pip")
    log("Installing dependencies (this may take a few minutes)...")
    
    try:
        result = subprocess.run([pip_exe, "install", "-r", str(req_file)], capture_output=True, text=True)
        if result.returncode != 0:
            log(f"Error installing dependencies: {result.stderr}")
            return False
        log("Dependencies installed successfully.")
        return True
    except Exception as e:
        log(f"Failed to install dependencies: {e}")
        return False

def launch_app():
    venv_dir = BASE_DIR / ".venv"
    python_exe = str(venv_dir / ("Scripts" if os.name == "nt" else "bin") / "python")
    
    log("Launching Management Console...")
    # Launch native UI (using correct relative path)
    ui_script = BASE_DIR / "version_desktop" / "console_ui.py"
    
    if os.name == "nt" and not is_debug_mode():
        # Execute with pythonw to avoid extra console dependencies if needed,
        # although the launcher itself already hides its own.
        python_exe = str(venv_dir / "Scripts" / "pythonw.exe")
        subprocess.run([python_exe, str(ui_script)], creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        subprocess.run([python_exe, str(ui_script)])

if __name__ == "__main__":
    try:
        if not is_debug_mode():
            hide_console()
            
        log("=== Vault Ingestor Installer ===")
        
        # 1. Ensure base files
        if not (BASE_DIR / "requirements.txt").exists():
            log("Initial configuration...")
            remote_hash = get_latest_remote_hash()
            if not remote_hash or not download_and_update(remote_hash):
                log("ERROR: Initial installation failed. Check your connection.")
                input("\nPress Enter to close...")
                sys.exit(1)
        else:
            check_for_updates()
        
        # 2. Setup config
        setup_config()
        
        # 3. Setup env
        if not setup_environment():
            log("ERROR: Could not configure environment.")
            input("\nPress Enter to close...")
            sys.exit(1)
        
        # 4. Launch
        launch_app()
    except Exception as e:
        log(f"GLOBAL CRITICAL FAILURE: {str(e)}")
        import traceback
        log(traceback.format_exc())
        input("\nInstaller has failed. Press Enter to close...")
