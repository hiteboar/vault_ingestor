import os
import sys
import struct
from pathlib import Path
from datetime import datetime, timezone

# Add parent directory to path so we can import the api module
sys.path.append(os.getcwd())

from api.main import extract_mp4_creation_time, extract_metadata_timestamp

def test_mp4_parser():
    print("--- Test: Pure Python MP4 Creation Time Parser ---")
    
    # Create a dummy MP4 file containing a mock mvhd atom
    # Difference between Jan 1, 1904 (Apple epoch) and Jan 1, 1970 (Unix epoch) is 2082844800 seconds
    apple_epoch_diff = 2082844800
    
    # 2026-05-30T12:00:00Z in Unix timestamp is 1777550400
    expected_unix_ts = 1777550400
    apple_ts = apple_epoch_diff + expected_unix_ts
    
    # Let's craft the mvhd atom:
    # 4 bytes size: e.g. 108 bytes -> \x00\x00\x00\x6c
    # 4 bytes name: b'mvhd'
    # 1 byte version: \x00 (version 0)
    # 3 bytes flags: \x00\x00\x00
    # 4 bytes creation time: Big-endian unsigned int
    mvhd_atom = b'\x00\x00\x00\x6cmvhd\x00\x00\x00\x00' + struct.pack(">I", apple_ts)
    
    # Create the dummy file with the mvhd atom inside it
    dummy_file = Path("test_dummy_video.mp4")
    try:
        # Write some garbage, then the mvhd atom to simulate a real file
        dummy_file.write_bytes(b'moov' + b'\x00' * 10 + mvhd_atom + b'\x00' * 20)
        
        # Test direct parser
        extracted = extract_mp4_creation_time(dummy_file)
        print(f"Extracted timestamp: {extracted}")
        assert extracted == "2026-04-30T12:00:00Z", f"Expected 2026-04-30T12:00:00Z, got {extracted}"
        
        # Test integration via extract_metadata_timestamp
        integrated = extract_metadata_timestamp(dummy_file, content_type="video/mp4")
        print(f"Integrated extracted timestamp: {integrated}")
        assert integrated == "2026-04-30T12:00:00Z", f"Expected 2026-04-30T12:00:00Z, got {integrated}"
        
        print("[OK] MP4 creation time parser test passed successfully!")
    finally:
        # Cleanup
        if dummy_file.exists():
            dummy_file.unlink()

if __name__ == "__main__":
    try:
        test_mp4_parser()
    except Exception as e:
        print(f"[ERROR] Test failed: {e}")
        sys.exit(1)
