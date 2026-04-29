import json
import os
import sys
from pathlib import Path

# Add root to path so we can import extract_timestamp and META_LOG
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from api.main import extract_timestamp, META_LOG

def reindex():
    if not META_LOG.exists():
        print(f"Error: No se encuentra el archivo de metadatos en {META_LOG}")
        print("Si has configurado una ruta distinta en .env, asegúrate de que el script la detecte.")
        return

    print(f"🚀 Iniciando re-indexación de fechas en {META_LOG}...")
    updated_items = []
    changes = 0
    
    with open(META_LOG, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                saved_path = Path(item.get("saved_path", ""))
                
                if saved_path.exists():
                    old_ts = item.get("timestamp")
                    new_ts = extract_timestamp(saved_path)
                    
                    if old_ts != new_ts:
                        print(f"  [UPDATE] {item.get('name')}:")
                        print(f"    Antiguo: {old_ts}")
                        print(f"    Nuevo:   {new_ts}")
                        item["timestamp"] = new_ts
                        changes += 1
                    updated_items.append(item)
                else:
                    print(f"  [SKIP] Archivo no encontrado físicamente: {item.get('name')}")
                    updated_items.append(item)
            except Exception as e:
                print(f"  [ERR] Error procesando línea: {e}")

    # Guardar cambios
    if changes > 0:
        with open(META_LOG, "w", encoding="utf-8") as f:
            for item in updated_items:
                f.write(json.dumps(item) + "\n")
        print(f"\n✅ Re-indexación completada. Se han actualizado {changes} registros.")
    else:
        print("\n✨ No se encontraron cambios necesarios. Todos los timestamps están al día.")

if __name__ == "__main__":
    reindex()
