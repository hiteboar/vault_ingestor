import json
import os
import shutil
import subprocess
from pathlib import Path
from PIL import Image
import hashlib
import time
from datetime import datetime
from dotenv import load_dotenv

# Cargar configuración
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

STORAGE_DIR = Path(os.getenv("STORAGE_DIR", str(BASE_DIR / "vault_storage"))).resolve()
UPLOAD_DIR = STORAGE_DIR / "uploaded_files"
META_LOG = STORAGE_DIR / "metadata.jsonl"
CACHE_DIR = STORAGE_DIR / ".cache" / "thumbnails"
TRASH_DIR = STORAGE_DIR / ".trash"

def ensure_dirs():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    TRASH_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

def generate_thumb(item):
    """Generate thumbnail for an item if it doesn't exist."""
    item_id = item.get("id")
    orig_path = Path(item.get("saved_path", ""))
    
    if not item_id or not orig_path.exists():
        return False

    thumb_path_webp = CACHE_DIR / f"{item_id}.webp"
    thumb_path_jpg = CACHE_DIR / f"{item_id}.jpg"

    if thumb_path_webp.exists() or thumb_path_jpg.exists():
        return False

    ext = orig_path.suffix.lower()
    img_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    vid_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

    try:
        if ext in img_exts:
            with Image.open(orig_path) as img:
                if img.mode in ("RGBA", "P"): img = img.convert("RGB")
                img.thumbnail((300, 300))
                try:
                    img.save(thumb_path_webp, "WEBP", quality=70)
                except Exception:
                    img.save(thumb_path_jpg, "JPEG", quality=75)
            return True
        elif ext in vid_exts:
            # First try generating a temp JPG to then convert or keep
            tmp_jpg = CACHE_DIR / f"{item_id}.tmp.jpg"
            cmd = [
                "ffmpeg", "-y", "-i", str(orig_path),
                "-ss", "00:00:01", "-vframes", "1",
                "-q:v", "4", str(tmp_jpg)
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            if tmp_jpg.exists():
                with Image.open(tmp_jpg) as img:
                    img.thumbnail((300, 300))
                    try:
                        img.save(thumb_path_webp, "WEBP", quality=70)
                        tmp_jpg.unlink()
                    except Exception:
                        img.save(thumb_path_jpg, "JPEG", quality=75)
                        tmp_jpg.unlink()
                return True
    except Exception:
        pass
    return False

def run_thumbnails():
    """Analiza registros en metadatos y genera miniaturas faltantes."""
    print(f"🚀 Generando miniaturas desde metadatos...")
    count = 0
    generated = 0
    if not META_LOG.exists(): return
    
    with open(META_LOG, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                if "id" not in item:
                    item["id"] = hashlib.md5(item["saved_path"].encode()).hexdigest()
                if generate_thumb(item):
                    generated += 1
                count += 1
    print(f"✅ Finalizado: {generated} nuevas miniaturas.")

def run_full_scan():
    """Escanea el disco físicamente, registra archivos nuevos y genera miniaturas."""
    print(f"🔍 Iniciando escaneo completo del sistema de archivos...")
    ensure_dirs()
    
    # 1. Cargar IDs ya registrados
    registered_ids = set()
    if META_LOG.exists():
        with open(META_LOG, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    if "id" in item: registered_ids.add(item["id"])

    new_items = []
    found_count = 0
    
    # 2. Recorrer UPLOAD_DIR
    for p in UPLOAD_DIR.rglob("*"):
        if p.is_file() and not p.name.startswith("."):
            # Ignorar carpetas de sistema si estuvieran dentro por error
            if ".cache" in p.parts or ".trash" in p.parts or ".vault" in p.parts:
                continue
                
            found_count += 1
            item_id = hashlib.md5(str(p.resolve()).encode()).hexdigest()
            
            if item_id not in registered_ids:
                # Determinar contexto (Carpeta)
                try:
                    rel = p.relative_to(UPLOAD_DIR)
                    parts = rel.parts
                    
                    # Estructura YYYY/MM/...
                    if len(parts) >= 3 and parts[0].isdigit() and len(parts[0]) == 4:
                        context = "root"
                    elif len(parts) >= 2:
                        context = parts[0]
                    else:
                        context = "root"
                except Exception:
                    context = "root"

                item = {
                    "id": item_id,
                    "name": p.name,
                    "saved_path": str(p.resolve()),
                    "timestamp": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "source": "manual_scan",
                    "context": context
                }
                new_items.append(item)
                registered_ids.add(item_id)
                print(f"  [NUEVO] Registrado: {p.name} en carpeta '{context}'")

    # 3. Guardar nuevos archivos en el log
    if new_items:
        with open(META_LOG, "a", encoding="utf-8") as f:
            for item in new_items:
                f.write(json.dumps(item) + "\n")
        print(f"✨ Se han añadido {len(new_items)} archivos nuevos a la app.")

    # 4. Generar miniaturas para TODO lo que falte
    print(f"🖼️ Verificando miniaturas para {found_count} archivos...")
    generated = 0
    if META_LOG.exists():
        with open(META_LOG, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    if generate_thumb(json.loads(line)):
                        generated += 1
    print(f"✅ Proceso finalizado. Total analizado: {found_count}. Miniaturas creadas: {generated}.")

def run_cleanup(dry_run=True):
    """Limpia registros muertos y archivos no registrados."""
    print(f"🧹 Limpieza de huérfanos ({'DRY RUN' if dry_run else 'REAL'})...")
    ensure_dirs()
    if not META_LOG.exists(): return

    # 1. Verificar registros
    active_items = []
    missing_files = 0
    with open(META_LOG, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                if Path(item["saved_path"]).exists():
                    active_items.append(item)
                else:
                    missing_files += 1
                    print(f"  [LOG] Registro sin archivo: {item['name']}")

    if not dry_run and missing_files > 0:
        with open(META_LOG, "w", encoding="utf-8") as f:
            for item in active_items:
                f.write(json.dumps(item) + "\n")

    # 2. Buscar archivos no registrados
    reg_paths = {Path(i["saved_path"]).resolve() for i in active_items}
    orphans = 0
    for p in UPLOAD_DIR.rglob("*"):
        if p.is_file() and not p.name.startswith(".") and p.resolve() not in reg_paths:
            orphans += 1
            if dry_run:
                print(f"  [DISK] Archivo no registrado: {p.name}")
            else:
                target = TRASH_DIR / p.name
                shutil.move(p, target)
                print(f"  [DISK] Movido a .trash: {p.name}")

    print(f"📊 Resumen: {missing_files} registros muertos, {orphans} archivos huérfanos.")

if __name__ == "__main__":
    import sys
    ensure_dirs()
    if "--scan" in sys.argv:
        run_full_scan()
    elif "--cleanup" in sys.argv:
        force = "--force" in sys.argv
        run_cleanup(dry_run=not force)
    elif "--thumbnails" in sys.argv:
        run_thumbnails()
    else:
        print("Vault Maintenance Tool")
        print("  --scan            Escanea disco y registra todo (Recomendado)")
        print("  --thumbnails      Solo genera miniaturas de lo ya registrado")
        print("  --cleanup         Busca archivos huérfanos")
        print("  --cleanup --force Ejecuta la limpieza")
