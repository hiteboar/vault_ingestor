import json
import os
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional

import psutil
from fastapi import FastAPI, HTTPException, Body, Header, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import io
from PIL import Image

from core.auth import AuthManager
from core.network import get_local_ip

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
CACHE_DIR = STORAGE_DIR / ".cache" / "thumbnails"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
ENV_PATH = BASE_DIR / ".env"

# Initialize Auth
auth = AuthManager(STORAGE_DIR / ".vault")

async def verify_device(x_device_token: Optional[str] = Header(None)):
    """Simple security check for linked devices."""
    if not x_device_token or not auth.is_token_valid(x_device_token):
        raise HTTPException(status_code=401, detail="Unauthorized: Device not linked")
    return x_device_token

cloudflare_tunnel = None

@app.on_event("startup")
async def startup_event():
    if os.getenv("ENABLE_REMOTE_ACCESS", "false").lower() == "true":
        import threading
        def _start_tunnel():
            global cloudflare_tunnel
            try:
                from pycloudflared import try_cloudflare
                port = int(os.getenv("API_PORT", "8000"))
                cloudflare_tunnel = try_cloudflare(port=port)
                os.environ["PUBLIC_URL"] = cloudflare_tunnel.tunnel
                print(f"\n[TUNNEL] Acceso remoto activado!\nURL Pública: {cloudflare_tunnel.tunnel}\n")
            except Exception as e:
                print(f"\n[TUNNEL_ERROR] {e}\n")
                
        threading.Thread(target=_start_tunnel, daemon=True).start()

class PinVerify(BaseModel):
    pin: str

class ConfigUpdate(BaseModel):
    key: str
    value: str

@app.get("/api/items")
async def get_items(x_device_token: str = Header(...)):
    device = auth.get_device_info(x_device_token)
    if not device:
        raise HTTPException(status_code=401, detail="Invalid token")

    role = device.get("role", "standard")
    allowed_folders = device.get("allowed_folders", [])

    if not META_LOG.exists():
        return []
    
    items = []
    try:
        with open(META_LOG, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        item = json.loads(line)
                        saved_path = Path(item["saved_path"])
                        
                        # Verify access for standard users
                        if role != "admin":
                            try:
                                rel_to_storage = saved_path.relative_to(STORAGE_DIR)
                                folder_name = rel_to_storage.parts[0] if len(rel_to_storage.parts) > 1 else "root"
                            except ValueError:
                                folder_name = "root"
                            if folder_name not in allowed_folders and "*" not in allowed_folders:
                                continue

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
        "ENABLE_REMOTE_ACCESS": os.getenv("ENABLE_REMOTE_ACCESS", "false"),
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

# --- AUTH ENDPOINTS ---

@app.get("/api/auth/request")
async def request_pairing():
    """Generates a Master PIN for the mobile app to link. Only allowed if no admin exists."""
    if auth.get_admins_count() > 0:
        raise HTTPException(status_code=403, detail="Admin already registered. Use App to invite.")
        
    pin = auth.generate_pin(role="admin", allowed_folders=["*"])
    ip = get_local_ip()
    port = int(os.getenv("API_PORT", "8000"))
    public_url = os.getenv("PUBLIC_URL")
    url = public_url if public_url else f"http://{ip}:{port}"
    return {
        "pin": pin,
        "url": url,
        "expires_in": 300
    }

class InviteRequest(BaseModel):
    folder: str

@app.post("/api/auth/invite")
async def create_invite(data: InviteRequest, x_device_token: str = Header(...)):
    """Creates a P2P invite for a standard user to a specific folder (Admin only)."""
    device = auth.get_device_info(x_device_token)
    if not device or device.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can generate invites")
    
    pin = auth.generate_pin(role="standard", allowed_folders=[data.folder])
    ip = get_local_ip()
    port = int(os.getenv("API_PORT", "8000"))
    public_url = os.getenv("PUBLIC_URL")
    url = public_url if public_url else f"http://{ip}:{port}"
    return {
        "pin": pin,
        "url": url,
        "expires_in": 300,
        "folder": data.folder
    }

@app.post("/api/auth/verify")
async def verify_pairing(data: PinVerify):
    """Verifies a PIN and returns a permanent device token."""
    token = auth.verify_pin(data.pin)
    if not token:
        raise HTTPException(status_code=400, detail="Invalid or expired PIN")
    return {"token": token}

@app.get("/api/auth/me")
async def get_me(x_device_token: str = Header(...)):
    """Returns the current user role and allowed folders."""
    device = auth.get_device_info(x_device_token)
    if not device:
        raise HTTPException(status_code=401, detail="Invalid token")
    return {
        "role": device.get("role", "standard"),
        "allowed_folders": device.get("allowed_folders", [])
    }

@app.get("/api/auth/qr")
async def get_pairing_qr():
    """Returns a QR code image for mobile pairing."""
    import qrcode
    from fastapi.responses import Response
    
    # Request a new PIN/Session
    pin_data = await request_pairing()
    qr_content = json.dumps({
        "url": pin_data["url"],
        "pin": pin_data["pin"]
    })
    
    # Generate QR
    qr = qrcode.QRCode(version=1, box_size=10, border=1)
    qr.add_data(qr_content)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    
    return Response(content=img_byte_arr.getvalue(), media_type="image/png")

# --- MEDIA & UPLOAD ---

@app.get("/api/media/thumbnail/{item_id}")
async def get_thumbnail(item_id: str):
    """Returns a cached or generated thumbnail for an image."""
    try:
        with open(META_LOG, "r", encoding="utf-8") as f:
            for line in f:
                if item_id in line:
                    item = json.loads(line)
                    if item.get("id") == item_id:
                        orig_path = Path(item["saved_path"])
                        if not orig_path.exists():
                            break
                        
                        thumb_path = CACHE_DIR / f"{item_id}.jpg"
                        if thumb_path.exists():
                            return FileResponse(thumb_path)
                        
                        import time
                        # Generate thumbnail
                        with Image.open(orig_path) as img:
                            img.thumbnail((400, 400)) 
                            img.save(thumb_path, "JPEG", quality=85)
                        return FileResponse(thumb_path)
    except Exception:
        pass
    
    raise HTTPException(status_code=404, detail="Thumbnail not available")

@app.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...), 
    context: str = Body("mobile_upload"),
    x_device_token: str = Header(...)
):
    """Securely uploads a file from the mobile app."""
    device = auth.get_device_info(x_device_token)
    if not device:
        raise HTTPException(status_code=401, detail="Invalid token")
        
    role = device.get("role", "standard")
    allowed_folders = device.get("allowed_folders", [])
    
    if role != "admin" and context not in allowed_folders and "*" not in allowed_folders:
        raise HTTPException(status_code=403, detail="No permission to upload to this folder")
        
    try:
        import secrets
        import time
        # Create context folder
        save_folder = STORAGE_DIR / context
        save_folder.mkdir(parents=True, exist_ok=True)
        
        file_path = save_folder / file.filename
        if file_path.exists():
            file_path = save_folder / f"{int(time.time())}_{file.filename}"
            
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        item = {
            "id": secrets.token_hex(8),
            "name": file.filename,
            "saved_path": str(file_path),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source": "mobile"
        }
        with open(META_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(item) + "\n")
            
        return {"status": "success", "id": item["id"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Serve media files
app.mount("/api/media", StaticFiles(directory=str(BASE_DIR)), name="media")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
