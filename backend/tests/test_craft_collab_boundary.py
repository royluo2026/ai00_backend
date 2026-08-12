import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class CraftCollabBoundaryTests(unittest.TestCase):
    def test_base_collab_is_only_a_compatibility_import(self):
        source = (ROOT / "backend/routers/collab.py").read_text(encoding="utf-8")
        self.assertNotIn("workmanship_", source)
        self.assertIn("plugins.craft.craft_backend.routers.collab", source)

if __name__ == "__main__":
    unittest.main()
