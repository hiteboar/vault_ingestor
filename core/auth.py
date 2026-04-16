import json
import secrets
import string
import time
from pathlib import Path
from typing import Dict, Optional, List

class AuthManager:
    """
    Manages mobile device linking via 6-digit PINs and persistent tokens.
    """
    def __init__(self, state_dir: Path):
        self.state_file = state_dir / "linked_devices.json"
        self.pin_file = state_dir / "pending_pins.json"
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        
        # Load linked devices: {token: {device_info, linked_at}}
        self.linked_devices = self._load(self.state_file)
        
        # Temporary PINs: {pin: {token, expires_at}}
        self.pending_pins = {}

    def _load(self, path: Path) -> Dict:
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save(self, path: Path, data: Dict):
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def generate_pin(self, role: str = "admin", allowed_folders: List[str] = None) -> str:
        """Generates a random 6-digit PIN valid for 5 minutes with specific scopes."""
        if allowed_folders is None:
            allowed_folders = ["*"]
            
        pin = ''.join(secrets.choice(string.digits) for _ in range(6))
        token = secrets.token_hex(32)
        expires_at = time.time() + 300 # 5 minutes
        
        self.pending_pins[pin] = {
            "token": token,
            "role": role,
            "allowed_folders": allowed_folders,
            "expires_at": expires_at
        }
        return pin

    def verify_pin(self, pin: str) -> Optional[str]:
        """Checks if a PIN is valid and returns the permanent token."""
        if pin not in self.pending_pins:
            return None
        
        session = self.pending_pins.pop(pin)
        if time.time() > session["expires_at"]:
            return None
            
        token = session["token"]
        self.linked_devices[token] = {
            "role": session.get("role", "admin"),
            "allowed_folders": session.get("allowed_folders", ["*"]),
            "linked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "last_seen": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        self._save(self.state_file, self.linked_devices)
        return token

    def is_token_valid(self, token: str) -> bool:
        """Validates a permanent device token."""
        if token in self.linked_devices:
            # Update last seen
            self.linked_devices[token]["last_seen"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            self._save(self.state_file, self.linked_devices)
            return True
        return False

    def get_device_info(self, token: str) -> Optional[Dict]:
        """Returns the complete device session if token is valid."""
        if self.is_token_valid(token):
            return self.linked_devices[token]
        return None

    def get_admins_count(self) -> int:
        """Counts how many admins exist."""
        return sum(1 for d in self.linked_devices.values() if d.get("role") == "admin")

    def revoke_token(self, token: str):
        if token in self.linked_devices:
            del self.linked_devices[token]
            self._save(self.state_file, self.linked_devices)
