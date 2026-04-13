import json
import os
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional

import psutil
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="Vault API & Dashboard")

# Enable CORS for the webapp and desktop console
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Expand for production if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent.parent
# We look for storage_dir in env or use default
from dotenv import load_dotenv, set_key
load_dotenv()

STORAGE_DIR = Path(os.getenv("STORAGE_DIR", str(BASE_DIR / "vault_storage"))).resolve()
META_LOG = Path(os.getenv("META_LOG", str(STORAGE_DIR / "metadata.jsonl"))).resolve()
ENV_PATH = BASE_DIR / ".env"

class ConfigUpdate(BaseModel):
    key: str
    value: str

@app.get("/api/items")
async def get_items():
    if not META_LOG.exists():
        return []
    
    items = []
    try:
        with open(META_LOG, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        item = json.loads(line)
                        # Convert absolute saved_path to a relative path from BASE_DIR
                        saved_path = Path(item["saved_path"])
                        try:
                            rel = saved_path.relative_to(BASE_DIR)
                            item["web_path"] = str(rel).replace("\\", "/")
                        except ValueError:
                            item["web_path"] = saved_path.name
                        items.append(item)
                    except Exception:
                        continue
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    return list(reversed(items))

@app.get("/api/system/status")
async def get_system_status():
    """Returns disk usage, RAM, and CPU info."""
    try:
        # Disk usage for the storage directory
        # If it doesn't exist, use the directory containing it
        check_path = STORAGE_DIR if STORAGE_DIR.exists() else STORAGE_DIR.parent
        usage = shutil.disk_usage(check_path)
        
        # CPU & RAM
        cpu_pct = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory()

        # Vault specific stats
        file_count = 0
        total_size = 0
        if STORAGE_DIR.exists():
            for p in STORAGE_DIR.rglob("*"):
                if p.is_file() and not "_tmp" in p.parts:
                    file_count += 1
                    total_size += p.stat().st_size

        return {
            "disk": {
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "percent": (usage.used / usage.total) * 100 if usage.total > 0 else 0
            },
            "ram": {
                "total": ram.total,
                "used": ram.used,
                "free": ram.available,
                "percent": ram.percent
            },
            "cpu": {
                "percent": cpu_pct
            },
            "vault": {
                "file_count": file_count,
                "total_size": total_size,
                "storage_path": str(STORAGE_DIR)
            },
            "status": "healthy"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/system/logs")
async def get_logs(lines: int = 50):
    """Returns the last N lines of the metadata log or system logs."""
    # For now, we return the metadata log as activity log
    if not META_LOG.exists():
        return []
    
    try:
        with open(META_LOG, "r", encoding="utf-8") as f:
            content = f.readlines()
            return [json.loads(line) for line in content[-lines:] if line.strip()]
    except Exception as e:
        return [{"error": str(e)}]

@app.get("/api/config")
async def get_config():
    """Returns the current relevant environment variables."""
    return {
        "STORAGE_DIR": os.getenv("STORAGE_DIR", ""),
        "API_PORT": os.getenv("API_PORT", "8000"),
        "ALLOW_COMPRESSED_PHOTOS": os.getenv("ALLOW_COMPRESSED_PHOTOS", "true"),
    }

@app.post("/api/config")
async def update_config(update: ConfigUpdate):
    """Updates a value in the .env file."""
    try:
        set_key(str(ENV_PATH), update.key, update.value)
        # Update current process environment
        os.environ[update.key] = update.value
        return {"status": "success", "message": f"Updated {update.key}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Serve media files
app.mount("/api/media", StaticFiles(directory=str(BASE_DIR)), name="media")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
