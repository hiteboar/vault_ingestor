from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Iterable, Optional

ByteStream = Iterable[bytes]

@dataclass
class IncomingMedia:
    source: str                 # "telegram" | "whatsapp"
    sender_id: str
    received_at: datetime
    content_type: str
    stream: ByteStream

    sender_name: Optional[str] = None
    suggested_filename: Optional[str] = None
    size_bytes: Optional[int] = None
    external_ids: Dict[str, str] = field(default_factory=dict)