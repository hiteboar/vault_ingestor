import os
from pathlib import Path
from typing import Set

def add_allowed_chat_id(env_path: Path, chat_id: str) -> None:
    """Añade un Chat ID a ALLOWED_CHAT_IDS en el archivo .env."""
    if not env_path.exists():
        env_path.write_text(f"ALLOWED_CHAT_IDS={chat_id}\n", encoding="utf-8")
        return

    lines = env_path.read_text(encoding="utf-8").splitlines()
    new_lines = []
    found = False
    
    for line in lines:
        if line.startswith("ALLOWED_CHAT_IDS="):
            found = True
            val = line.split("=", 1)[1].strip()
            ids = set(part.strip() for part in val.split(",") if part.strip())
            ids.add(chat_id)
            new_lines.append(f"ALLOWED_CHAT_IDS={','.join(sorted(ids))}")
        else:
            new_lines.append(line)
            
    if not found:
        new_lines.append(f"ALLOWED_CHAT_IDS={chat_id}")
        
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

def remove_allowed_chat_id(env_path: Path, chat_id: str) -> None:
    """Elimina un Chat ID de ALLOWED_CHAT_IDS en el archivo .env."""
    if not env_path.exists():
        return

    lines = env_path.read_text(encoding="utf-8").splitlines()
    new_lines = []
    
    for line in lines:
        if line.startswith("ALLOWED_CHAT_IDS="):
            val = line.split("=", 1)[1].strip()
            ids = set(part.strip() for part in val.split(",") if part.strip())
            if chat_id in ids:
                ids.remove(chat_id)
            if ids:
                new_lines.append(f"ALLOWED_CHAT_IDS={','.join(sorted(ids))}")
            # Si se queda vacío, podemos optar por dejar la clave vacía o quitar la línea. 
            # Dejaremos la clave vacía para mantener la estructura.
            else:
                new_lines.append("ALLOWED_CHAT_IDS=")
        else:
            new_lines.append(line)
            
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
