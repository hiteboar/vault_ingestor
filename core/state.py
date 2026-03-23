import json
import datetime
import string
import random
from pathlib import Path
from typing import Any, Dict, Optional, List

class ChatStateStore:
    """
    Estado por chat persistente:
      - context (carpeta)
      - require_original (bool)
      - access (dict): {folder_name: tag}
    """
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._state: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._state = {}
            return
        try:
            obj = json.loads(self.path.read_text(encoding="utf-8"))
            self._state = obj if isinstance(obj, dict) else {}
        except Exception:
            self._state = {}

    def _save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def _chat(self, chat_id: str) -> Dict[str, Any]:
        if chat_id not in self._state or not isinstance(self._state.get(chat_id), dict):
            self._state[chat_id] = {}
        # Ensure access exists
        if "access" not in self._state[chat_id]:
           self._state[chat_id]["access"] = {}
        return self._state[chat_id]

    # ---- Global Settings ----
    def get_global_setting(self, key: str, default: Any) -> Any:
        if "_global" not in self._state:
            return default
        return self._state["_global"].get(key, default)

    def set_global_setting(self, key: str, value: Any) -> None:
        if "_global" not in self._state:
            self._state["_global"] = {}
        self._state["_global"][key] = value
        self._save()

    # ---- Context (carpeta) ----
    def get_context(self, chat_id: str, default: str) -> str:
        chat = self._chat(chat_id)
        ctx = chat.get("context")
        return ctx if isinstance(ctx, str) and ctx.strip() else default

    def set_context(self, chat_id: str, context: str) -> None:
        chat = self._chat(chat_id)
        chat["context"] = context
        self._save()

    def clear_context(self, chat_id: str) -> None:
        chat = self._chat(chat_id)
        if "context" in chat:
            chat.pop("context", None)
            self._save()

    # ---- Require original ----
    def get_require_original(self, chat_id: str, default: bool) -> bool:
        chat = self._chat(chat_id)
        val = chat.get("require_original")
        if isinstance(val, bool):
            return val
        return default

    def set_require_original(self, chat_id: str, require_original: bool) -> None:
        chat = self._chat(chat_id)
        chat["require_original"] = bool(require_original)
        self._save()

    # ---- Pending action ----
    def get_pending_action(self, chat_id: str) -> Optional[Dict[str, Any]]:
        chat = self._chat(chat_id)
        return chat.get("pending_action")

    def set_pending_action(self, chat_id: str, action: Dict[str, Any]) -> None:
        chat = self._chat(chat_id)
        chat["pending_action"] = action
        self._save()

    def clear_pending_action(self, chat_id: str) -> None:
        chat = self._chat(chat_id)
        if "pending_action" in chat:
            chat.pop("pending_action", None)
            self._save()

    # ---- Invitations & Access ----
    def create_invite(self, folder: str, tag: str = "invitado") -> str:
        if "_invites" not in self._state:
            self._state["_invites"] = {}
        
        chars = string.ascii_uppercase + string.digits
        code = ''.join(random.choices(chars, k=8))
        
        self._state["_invites"][code] = {
            "folder": folder,
            "tag": tag,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        self._save()
        return code

    def _prune_invites(self) -> None:
        if "_invites" not in self._state:
            return
        
        now = datetime.datetime.now(datetime.timezone.utc)
        to_delete = []
        for code, info in self._state["_invites"].items():
            try:
                if not isinstance(info, dict) or "created_at" not in info:
                    to_delete.append(code)
                    continue
                created_at = datetime.datetime.fromisoformat(info["created_at"])
                if (now - created_at).total_seconds() > 24 * 3600:
                    to_delete.append(code)
            except (KeyError, ValueError, TypeError):
                to_delete.append(code)
                
        if to_delete:
            for c in to_delete:
                self._state["_invites"].pop(c, None)
            self._save()

    def claim_invite(self, chat_id: str, code: str) -> Optional[str]:
        self._prune_invites()
        invites = self._state.get("_invites", {})
        if code not in invites:
            return None
        
        info = invites.pop(code)
        if isinstance(info, str):
            folder = info
            tag = "invitado_legacy"
        else:
            folder = info["folder"]
            tag = info["tag"]
        
        chat = self._chat(chat_id)
        chat["access"][folder] = {
            "tag": tag,
            "created_at": info.get("created_at") if isinstance(info, dict) else datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        # Limpiar campo antiguo
        chat.pop("allowed_folders", None)
            
        self._save()
        return folder

    def get_allowed_folders(self, chat_id: str) -> list[str]:
        self._prune_access(chat_id)
        chat = self._chat(chat_id)
        access = chat.get("access", {})
        if isinstance(access, dict):
            return list(access.keys())
        return []

    def is_user_allowed(self, chat_id: str) -> bool:
        """Determina si un usuario tiene algún tipo de acceso (invitación activa)."""
        self._prune_access(chat_id)
        chat = self._chat(chat_id)
        access = chat.get("access", {})
        return bool(access and isinstance(access, dict))

    def _prune_access(self, chat_id: str) -> None:
        """Elimina accesos que han caducado (si se desea que el acceso dure lo mismo que la invitación)."""
        chat = self._chat(chat_id)
        access = chat.get("access", {})
        if not isinstance(access, dict):
            return
            
        now = datetime.datetime.now(datetime.timezone.utc)
        to_delete = []
        for folder, info in access.items():
            if not isinstance(info, dict) or "created_at" not in info:
                # Si no tiene metadatos o no es el formato nuevo, lo dejamos (retrocompatibilidad)
                continue
            try:
                created_at = datetime.datetime.fromisoformat(info["created_at"])
                if (now - created_at).total_seconds() > 24 * 3600:
                    to_delete.append(folder)
            except (ValueError, TypeError):
                continue
                
        if to_delete:
            for f in to_delete:
                access.pop(f, None)
            self._save()

    def get_access_report(self) -> dict:
        self._prune_invites()
        report = {
            "pending": [],
            "active": []
        }
        
        # Pendientes
        for code, info in self._state.get("_invites", {}).items():
            if isinstance(info, dict):
                report["pending"].append({
                    "code": code,
                    "folder": info.get("folder"),
                    "tag": info.get("tag"),
                    "created_at": info.get("created_at")
                })
            
        # Activos
        for chat_id, data in self._state.items():
            if chat_id.startswith("_") or not isinstance(data, dict):
                continue
            access = data.get("access", {})
            for folder, data in access.items():
                tag = data.get("tag", "invitado") if isinstance(data, dict) else data
                report["active"].append({
                    "chat_id": chat_id,
                    "folder": folder,
                    "tag": tag
                })
        return report

    def revoke_access(self, target: str) -> bool:
        """Revoca por chat_id o por tag."""
        changed = False
        
        # Caso 1: target es un chat_id exacto (numérico como string)
        if target in self._state and isinstance(self._state[target], dict):
            if "access" in self._state[target]:
                self._state[target].pop("access", None)
                changed = True
        
        # Caso 2: target es un tag
        for chat_id, data in self._state.items():
            if chat_id.startswith("_") or not isinstance(data, dict):
                continue
            access = data.get("access", {})
            if isinstance(access, dict):
                to_remove = []
                for f, data in access.items():
                    tag = data.get("tag") if isinstance(data, dict) else data
                    if tag == target:
                        to_remove.append(f)
                
                if to_remove:
                    for f in to_remove:
                        access.pop(f)
                    changed = True
                    
        if changed:
            self._save()
        return changed