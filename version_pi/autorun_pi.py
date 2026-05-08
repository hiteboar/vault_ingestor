import os
import sys
import subprocess
import time
import logging
from logging.handlers import RotatingFileHandler
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_FILE = PROJECT_ROOT / "app.log"

# Setup basic logging with rotation
# maxBytes=5MB, backupCount=3 -> Max total size ~20MB
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        RotatingFileHandler(str(LOG_FILE), maxBytes=5*1024*1024, backupCount=3),
        logging.StreamHandler(sys.stdout)
    ]
)

APP_SCRIPT = PROJECT_ROOT / "app.py"
VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"


if not VENV_PYTHON.exists():
    VENV_PYTHON = Path(sys.executable) # Fallback

def notify_admin(message):
    """
    Hook for admin notifications.
    Ready to be extended (e.g. for Telegram) in non-main branches.
    """
    logging.info(f"[NOTIFY] {message}")
    # TODO: Implement external tool call here if needed

import threading

def check_for_updates():
    logging.info("Checking for updates on MobileApp_prod branch...")
    try:
        # Check connection by fetching metadata. Returns error code if no wifi/internet
        subprocess.run(["git", "fetch", "origin", "MobileApp_prod"], check=True, cwd=str(PROJECT_ROOT), capture_output=True)
        # Compare status against official tracking
        status = subprocess.check_output(["git", "status", "-uno"], cwd=str(PROJECT_ROOT), text=True)
        if hasattr(status, "lower") and "your branch is behind" in status.lower():
             logging.info("Update detected! Local branch is behind origin/MobileApp_prod.")
             return True
        return False
    except Exception as e:
        logging.warning("Offline or error during update check. Skipping update protocol.")
        return False

def apply_updates():
    logging.info("Auto-Updating components from MobileApp_prod...")
    try:
        # Force sync (git fetch already did it but just in case) to avoid visual merge conflicts
        subprocess.run(["git", "reset", "--hard", "origin/MobileApp_prod"], check=True, cwd=str(PROJECT_ROOT), capture_output=True)
        logging.info("Pull complete. Running setup_pi.sh for new dependencies...")
        subprocess.run(["bash", "version_pi/setup_pi.sh"], check=True, cwd=str(PROJECT_ROOT), capture_output=True)
        logging.info("Successfully updated Vault Ingestor via Auto-Updater.")
    except Exception as e:
        logging.error(f"Critical failure applying update: {e}. Attempting boot anyway.")

def stream_to_logger(pipe, level):
    for line in iter(pipe.readline, b''):
        try:
            line_str = line.decode('utf-8', errors='replace').rstrip()
            if line_str:
                logging.log(level, line_str)
        except Exception:
            pass

def run_app():
    """Starts the stage 2 application."""
    logging.info("Starting Stage 2: Main Application...")
    try:
        proc = subprocess.Popen(
            [str(VENV_PYTHON), str(APP_SCRIPT)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(PROJECT_ROOT),
            bufsize=1
        )
        
        # Start threads to capture and log all output and errors from app.py
        threading.Thread(target=stream_to_logger, args=(proc.stdout, logging.INFO), daemon=True).start()
        threading.Thread(target=stream_to_logger, args=(proc.stderr, logging.ERROR), daemon=True).start()
        
        return proc
    except Exception as e:
        logging.error(f"Failed to start Stage 2: {e}")
        return None

def main():
    logging.info("=== Stage 1: Vault Ingestor Supervisor ===")
    
    # 0. Boot Phase Auto-Updater
    if check_for_updates():
         apply_updates()
    else:
         logging.info("No updates required. System is proceeding with boot.")
    
    max_retries = 2
    retry_delay = 10 # seconds
    
    for attempt in range(1, max_retries + 1):
        logging.info(f"Attempt {attempt}/{max_retries}...")
        
        proc = run_app()
        if proc:
            exit_code = proc.wait()
            if exit_code == 0:
                logging.info("Application exited successfully.")
                sys.exit(0)
            else:
                msg = f"Application crashed with exit code {exit_code} (Attempt {attempt})."
                logging.error(msg)
                notify_admin(msg)
        else:
            msg = f"Could not start application (Attempt {attempt})."
            logging.error(msg)
            notify_admin(msg)
            
        if attempt < max_retries:
            logging.info(f"Waiting {retry_delay}s before retry...")
            time.sleep(retry_delay)
            
    # If we reached here, both attempts failed
    msg = "CRITICAL: Application failed after 2 attempts. Entering Diagnostic Mode."
    logging.error(msg)
    notify_admin(msg)
    
    # Diagnostic Mode: Stay alive for SSH access
    logging.info("Supervisor will remain active. You can now connect via SSH to debug.")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        logging.info("Supervisor stopped by user.")

if __name__ == "__main__":
    main()
