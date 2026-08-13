import unittest
from pathlib import Path


class DeviceDomainBoundaryTests(unittest.TestCase):
    def test_device_storage_is_not_implemented_in_base(self):
        root = Path(__file__).resolve().parents[2]
        base_adapter = root / "backend/capabilities/local_runtime_next.py"
        device = (root / "plugins/device/device_backend/control_plane.py").read_text(encoding="utf-8")
        connection = (root / "plugins/device/device_backend/data/connection.py").read_text(encoding="utf-8")
        self.assertFalse(base_adapter.exists())
        self.assertNotIn("CREATE TABLE", device.upper())
        self.assertNotIn("backend.db", device)
        self.assertIn('os.getenv("AI00_DEVICE_DB_URL"', connection)
        self.assertIn("AI00_LOCAL_RUNTIME_DB_URL is deprecated", connection)
        self.assertIn("owner_user_gid=%s", device)


if __name__ == "__main__":
    unittest.main()
