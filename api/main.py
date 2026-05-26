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
import time
from datetime import datetime, timezone
from PIL import Image as PILImage, ImageOps

try:
    import exifread
except ImportError:
    exifread = None

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
    """Ensures the directory is writable, otherwise returns a local fallback."""
    try:
        target_path.mkdir(parents=True, exist_ok=True)
        # Test de escritura
        test_file = target_path / ".init_test"
        test_file.touch()
        test_file.unlink()
        return target_path
    except Exception as e:
        fallback = BASE_DIR / "vault_internal" / fallback_subdir
        print(f"\n[!] PERMISSIONS ERROR at: {target_path}")
        print(f"    Using local fallback: {fallback}")
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback

# Apply robust logic to critical directories
SAFE_STORAGE_DIR = get_robust_path(STORAGE_DIR, "storage")
META_LOG = Path(os.getenv("META_LOG", str(SAFE_STORAGE_DIR / "metadata.jsonl"))).resolve()
CACHE_DIR = get_robust_path(STORAGE_DIR / ".cache" / "thumbnails", "thumbnails")
AUDIT_LOG = SAFE_STORAGE_DIR / "audit.log"
ENV_PATH = BASE_DIR / ".env"
RECOVERY_FILE = BASE_DIR / "vault_internal" / ".recovery_token"

# Initialize Auth (now uses original STORAGE_DIR but AuthManager must be robust internally)
# However, we pass a safe path to avoid initial crash
auth = AuthManager(get_robust_path(STORAGE_DIR / ".vault", "vault_auth"))

def maintain_cache(cache_dir: Path, max_size_mb: int = 500):
    """Deletes the oldest thumbnails if the space limit is exceeded."""
    try:
        # Buscar todos los formatos soportados
        files = []
        for ext in ["*.webp", "*.jpg", "*.jpeg"]:
            files.extend(cache_dir.glob(ext))
        
        files.sort(key=lambda x: x.stat().st_mtime)
        total_size = sum(f.stat().st_size for f in files)
        
        if total_size > max_size_mb * 1024 * 1024:
            # Delete the oldest 20%
            to_delete = files[:max(1, len(files) // 5)]
            for f in to_delete:
                try:
                    f.unlink()
                except:
                    pass
            print(f"[CACHE] Automatic cleanup: {len(to_delete)} thumbnails removed.")
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

def extract_metadata_timestamp(file_path: Path) -> Optional[str]:
    """Extracts date/time from EXIF, FFprobe, or Filename. Returns None if none found."""
    ext = file_path.suffix.lower()
    filename = file_path.name
    
    # 1. Try EXIF for images (supporting JPG, JPEG, PNG, WEBP, HEIC, HEIF)
    if ext in {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}:
        # Try exifread first (highly reliable for HEIC/JPEG and pure Python)
        if exifread:
            try:
                with open(file_path, 'rb') as f:
                    tags = exifread.process_file(f, details=False)
                    tag = tags.get('EXIF DateTimeOriginal') or tags.get('Image DateTime') or tags.get('EXIF DateTimeDigitized')
                    if tag:
                        try:
                            date_str = str(tag).strip().replace('\x00', '')
                            dt = datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
                            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                        except:
                            pass
            except:
                pass

        # Fallback to PIL (Pillow) if exifread is not available or didn't find anything
        try:
            from PIL import Image as PILImage
            from PIL.ExifTags import TAGS
            with PILImage.open(file_path) as img:
                exif = img._getexif()
                if exif:
                    # Buscar etiquetas de fecha comunes
                    for tag_id, value in exif.items():
                        tag = TAGS.get(tag_id, tag_id)
                        if tag in ('DateTimeOriginal', 'DateTime', 'DateTimeDigitized') and value:
                            try:
                                # EXIF format is usually "YYYY:MM:DD HH:MM:SS"
                                # But sometimes it has weird or null characters at the end
                                date_str = str(value).strip().replace('\x00', '')
                                dt = datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
                                return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                            except:
                                pass
        except:
            pass
            
    # 2. Try FFprobe for videos
    elif ext in {".mp4", ".mov", ".avi", ".mkv", ".webm"}:
        try:
            import subprocess
            cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(file_path)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                meta = json.loads(result.stdout)
                tags = meta.get("format", {}).get("tags", {})
                # Try various creation tags
                creation_time = tags.get("creation_time") or tags.get("com.apple.quicktime.creationdate")
                if creation_time:
                    return creation_time
        except:
            pass
            
    # 3. Try to extract from filename (Pattern: YYYYMMDD or YYYY-MM-DD)
    # Common on mobiles: IMG_20230515_... or VID_20230515_...
    import re
    date_match = re.search(r'(\d{4})[-_]?(\d{2})[-_]?(\d{2})', filename)
    if date_match:
        try:
            year, month, day = date_match.groups()
            # Check if it looks like a reasonable date
            if 1990 <= int(year) <= 2100 and 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
                return f"{year}-{month}-{day}T12:00:00Z"
        except:
            pass
            
    return None

def extract_timestamp(file_path: Path) -> str:
    """Extracts the most accurate date possible from a file and returns it in ISO format."""
    ts = extract_metadata_timestamp(file_path)
    if ts:
        return ts

    # 4. Fallback to system modification date (in UTC)
    try:
        mtime = file_path.stat().st_mtime
        return datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

class MetadataManager:
    def __init__(self):
        self._cache = {}
        
    def load(self):
        """Loads the metadata log into RAM for instant searches, auto-healing incorrect paths on startup."""
        if not META_LOG.exists():
            return
        
        # 1. Escanear archivos físicos reales bajo el STORAGE_DIR actual
        base_upload = STORAGE_DIR / "uploaded_files"
        physical_files = {}
        try:
            if base_upload.exists():
                for p in base_upload.rglob("*"):
                    if p.is_file() and not p.name.startswith("."):
                        # Mapeamos nombre_archivo -> ruta_absoluta_real
                        physical_files[p.name] = p.resolve()
        except Exception as e:
            print(f"[META_WARNING] Error indexing physical files for self-healing: {e}")

        new_cache = {}
        healed_count = 0
        records_to_write = []
        
        try:
            with open(META_LOG, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    item = json.loads(line)
                    saved_path_str = item.get("saved_path", "")
                    saved_path = Path(saved_path_str) if saved_path_str else None
                    filename = item.get("name")

                    # Verificar si la ruta guardada es inválida o no existe físicamente
                    if filename and (not saved_path or not saved_path.exists()):
                        # Buscar si el archivo existe en la ubicación física real actual
                        if filename in physical_files:
                            real_path = physical_files[filename]
                            item["saved_path"] = str(real_path)
                            if "reported_path" in item:
                                item["reported_path"] = str(real_path)
                            healed_count += 1
                            print(f"[SELF-HEAL] Corregida ruta para {filename} -> {real_path}")

                    item_id = item.get("id")
                    if not item_id:
                        item_id = hashlib.md5(item.get("saved_path", "").encode()).hexdigest()
                        item["id"] = item_id
                    
                    new_cache[item_id] = item
                    records_to_write.append(json.dumps(item) + "\n")

            # 2. Si hubo registros auto-reparados, hacemos backup y reescribimos de forma segura
            if healed_count > 0:
                try:
                    backup_path = META_LOG.with_suffix(".jsonl.bak")
                    shutil.copy2(META_LOG, backup_path)
                    print(f"[SELF-HEAL] Creado backup de seguridad en {backup_path}")
                    
                    with open(META_LOG, "w", encoding="utf-8") as f:
                        f.writelines(records_to_write)
                    print(f"[SELF-HEAL] ¡Se han reparado {healed_count} registros de metadatos automáticamente!")
                except Exception as save_err:
                    print(f"[SELF-HEAL_ERROR] Error al guardar metadatos reparados: {save_err}")

            self._cache = new_cache
            print(f"[META] Cache loaded: {len(self._cache)} files indexed in RAM. (Self-heal: {healed_count} repaired)")
        except Exception as e:
            print(f"[META_ERROR] Error loading metadata: {e}")
            
    def get_item(self, item_id: str) -> Optional[dict]:
        return self._cache.get(item_id)

    def get_path(self, item_id: str) -> Optional[str]:
        item = self._cache.get(item_id)
        return item.get("saved_path") if item else None
        
    def update(self, item: dict):
        self._cache[item["id"]] = item
        
    def remove(self, item_id: str):
        if item_id in self._cache:
            del self._cache[item_id]

metadata_cache = MetadataManager()
thumb_semaphore = asyncio.Semaphore(3)  # Limit of 3 simultaneous generations

async def pre_generate_thumbnails_worker():
    """Background worker that looks for files without thumbnails and generates them without haste."""
    print("[WORKER] Starting pre-generation of thumbnails...")
    # Get snapshot of current IDs
    ids = list(metadata_cache._cache.keys())
    for item_id in ids:
        thumb_path = CACHE_DIR / f"{item_id}.webp"
        if not thumb_path.exists():
            try:
                # We simulate an internal request to leverage generation logic with semaphore
                # But we do it in a way that doesn't block critical applications
                await asyncio.sleep(0.5) # Pausa entre generaciones para no ahogar la Pi
                # Llamamos a una función interna de generación (refactorizamos get_thumbnail después si es necesario)
                # Por ahora, simplemente dejamos que ocurra bajo demanda o implementamos aquí
                pass 
            except:
                continue
    print("[WORKER] Pre-generation completed.")

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
        print(f"[*] Failed generating recovery token: {e}")

    
    # Lanzar worker de pre-generación en segundo plano (sin esperar)
    # asyncio.create_task(pre_generate_thumbnails_worker())
    
    if os.getenv("ENABLE_REMOTE_ACCESS", "false").lower() == "true":
        import threading
        import subprocess
        
        def _start_tunnel():
            global cloudflare_tunnel
            port = int(os.getenv("API_PORT", "8001"))
            token = os.getenv("CLOUDFLARE_TOKEN")
            
            # Estrategia 1: Intentar usar el binario oficial del sistema (más estable en Pi)
            try:
                if token:
                    print(f"[*] Using Cloudflare Token for persistent tunnel...")
                    process = subprocess.Popen(
                        ["cloudflared", "tunnel", "run", "--token", token],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1
                    )
                    # In token mode, the URL should already be configured in the Cloudflare panel
                    # and point to this local port. We use PUBLIC_URL from .env if it exists.
                    url = os.getenv("PUBLIC_URL", "Configured in Cloudflare dashboard")
                    print("\n" + "!"*50)
                    print("   REMOTE ACCESS (PERSISTENT) ENABLED")
                    print(f"   URL: {url}")
                    print("!"*50)
                else:
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
                                    print("   REMOTE ACCESS (OFFICIAL) ENABLED")
                                    print(f"   URL: {url}")
                                    print("!"*50)
                                    found_url = True
            except Exception as e:
                if not token:
                    print(f"[*] System cloudflared not available or failed: {e}")
                    # Strategy 2: Fallback to pycloudflared (for Windows/others)
                    try:
                        from pycloudflared import try_cloudflare
                        cloudflare_tunnel = try_cloudflare(port=port)
                        os.environ["PUBLIC_URL"] = cloudflare_tunnel.tunnel
                        
                        print("\n" + "!"*50)
                        print("   REMOTE ACCESS (PY) ENABLED")
                        print(f"   URL: {cloudflare_tunnel.tunnel}")
                        print("!"*50)
                    except Exception as e2:
                        print(f"\n[TUNNEL_ERROR] Could not start remote access: {e2}")
                        print("[*] The system will continue running locally.\n")
                else:
                    print(f"\n[TUNNEL_ERROR] Cloudflare Token error: {e}")
                
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
    """Returns the list of folders available in storage."""
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
    """Returns the meta-information of all folders (dynamically calculated from cache)."""
    device = auth.get_device_info(x_device_token)
    if not device:
        raise HTTPException(status_code=401, detail="Invalid token")
        
    role = device.get("role", "standard")
    allowed_folders = device.get("allowed_folders", [])
    
    # Agrupar timestamps por carpeta desde la caché en RAM
    folder_stats = {}
    for item in metadata_cache._cache.values():
        ctx = item.get("context", "root")
        ts = item.get("timestamp")
        if not ts: continue
        
        if ctx not in folder_stats:
            folder_stats[ctx] = []
        folder_stats[ctx].append(ts)
    
    meta_dict = {}
    for folder_name, timestamps in folder_stats.items():
        # Saltamos root porque se maneja implícitamente en la línea de tiempo
        if folder_name == "root": continue
        
        # Verificar permisos
        if role == "admin" or folder_name in allowed_folders or "*" in allowed_folders:
            timestamps.sort()
            meta_dict[folder_name] = {
                "date_range": {
                    "oldest": timestamps[0],
                    "newest": timestamps[-1]
                }
            }
                        
    return meta_dict

@app.post("/api/folders")
async def create_folder(data: FolderCreate, x_device_token: str = Header(...)):
    """Creates a new physical folder in storage."""
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
    
    # Sort by timestamp (newest first)
    items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return items

@app.get("/api/items/{item_id}/info")
async def get_item_info(item_id: str, x_device_token: str = Header(...)):
    device = auth.get_device_info(x_device_token)
    if not device:
        raise HTTPException(status_code=401, detail="Invalid token")

    item_meta = metadata_cache.get_item(item_id)
    if not item_meta:
        raise HTTPException(status_code=404, detail="Item not found in cache")
        
    saved_path_str = item_meta.get("saved_path")
    orig_path = Path(saved_path_str)
    if not orig_path.exists():
        raise HTTPException(status_code=404, detail="Original file missing")
        
    info = {
        "id": item_id,
        "name": orig_path.name,
        "size": orig_path.stat().st_size,
        "gps": None,
        "timestamp": item_meta.get("timestamp")
    }
    
    # Always try a fresh extraction of ACTUAL METADATA to ensure the most accurate date is shown
    # If the file has no embedded EXIF/FFprobe/filename date, we keep the existing timestamp
    # instead of falling back to the server's file modification time.
    fresh_ts = extract_metadata_timestamp(orig_path)
    
    # If the fresh extraction is different from what we had in meta, update the log/cache
    if fresh_ts and fresh_ts != item_meta.get("timestamp"):
        item_meta["timestamp"] = fresh_ts
        metadata_cache.update(item_meta)
        
        # Update the log file immediately
        try:
            remaining_lines = []
            with open(META_LOG, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        m = json.loads(line)
                        if m.get("id") == item_id:
                            m["timestamp"] = fresh_ts
                            remaining_lines.append(json.dumps(m) + "\n")
                        else:
                            remaining_lines.append(line)
            with open(META_LOG, "w", encoding="utf-8") as f:
                f.writelines(remaining_lines)
        except:
            pass
            
    info["timestamp"] = item_meta.get("timestamp")
    
    try:
        if ext in {".jpg", ".jpeg", ".png", ".webp"}:
            from PIL import Image as PILImage
            from PIL.ExifTags import TAGS, GPSTAGS
            with PILImage.open(orig_path) as img:
                exif = img._getexif()
                if exif:
                    for tag_id, value in exif.items():
                        tag = TAGS.get(tag_id, tag_id)
                        if tag == 'DateTimeOriginal' and value:
                            pass
                    
                    gps_info = {}
                    if 34853 in exif: # GPSInfo
                        for key, val in exif[34853].items():
                            decode = GPSTAGS.get(key, key)
                            gps_info[decode] = val
                    if "GPSLatitude" in gps_info and "GPSLongitude" in gps_info:
                        def parse_dms(dms, ref):
                            dec = float(dms[0]) + float(dms[1])/60 + float(dms[2])/3600
                            return -dec if ref in ['S', 'W'] else dec
                        try:
                            lat = parse_dms(gps_info["GPSLatitude"], gps_info.get("GPSLatitudeRef", "N"))
                            lon = parse_dms(gps_info["GPSLongitude"], gps_info.get("GPSLongitudeRef", "E"))
                            info["gps"] = {"lat": lat, "lon": lon}
                        except Exception as e:
                            print(f"Error parsing GPS: {e}")
        elif ext in {".mp4", ".mov", ".avi", ".mkv"}:
            import subprocess
            import re
            cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(orig_path)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                meta = json.loads(result.stdout)
                tags = meta.get("format", {}).get("tags", {})
                
                loc = tags.get("location") or tags.get("com.apple.quicktime.location.ISO6709")
                if loc:
                    match = re.search(r'([+-]\d+\.\d+)([+-]\d+\.\d+)', str(loc))
                    if match:
                        info["gps"] = {"lat": float(match.group(1)), "lon": float(match.group(2))}
    except Exception as e:
        print(f"[INFO_ERROR] Could not extract metadata for {orig_path.name}: {e}")

    return info

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
        # Security validation (optional for thumbnails, but recommended)
        auth_token = x_device_token or token
        if auth_token:
            auth.get_device_info(auth_token) # Validate that the device exists
            
        # 1. Instant RAM search
        saved_path_str = metadata_cache.get_path(item_id)
        if not saved_path_str:
            print(f"[THUMB_DEBUG] ID not found in RAM cache: {item_id}")
            raise HTTPException(status_code=404, detail="Item not in cache")
            
        orig_path = Path(saved_path_str)
        if not orig_path.exists():
            print(f"[THUMB_DEBUG] Original file no longer exists: {saved_path_str}")
            raise HTTPException(status_code=404, detail="Original file missing")
        
        # 2. Check if it already exists on disk (searching multiple extensions)
        thumb_path_webp = CACHE_DIR / f"{item_id}.webp"
        thumb_path_jpg = CACHE_DIR / f"{item_id}.jpg"
        
        if thumb_path_webp.exists():
            return FileResponse(thumb_path_webp)
        if thumb_path_jpg.exists():
            return FileResponse(thumb_path_jpg)
            
        print(f"[THUMB_DEBUG] Generating new thumbnail for: {item_id}")
        
        # 3. Maintenance probability
        import random
        if random.random() < 0.02:
            background_tasks.add_task(maintain_cache, CACHE_DIR)

        # 4. Generation with Semaphore (CPU control)
        async with thumb_semaphore:
            # Re-verify after waiting in case another thread generated it
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
                            # Fallback to JPEG if WEBP fails (missing encoder on the system)
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
                print(f"[THUMB_GEN_ERROR] Critical failure generating thumbnail for {item_id}: {gen_err}")
                            
        raise HTTPException(status_code=404, detail="Thumbnail could not be generated")
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Thumbnail error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/api/media/file/{path:path}")
async def get_media_file(path: str, x_device_token: Optional[str] = Header(None), token: Optional[str] = Query(None)):
    """Serves a media file with device token validation (via header or query parameter)."""
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
        # 1. Try to extract authentic metadata from file (EXIF/FFprobe/filename)
        final_timestamp = extract_metadata_timestamp(file_path)
        
        # 2. If no authentic metadata, prioritize original_date from the client if provided
        if not final_timestamp and original_date:
            final_timestamp = original_date
            
        # 3. If still no timestamp, fallback to server mtime or now
        if not final_timestamp:
            try:
                mtime = file_path.stat().st_mtime
                final_timestamp = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            except:
                final_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

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
            
        # Sync RAM Cache
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

        # 4. Sync RAM Cache
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
                
            # 3. Reload full RAM Cache after deleting folder
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
