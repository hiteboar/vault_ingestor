import os
import sys
import subprocess
import time
import logging
from logging.handlers import RotatingFileHandler
import traceback
from pathlib import Path

# Setup basic logging with rotation
# maxBytes=5MB, backupCount=3 -> Max total size ~20MB
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        RotatingFileHandler("autorun.log", maxBytes=5*1024*1024, backupCount=3),
        logging.StreamHandler(sys.stdout)
    ]
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
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

def run_app():
    """Starts the stage 2 application."""
    logging.info("Starting Stage 2: Main Application...")
    try:
        # Use Popen to allow monitoring or signal handling if needed
        proc = subprocess.Popen(
            [str(VENV_PYTHON), str(APP_SCRIPT)],
            stdout=sys.stdout,
            stderr=sys.stderr,
            cwd=str(PROJECT_ROOT)
        )
        return proc
    except Exception as e:
        logging.error(f"Failed to start Stage 2: {e}")
        return None

def main():
    logging.info("=== Stage 1: Vault Ingestor Supervisor ===")
    
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
