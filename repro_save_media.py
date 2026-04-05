import sys
from pathlib import Path
from datetime import datetime, timezone
import io

# Add current dir to path to import core
sys.path.append(str(Path.cwd()))

from core.models import IncomingMedia
from core.pipeline import process_one

def test_save_media_with_formats():
    base_dir = Path("test_data")
    base_dir.mkdir(exist_ok=True)
    meta_log = base_dir / "meta.jsonl"
    
    media = IncomingMedia(
        source="test",
        sender_id="123",
        sender_name="Tester",
        received_at=datetime.now(timezone.utc),
        content_type="image/jpeg",
        size_bytes=100,
        suggested_filename="test.jpg",
        stream=iter([b"dummy data"]),
        external_ids={"msg_id": "1"},
    )
    
    formats_dict = {"image/jpeg": ".jpg"}
    
    print("Attempting to process media with formats_dict...")
    try:
        path, is_dup, existing, file_hash = process_one(
            base_dir,
            meta_log,
            media,
            formats_dict=formats_dict
        )
        print(f"Success! Saved to {path}")
    except TypeError as e:
        print(f"Failed with TypeError: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Failed with unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_save_media_with_formats()
