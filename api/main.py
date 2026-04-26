import json
import os
import asyncio
import hashlib
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional

import psutil
from fastapi import FastAPI, HTTPException, Body, Header, UploadFile, File, Form, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import io
from PIL import Image as PILImage, ImageOps

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

def get_robust_path(target_path: Path, fallback_subdir: str) -> Path:
    """Asegura que el directorio sea escribible, de lo contrario devuelve un fallback local."""
    try:
        target_path.mkdir(parents=True, exist_ok=True)
        # Test de escritura
        test_file = target_path / ".init_test"
        test_file.touch()
        test_file.unlink()
        return target_path
    except Exception as e:
        fallback = BASE_DIR / "vault_internal" / fallback_subdir
        print(f"\n[!] ERROR DE PERMISOS en: {target_path}")
        print(f"    Usando fallback local: {fallback}")
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback

# Aplicar lógica robusta a directorios críticos
SAFE_STORAGE_DIR = get_robust_path(STORAGE_DIR, "storage")
META_LOG = Path(os.getenv("META_LOG", str(SAFE_STORAGE_DIR / "metadata.jsonl"))).resolve()
CACHE_DIR = get_robust_path(STORAGE_DIR / ".cache" / "thumbnails", "thumbnails")
AUDIT_LOG = SAFE_STORAGE_DIR / "audit.log"
ENV_PATH = BASE_DIR / ".env"
RECOVERY_FILE = BASE_DIR / "vault_internal" / ".recovery_token"

# Initialize Auth (ahora usa STORAGE_DIR original pero AuthManager debe ser robusto internamente)
# No obstante, pasamos un path seguro para evitar el crash inicial
auth = AuthManager(get_robust_path(STORAGE_DIR / ".vault", "vault_auth"))

def maintain_cache(cache_dir: Path, max_size_mb: int = 500):
    """Elimina las miniaturas más antiguas si se supera el límite de espacio."""
    try:
        # Buscar todos los formatos soportados
        files = []
        for ext in ["*.webp", "*.jpg", "*.jpeg"]:
            files.extend(cache_dir.glob(ext))
        
        files.sort(key=lambda x: x.stat().st_mtime)
        total_size = sum(f.stat().st_size for f in files)
        
        if total_size > max_size_mb * 1024 * 1024:
            # Borrar el 20% más antiguo
            to_delete = files[:max(1, len(files) // 5)]
            for f in to_delete:
                try:
                    f.unlink()
                except:
                    pass
            print(f"[CACHE] Limpieza automática: {len(to_delete)} miniaturas eliminadas.")
    except Exception as e:
        print(f"[CACHE_ERROR] Error en mantenimiento: {e}")

async def verify_device(x_device_token: Optional[str] = Header(None)):
    """Simple security check for linked devices."""
    if not x_device_token or not auth.is_token_valid(x_device_token):
        raise HTTPException(status_code=401, detail="Unauthorized: Device not linked")
    return x_device_token

def log_audit(action: str, path: Path, device_info: dict):
    """Records an action to the audit log."""
    try:
        import time
        from datetime import datetime
        
        # Calculate relative path if possible
        try:
            rel_path = str(path.relative_to(STORAGE_DIR))
        except ValueError:
            rel_path = str(path.name)
            
        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "action": action,
            "path": rel_path,
            "user": device_info.get("name", "unknown_device"),
            "role": device_info.get("role", "standard")
        }
        with open(AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        print(f"[AUDIT_ERROR] {e}")

class MetadataManager:
    def __init__(self):
        self._cache = {}
        
    def load(self):
        """Carga el log de metadatos en RAM para búsquedas instantáneas."""
        if not META_LOG.exists():
            return
        new_cache = {}
        try:
            with open(META_LOG, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        item = json.loads(line)
                        saved_path = item.get("saved_path")
                        if saved_path:
                            # Generar ID consistente con get_items si no existe
                            item_id = item.get("id")
                            if not item_id:
                                item_id = hashlib.md5(saved_path.encode()).hexdigest()
                            new_cache[item_id] = saved_path
            self._cache = new_cache
            print(f"[META] Caché cargada: {len(self._cache)} archivos indexados en RAM.")
        except Exception as e:
            print(f"[META_ERROR] Error cargando metadatos: {e}")
            
    def get_path(self, item_id: str) -> Optional[str]:
        return self._cache.get(item_id)
        
    def update(self, item: dict):
        self._cache[item["id"]] = item["saved_path"]
        
    def remove(self, item_id: str):
        if item_id in self._cache:
            del self._cache[item_id]

metadata_cache = MetadataManager()
thumb_semaphore = asyncio.Semaphore(3)  # Límite de 3 generaciones simultáneas

async def pre_generate_thumbnails_worker():
    """Worker de fondo que busca archivos sin miniatura y los genera sín prisas."""
    print("[WORKER] Iniciando pre-generación de miniaturas...")
    # Obtenemos snapshot de los IDs actuales
    ids = list(metadata_cache._cache.keys())
    for item_id in ids:
        thumb_path = CACHE_DIR / f"{item_id}.webp"
        if not thumb_path.exists():
            try:
                # Simulamos una petición interna para aprovechar la lógica de generación con semáforo
                # Pero lo hacemos de forma que no bloquee aplicaciones críticas
                await asyncio.sleep(0.5) # Pausa entre generaciones para no ahogar la Pi
                # Llamamos a una función interna de generación (refactorizamos get_thumbnail después si es necesario)
                # Por ahora, simplemente dejamos que ocurra bajo demanda o implementamos aquí
                pass 
            except:
                continue
    print("[WORKER] Pre-generación completada.")

cloudflare_tunnel = None

@app.on_event("startup")
async def startup_event():
    # Iniciar caché de metadatos
    metadata_cache.load()
    
    # Generar token de recuperación local
    try:
        import secrets
        RECOVERY_FILE.parent.mkdir(parents=True, exist_ok=True)
        RECOVERY_FILE.write_text(secrets.token_hex(16))
    except Exception as e:
        print(f"[*] Fallo generando token de recuperación: {e}")

    
    # Lanzar worker de pre-generación en segundo plano (sin esperar)
    # asyncio.create_task(pre_generate_thumbnails_worker())
    
    if os.getenv("ENABLE_REMOTE_ACCESS", "false").lower() == "true":
        import threading
        import subprocess
        
        def _start_tunnel():
            global cloudflare_tunnel
            port = int(os.getenv("API_PORT", "8001"))
            
            # Estrategia 1: Intentar usar el binario oficial del sistema (más estable en Pi)
            try:
                process = subprocess.Popen(
                    ["cloudflared", "tunnel", "--url", f"http://localhost:{port}"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )
                
                # Buscar la URL y mantener el pipe abierto para evitar crash (SIGPIPE)
                found_url = False
                for line in process.stdout:
                    if not found_url and "trycloudflare.com" in line:
                        parts = line.split()
                        for p in parts:
                            if "https://" in p and "trycloudflare.com" in p:
                                url = p.strip()
                                os.environ["PUBLIC_URL"] = url
                                print("\n" + "!"*50)
                                print("   ACCESO REMOTO (OFICIAL) ACTIVADO")
                                print(f"   URL: {url}")
                                print("!"*50)
                                found_url = True

                
            except Exception as e:
                print(f"[*] Cloudflared del sistema no disponible o falló: {e}")

            # Estrategia 2: Fallback a pycloudflared (para Windows/otros)
            try:
                from pycloudflared import try_cloudflare
                cloudflare_tunnel = try_cloudflare(port=port)
                os.environ["PUBLIC_URL"] = cloudflare_tunnel.tunnel
                
                print("\n" + "!"*50)
                print("   ACCESO REMOTO (PY) ACTIVADO")
                print(f"   URL: {cloudflare_tunnel.tunnel}")
                print("!"*50)
            except Exception as e:
                print(f"\n[TUNNEL_ERROR] No se pudo iniciar el acceso remoto: {e}")
                print("[*] El sistema seguirá funcionando de forma local.\n")
                
        threading.Thread(target=_start_tunnel, daemon=True).start()

class ConfigUpdate(BaseModel):
    key: str
    value: str

class PinVerify(BaseModel):
    pin: str

class FolderCreate(BaseModel):
    name: str

def update_folder_meta(folder_name: str):
    if folder_name == "root":
        return
    base_upload = STORAGE_DIR / "uploaded_files"
    folder_path = base_upload / folder_name
    if not folder_path.exists() or not META_LOG.exists():
        return
    
    timestamps = []
    try:
        with open(META_LOG, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    if item.get("context") == folder_name:
                        ts = item.get("timestamp")
                        if ts and Path(item.get("saved_path", "")).exists():
                            timestamps.append(ts)
    except Exception as e:
        print(f"[META] Error reading META_LOG for folder {folder_name}: {e}")
        return

    if timestamps:
        timestamps.sort()
        meta_data = {
            "date_range": {
                "oldest": timestamps[0],
                "newest": timestamps[-1]
            }
        }
    else:
        meta_data = {"date_range": None}
        
    meta_file = folder_path / ".meta.json"
    try:
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta_data, f)
    except Exception as e:
        print(f"[META] Error writing .meta.json: {e}")

@app.get("/api/folders")
async def list_folders(x_device_token: str = Header(...)):
    """Devuelve la lista de carpetas disponibles en el almacenamiento."""
    device = auth.get_device_info(x_device_token)
    if not device:
        raise HTTPException(status_code=401, detail="Invalid token")
        
    role = device.get("role", "standard")
    allowed_folders = device.get("allowed_folders", [])
    
    base_upload = STORAGE_DIR / "uploaded_files"
    if not base_upload.exists():
        return []
        
    folders = []
    # Incluimos 'root' como carpeta virtual por defecto
    if role == "admin" or "root" in allowed_folders or "*" in allowed_folders:
        folders.append("root")
        
    for item in base_upload.iterdir():
        if item.is_dir():
            folder_name = item.name
            if role == "admin" or folder_name in allowed_folders or "*" in allowed_folders:
                folders.append(folder_name)
                
    return sorted(list(set(folders)))

@app.get("/api/folders/meta")
async def get_folders_meta(x_device_token: str = Header(...)):
    """Devuelve la metainformación de todas las carpetas disponibles para el usuario."""
    device = auth.get_device_info(x_device_token)
    if not device:
        raise HTTPException(status_code=401, detail="Invalid token")
        
    role = device.get("role", "standard")
    allowed_folders = device.get("allowed_folders", [])
    
    base_upload = STORAGE_DIR / "uploaded_files"
    if not base_upload.exists():
        return {}
        
    meta_dict = {}
    for item in base_upload.iterdir():
        if item.is_dir():
            folder_name = item.name
            if role == "admin" or folder_name in allowed_folders or "*" in allowed_folders:
                meta_file = item / ".meta.json"
                if not meta_file.exists():
                    update_folder_meta(folder_name)
                    
                if meta_file.exists():
                    try:
                        with open(meta_file, "r", encoding="utf-8") as f:
                            meta_dict[folder_name] = json.load(f)
                    except Exception:
                        pass
                        
    return meta_dict

@app.post("/api/folders")
async def create_folder(data: FolderCreate, x_device_token: str = Header(...)):
    """Crea una nueva carpeta física en el almacenamiento."""
    device = auth.get_device_info(x_device_token)
    if not device or device.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can create folders")
        
    # Limpiar el nombre de la carpeta
    clean_name = "".join(c for c in data.name if c.isalnum() or c in (" ", "-", "_")).strip()
    if not clean_name or clean_name == "root":
        raise HTTPException(status_code=400, detail="Invalid folder name")
        
    folder_path = STORAGE_DIR / "uploaded_files" / clean_name
    try:
        folder_path.mkdir(parents=True, exist_ok=True)
        log_audit("CREATE_FOLDER", folder_path, device)
        return {"status": "success", "folder": clean_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
                        
                        # Verify physical existence
                        if not saved_path.exists():
                            continue
                        
                        # Verify access for standard users
                        if role != "admin":
                            try:
                                rel_to_storage = saved_path.relative_to(STORAGE_DIR)
                                folder_name = rel_to_storage.parts[0] if len(rel_to_storage.parts) > 1 else "root"
                            except ValueError:
                                folder_name = "root"
                            if folder_name not in allowed_folders and "*" not in allowed_folders:
                                continue

                        # Ensure unique ID and basic structure
                        if "id" not in item:
                            item["id"] = hashlib.md5(item.get("saved_path", "unknown").encode()).hexdigest()

                        # Generate web_path relative to STORAGE or BASE
                        try:
                            # Try relative to storage first (most common)
                            rel = saved_path.relative_to(SAFE_STORAGE_DIR)
                            item["web_path"] = str(rel).replace("\\", "/")
                        except ValueError:
                            try:
                                # Try relative to project root
                                rel = saved_path.relative_to(BASE_DIR)
                                item["web_path"] = str(rel).replace("\\", "/")
                            except ValueError:
                                # Fallback to filename
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
                if p.is_file() and not any(part in p.parts for part in ["_tmp", ".cache"]):
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
async def request_pairing(recovery: Optional[str] = Query(None)):
    """Generates a Master PIN for the mobile app to link. Only allowed if no admin exists or via recovery token."""
    
    is_recovery = False
    if recovery and RECOVERY_FILE.exists():
        if recovery == RECOVERY_FILE.read_text().strip():
            is_recovery = True
            
    if auth.get_admins_count() > 0 and not is_recovery:
        raise HTTPException(status_code=403, detail="Admin already registered. Use App to invite.")
        
    pin = auth.generate_pin(role="admin", allowed_folders=["*"])
    ip = get_local_ip()
    port = int(os.getenv("API_PORT", "8000"))
    public_url = os.getenv("PUBLIC_URL")
    url = public_url if public_url else f"http://{ip}:{port}"
    return {
        "pin": pin,
        "url": url,
        "expires_in": 300,
        "recovered": is_recovery
    }

class InviteRequest(BaseModel):
    folders: List[str]

@app.post("/api/auth/invite")
async def create_invite(data: InviteRequest, x_device_token: str = Header(...)):
    """Creates a P2P invite for a standard user to a specific folder (Admin only)."""
    device = auth.get_device_info(x_device_token)
    if not device or device.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can generate invites")
    
    pin = auth.generate_pin(role="standard", allowed_folders=data.folders)
    ip = get_local_ip()
    port = int(os.getenv("API_PORT", "8000"))
    public_url = os.getenv("PUBLIC_URL")
    url = public_url if public_url else f"http://{ip}:{port}"
    return {
        "pin": pin,
        "url": url,
        "expires_in": 300,
        "folders": data.folders
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
async def get_thumbnail(
    item_id: str, 
    background_tasks: BackgroundTasks,
    x_device_token: Optional[str] = Header(None), 
    token: Optional[str] = Query(None)
):
    """Returns a cached or generated thumbnail for an image (optimized WebP)."""
    try:
        # Validación de seguridad (opcional para miniaturas, pero recomendada)
        auth_token = x_device_token or token
        if auth_token:
            auth.get_device_info(auth_token) # Validamos que el dispositivo existe
            
        # 1. Búsqueda instantánea en RAM
        saved_path_str = metadata_cache.get_path(item_id)
        if not saved_path_str:
            print(f"[THUMB_DEBUG] ID no encontrado en caché RAM: {item_id}")
            raise HTTPException(status_code=404, detail="Item not in cache")
            
        orig_path = Path(saved_path_str)
        if not orig_path.exists():
            print(f"[THUMB_DEBUG] El archivo original ya no existe: {saved_path_str}")
            raise HTTPException(status_code=404, detail="Original file missing")
        
        # 2. Verificar si ya existe en disco (buscando múltiples extensiones)
        thumb_path_webp = CACHE_DIR / f"{item_id}.webp"
        thumb_path_jpg = CACHE_DIR / f"{item_id}.jpg"
        
        if thumb_path_webp.exists():
            return FileResponse(thumb_path_webp)
        if thumb_path_jpg.exists():
            return FileResponse(thumb_path_jpg)
            
        print(f"[THUMB_DEBUG] Generando nueva miniatura para: {item_id}")
        
        # 3. Probabilidad de mantenimiento
        import random
        if random.random() < 0.02:
            background_tasks.add_task(maintain_cache, CACHE_DIR)

        # 4. Generación con Semáforo (Control de CPU)
        async with thumb_semaphore:
            # Re-verificar tras la espera por si otro hilo la generó
            if thumb_path_webp.exists(): return FileResponse(thumb_path_webp)
            if thumb_path_jpg.exists(): return FileResponse(thumb_path_jpg)
                
            import subprocess
            img_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
            vid_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
            ext = orig_path.suffix.lower()
            
            try:
                if ext in img_exts:
                    with PILImage.open(orig_path) as img:
                        img = ImageOps.exif_transpose(img)
                        if img.mode in ("RGBA", "P"): img = img.convert("RGB")
                        img.thumbnail((300, 300)) 
                        try:
                            img.save(thumb_path_webp, "WEBP", quality=70)
                            return FileResponse(thumb_path_webp)
                        except Exception:
                            # Fallback a JPEG si falla WEBP (falta de encoder en el sistema)
                            img.save(thumb_path_jpg, "JPEG", quality=75)
                            return FileResponse(thumb_path_jpg)
                            
                elif ext in vid_exts:
                    tmp_jpg = CACHE_DIR / f"{item_id}.tmp.jpg"
                    cmd = ["ffmpeg", "-y", "-i", str(orig_path), "-ss", "00:00:01", "-vframes", "1", "-q:v", "4", str(tmp_jpg)]
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                    if tmp_jpg.exists():
                        with PILImage.open(tmp_jpg) as img:
                            img = ImageOps.exif_transpose(img)
                            img.thumbnail((300, 300))
                            try:
                                img.save(thumb_path_webp, "WEBP", quality=70)
                                tmp_jpg.unlink()
                                return FileResponse(thumb_path_webp)
                            except Exception:
                                img.save(thumb_path_jpg, "JPEG", quality=75)
                                tmp_jpg.unlink()
                                return FileResponse(thumb_path_jpg)
            except Exception as gen_err:
                print(f"[THUMB_GEN_ERROR] Fallo crítico generando miniatura para {item_id}: {gen_err}")
                            
        raise HTTPException(status_code=404, detail="Thumbnail could not be generated")
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Thumbnail error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/api/media/file/{path:path}")
async def get_media_file(path: str, x_device_token: Optional[str] = Header(None), token: Optional[str] = Query(None)):
    """Serves a media file with device token validation (via header or query para)."""
    auth_token = x_device_token or token
    if not auth_token:
        raise HTTPException(status_code=401, detail="Token not provided")
        
    device = auth.get_device_info(auth_token)
    if not device:
        raise HTTPException(status_code=401, detail="Invalid token")
        
    # Security Check and Path Resolution
    try:
        requested_path = Path(path)
        # Try finding the file in SAFE_STORAGE_DIR first, then BASE_DIR
        possible_paths = [
            (SAFE_STORAGE_DIR / requested_path).resolve(),
            (BASE_DIR / requested_path).resolve()
        ]
        
        target_file = None
        for p in possible_paths:
            # Security: Ensure resolved path is inside one of the allowed directories
            is_inside_storage = False
            try:
                p.relative_to(SAFE_STORAGE_DIR)
                is_inside_storage = True
            except ValueError:
                pass
                
            is_inside_base = False
            try:
                p.relative_to(BASE_DIR)
                is_inside_base = True
            except ValueError:
                pass
                
            if (is_inside_storage or is_inside_base) and p.exists() and p.is_file():
                target_file = p
                break
        
        if not target_file:
            raise HTTPException(status_code=404, detail="File not found or access denied")
            
        return FileResponse(target_file)
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[MEDIA_ERROR] {e}")
        raise HTTPException(status_code=403, detail="Error accessing file")

@app.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...), 
    context: str = Form("root"),
    original_date: Optional[str] = Form(None),
    x_device_token: str = Header(...)
):
    """Securely uploads a file from the mobile app."""
    device = auth.get_device_info(x_device_token)
    if not device:
        raise HTTPException(status_code=401, detail="Invalid token")
        
    role = device.get("role", "standard")
    allowed_folders = device.get("allowed_folders", [])
    
    # Check permission for the targeted folder
    if role != "admin" and context not in allowed_folders and "*" not in allowed_folders:
        raise HTTPException(status_code=403, detail="No permission to upload to this folder")
        
    try:
        import secrets
        import time
        from datetime import datetime
        
        # New structure: uploaded_files/
        base_upload = STORAGE_DIR / "uploaded_files"
        
        if context == "root":
            # Date based: uploaded_files/YYYY/MM
            now = datetime.now()
            save_folder = base_upload / str(now.year) / f"{now.month:02d}"
        else:
            # Named folder: uploaded_files/named_folder
            save_folder = base_upload / context
            
        save_folder.mkdir(parents=True, exist_ok=True)
        
        file_path = save_folder / file.filename
        if file_path.exists():
            file_path = save_folder / f"{int(time.time())}_{file.filename}"
            
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Determine final timestamp
        final_timestamp = None
        
        # 1. Try EXIF for images
        if file.filename.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
            try:
                from PIL import Image as PILImage
                from PIL.ExifTags import TAGS
                with PILImage.open(file_path) as img:
                    exif = img.getexif()
                    if exif:
                        for tag_id, value in exif.items():
                            tag = TAGS.get(tag_id, tag_id)
                            if tag == 'DateTimeOriginal' and value:
                                try:
                                    dt = datetime.strptime(str(value).strip(), "%Y:%m:%d %H:%M:%S")
                                    final_timestamp = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                                    break
                                except:
                                    pass
            except Exception as e:
                print(f"[EXIF_ERROR] {e}")
                
        # 2. Try client-provided original date
        if not final_timestamp and original_date:
            try:
                if "T" in original_date:
                    final_timestamp = original_date
            except:
                pass
                
        # 3. Fallback to current time
        if not final_timestamp:
            final_timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        item = {
            "id": secrets.token_hex(8),
            "name": file.filename,
            "saved_path": str(file_path),
            "timestamp": final_timestamp,
            "source": "mobile",
            "context": context
        }
        with open(META_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(item) + "\n")
            
        # Sincronizar Cache en RAM
        metadata_cache.update(item)
            
        update_folder_meta(context)
            
        # Log Audit
        log_audit("UPLOAD", file_path, device)
            
        return {"status": "success", "id": item["id"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/items/{item_id}")
async def delete_item(item_id: str, x_device_token: str = Header(...)):
    """Deletes a file and its metadata (Admin only)."""
    device = auth.get_device_info(x_device_token)
    if not device or device.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can delete items")

    if not META_LOG.exists():
        raise HTTPException(status_code=404, detail="Metadata log not found")

    target_item = None
    remaining_items = []
    
    try:
        # Read and find the item to delete
        with open(META_LOG, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    if item.get("id") == item_id:
                        target_item = item
                    else:
                        remaining_items.append(line)
        
        if not target_item:
            raise HTTPException(status_code=404, detail="Item not found")

        # 1. Delete physical file
        p = Path(target_item["saved_path"])
        if p.exists():
            p.unlink()
            
        # 2. Delete thumbnails if they exist
        for ext in [".webp", ".jpg", ".jpeg"]:
            tp = CACHE_DIR / f"{item_id}{ext}"
            if tp.exists():
                tp.unlink()

        # 3. Rewrite metadata log
        with open(META_LOG, "w", encoding="utf-8") as f:
            f.writelines(remaining_items)

        # 4. Sincronizar Cache en RAM
        metadata_cache.remove(item_id)
        
        if target_item.get("context"):
            update_folder_meta(target_item.get("context"))

        # Log Audit
        log_audit("DELETE_ITEM", Path(target_item["saved_path"]), device)

        return {"status": "success", "message": "Item deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class FolderNameRequest(BaseModel):
    name: str

@app.post("/api/folders")
async def create_folder(req: FolderNameRequest, x_device_token: str = Header(...)):
    """Creates a new empty folder (Admin only)."""
    device = auth.get_device_info(x_device_token)
    if not device or device.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can create folders")
        
    folder_name = req.name.strip()
    if not folder_name or folder_name.lower() == "root":
        raise HTTPException(status_code=400, detail="Invalid folder name")
        
    try:
        base_upload = STORAGE_DIR / "uploaded_files"
        folder_path = base_upload / folder_name
        folder_path.mkdir(parents=True, exist_ok=True)
        
        # Log Audit
        log_audit("CREATE_FOLDER", folder_path, device)
        
        return {"status": "success", "message": f"Folder {folder_name} created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/folders/{folder_name}")
async def delete_folder(folder_name: str, x_device_token: str = Header(...)):
    """Deletes a named folder and all its items (Admin only)."""
    device = auth.get_device_info(x_device_token)
    if not device or device.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can delete folders")
    
    if folder_name == "root":
        raise HTTPException(status_code=400, detail="Cannot delete root/timeline folder")

    try:
        base_upload = STORAGE_DIR / "uploaded_files"
        folder_path = base_upload / folder_name
        
        # 1. Physically delete the folder and files
        if folder_path.exists():
            shutil.rmtree(folder_path)
            
        # 2. Clean up metadata log
        remaining_items = []
        if META_LOG.exists():
            with open(META_LOG, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        item = json.loads(line)
                        saved_path = Path(item["saved_path"])
                        try:
                            # If the path is inside the folder_path, skip it (delete from log)
                            saved_path.relative_to(folder_path)
                        except ValueError:
                            remaining_items.append(line)
                            
            with open(META_LOG, "w", encoding="utf-8") as f:
                f.writelines(remaining_items)
                
            # 3. Recargar Cache en RAM completa tras borrar carpeta
            metadata_cache.load()
                
        # Log Audit
        log_audit("DELETE_FOLDER", folder_path, device)
                
        return {"status": "success", "message": f"Folder {folder_name} deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Serve media files
app.mount("/api/media", StaticFiles(directory=str(BASE_DIR)), name="media")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
