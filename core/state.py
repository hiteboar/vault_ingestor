from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, Optional

class ChatStateStore:
    """
    Estado por chat persistente:
      - context (carpeta)
      - require_original (bool): True => rechaza 'photo' y exige 'document' para imágenes
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
        return self._state[chat_id]

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
    def create_invite(self, folder: str) -> str:
        import string, random
        if "_invites" not in self._state:
            self._state["_invites"] = {}
        chars = string.ascii_uppercase + string.digits
        code = ''.join(random.choices(chars, k=8))
        self._state["_invites"][code] = folder
        self._save()
        return code

    def claim_invite(self, chat_id: str, code: str) -> Optional[str]:
        invites = self._state.get("_invites", {})
        if code not in invites:
            return None
        folder = invites.pop(code)
        
        chat = self._chat(chat_id)
        if "allowed_folders" not in chat:
            chat["allowed_folders"] = []
            
        if folder not in chat["allowed_folders"]:
            chat["allowed_folders"].append(folder)
            
        self._save()
        return folder

    def get_allowed_folders(self, chat_id: str) -> list[str]:
        chat = self._chat(chat_id)
        return chat.get("allowed_folders", [])