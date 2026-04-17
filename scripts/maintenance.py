import json
import os
import shutil
import subprocess
from pathlib import Path
from PIL import Image
import hashlib
from dotenv import load_dotenv

# Cargar configuración
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

STORAGE_DIR = Path(os.getenv("STORAGE_DIR", str(BASE_DIR / "vault_storage"))).resolve()
META_LOG = STORAGE_DIR / "metadata.jsonl"
CACHE_DIR = STORAGE_DIR / ".cache" / "thumbnails"
TRASH_DIR = STORAGE_DIR / ".trash"

def ensure_dirs():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    TRASH_DIR.mkdir(parents=True, exist_ok=True)

def generate_thumb(item):
    item_id = item.get("id")
    orig_path = Path(item.get("saved_path", ""))
    
    if not item_id or not orig_path.exists():
        return False

    thumb_path = CACHE_DIR / f"{item_id}.jpg"
    if thumb_path.exists():
        return False

    ext = orig_path.suffix.lower()
    img_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    vid_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

    try:
        if ext in img_exts:
            with Image.open(orig_path) as img:
                img.convert('RGB').thumbnail((400, 400))
                img.save(thumb_path, "JPEG", quality=85)
            return True
        elif ext in vid_exts:
            cmd = [
                "ffmpeg", "-y", "-i", str(orig_path),
                "-ss", "00:00:01", "-vframes", "1",
                "-q:v", "2", str(thumb_path)
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return thumb_path.exists()
    except Exception:
        pass
    return False

def run_thumbnails():
    print(f"🚀 Generando miniaturas faltantes...")
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

def run_cleanup(dry_run=True):
    print(f"🧹 Iniciando limpieza de huérfanos ({'DRY RUN' if dry_run else 'EJECUCIÓN REAL'})...")
    
    if not META_LOG.exists():
        print("❌ No hay log de metadatos.")
        return

    # 1. Cargar metadatos y verificar archivos faltantes
    active_items = []
    missing_files = 0
    with open(META_LOG, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                p = Path(item["saved_path"])
                if p.exists():
                    active_items.append(item)
                else:
                    missing_files += 1
                    print(f"  [LOG] Archivo no encontrado en disco: {p.name}")

    if not dry_run and missing_files > 0:
        # Reescribir log sin los desaparecidos
        with open(META_LOG, "w", encoding="utf-8") as f:
            for item in active_items:
                f.write(json.dumps(item) + "\n")
        print(f"  ✨ Registro de metadatos limpiado ({missing_files} entradas eliminadas).")

    # 2. Buscar archivos en disco que no estén en metadatos
    registered_paths = {Path(i["saved_path"]).resolve() for i in active_items}
    orphans_found = 0
    
    # Escaneamos STORAGE_DIR recursivamente
    for p in STORAGE_DIR.rglob("*"):
        if p.is_file() and not p.name.startswith(".") and p != META_LOG:
            # Ignorar carpetas de sistema
            if ".cache" in p.parts or ".trash" in p.parts or ".vault" in p.parts:
                continue
                
            if p.resolve() not in registered_paths:
                orphans_found += 1
                if dry_run:
                    print(f"  [DISK] Huérfano detectado: {p.relative_to(STORAGE_DIR)}")
                else:
                    target = TRASH_DIR / p.relative_to(STORAGE_DIR).name
                    if target.exists():
                        target = TRASH_DIR / f"{int(os.path.getmtime(p))}_{p.name}"
                    shutil.move(p, target)
                    print(f"  [DISK] Movido a .trash: {p.name}")

    # 3. Limpiar miniaturas sin uso
    active_ids = {i.get("id") for i in active_items if i.get("id")}
    orphans_thumbs = 0
    for t in CACHE_DIR.glob("*.jpg"):
        tid = t.stem
        if tid not in active_ids:
            orphans_thumbs += 1
            if dry_run:
                print(f"  [THUMB] Miniatura sin uso: {t.name}")
            else:
                t.unlink()

    print(f"\n📊 Resumen de limpieza:")
    print(f"  - Entradas de log inválidas: {missing_files}")
    print(f"  - Archivos huérfanos en disco: {orphans_found}")
    print(f"  - Miniaturas sin uso: {orphans_thumbs}")
    
    if dry_run:
        print("\n⚠️  Esto fue un DRY RUN. Usa --force para aplicar cambios.")

if __name__ == "__main__":
    import sys
    ensure_dirs()
    
    if "--thumbnails" in sys.argv:
        run_thumbnails()
    elif "--cleanup" in sys.argv:
        force = "--force" in sys.argv
        run_cleanup(dry_run=not force)
    else:
        print("Opciones:")
        print("  --thumbnails      Genera miniaturas faltantes")
        print("  --cleanup         Busca archivos huérfanos (modo seguro)")
        print("  --cleanup --force Ejecuta la limpieza real (mueve a .trash)")
