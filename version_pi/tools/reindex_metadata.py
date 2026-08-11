import json
import os
import sys
from pathlib import Path

# Add root to path so we can import extract_timestamp and META_LOG
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(ROOT_DIR))

# Ensure we can import from api
try:
    from api.main import extract_timestamp, META_LOG
except ImportError:
    # Fallback if structure is different
    from vault_ingestor.api.main import extract_timestamp, META_LOG

def reindex():
    if not META_LOG.exists():
        print(f"Error: Metadata file not found at {META_LOG}")
        print("If you have configured a different path in .env, make sure the script detects it.")
        return

    print(f"🚀 Starting date re-indexing in {META_LOG}...")
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
                        print(f"    Old: {old_ts}")
                        print(f"    New: {new_ts}")
                        item["timestamp"] = new_ts
                        changes += 1
                    updated_items.append(item)
                else:
                    print(f"  [SKIP] File not found physically: {item.get('name')}")
                    updated_items.append(item)
            except Exception as e:
                print(f"  [ERR] Error processing line: {e}")

    # Save changes
    if changes > 0:
        with open(META_LOG, "w", encoding="utf-8") as f:
            for item in updated_items:
                f.write(json.dumps(item) + "\n")
        print(f"\n✅ Re-indexing completed. {changes} records updated.")
    else:
        print("\n✨ No changes needed. All timestamps are up to date.")

if __name__ == "__main__":
    reindex()
