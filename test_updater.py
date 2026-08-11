import os
import shutil
import tempfile
import unittest
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(PROJECT_ROOT))

from core.manager import UpdateManager

class TestUpdateManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.storage_dir = self.temp_dir / "vault_storage"
        self.storage_dir.mkdir()
        
        # Create some fake project files to test backup and rollback
        self.fake_project_file = self.temp_dir / "app.py"
        self.fake_project_file.write_text("print('hello world')", encoding="utf-8")
        
        self.manager = UpdateManager(self.temp_dir, self.storage_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_state_management(self):
        # Default state
        state = self.manager._get_state()
        self.assertEqual(state["pending_verification"], False)
        
        # Set and get state
        state["pending_verification"] = True
        self.manager._set_state(state)
        
        new_state = self.manager._get_state()
        self.assertTrue(new_state["pending_verification"])

    def test_create_local_backup(self):
        backup_dir = self.manager.create_local_backup()
        self.assertTrue(Path(backup_dir).exists())
        self.assertTrue((Path(backup_dir) / "app.py").exists())
        
        state = self.manager._get_state()
        self.assertNotEqual(state["last_stable"], "Ninguna")

    def test_rollback_offline(self):
        # 1. Create initial state
        self.manager.create_local_backup()
        
        # 2. Simulate a broken update
        self.fake_project_file.write_text("syntax error!!! broken!!!", encoding="utf-8")
        
        # 3. Perform rollback
        success, msg = self.manager.rollback_to_last_stable("Test fallback")
        
        self.assertTrue(success)
        self.assertEqual(self.fake_project_file.read_text(encoding="utf-8"), "print('hello world')")
        
        state = self.manager._get_state()
        self.assertTrue(state["verification_failed"])
        self.assertFalse(state["pending_verification"])

if __name__ == '__main__':
    unittest.main()
