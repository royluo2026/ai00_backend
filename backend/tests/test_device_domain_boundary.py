import unittest
from pathlib import Path


class DeviceDomainBoundaryTests(unittest.TestCase):
    def test_device_storage_is_not_implemented_in_base(self):
        root = Path(__file__).resolve().parents[2]
        base_adapter = (root / "backend/capabilities/local_runtime_next.py").read_text(encoding="utf-8")
        device = (root / "plugins/device/device_backend/control_plane.py").read_text(encoding="utf-8")
        connection = (root / "plugins/device/device_backend/data/connection.py").read_text(encoding="utf-8")
        self.assertNotIn("workmanship_runtime_", base_adapter)
        self.assertNotIn("CREATE TABLE", device.upper())
        self.assertNotIn("backend.db", device)
        self.assertIn("AI00_DEVICE_DB_URL", connection)
        self.assertIn("owner_user_gid=%s", device)


if __name__ == "__main__":
    unittest.main()
