import json
import os
from pathlib import Path
from typing import List, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Vault API")

# Enable CORS for the webapp
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent.parent
META_LOG = BASE_DIR / "meta.jsonl"

@app.get("/api/items")
async def get_items():
    if not META_LOG.exists():
        return []
    
    items = []
    try:
        with open(META_LOG, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    # Convert absolute saved_path to a relative path from BASE_DIR
                    saved_path = Path(item["saved_path"])
                    try:
                        rel = saved_path.relative_to(BASE_DIR)
                        item["web_path"] = str(rel).replace("\\", "/")
                    except ValueError:
                        # Fallback if path is outside BASE_DIR (unlikely)
                        item["web_path"] = saved_path.name
                    items.append(item)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    # Reverse to show newest first
    return list(reversed(items))

# Serve media files
# StaticFiles will serve everything in the base directory
# We can filter this later for security if needed
app.mount("/api/media", StaticFiles(directory=str(BASE_DIR)), name="media")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
