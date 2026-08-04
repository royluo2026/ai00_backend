import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class CraftOntologyBoundaryTests(unittest.TestCase):
    def test_base_ontology_is_only_a_compatibility_import(self):
        source = (ROOT / "backend/routers/ontology.py").read_text(encoding="utf-8")
        self.assertNotIn("workmanship_", source)
        self.assertIn("plugins.craft.craft_backend.routers.ontology", source)

    def test_craft_table_name_converter_rejects_base_tables(self):
        from plugins.craft.craft_backend.table_names import craft_entity_table_name

        self.assertEqual(craft_entity_table_name("bop.bop_entries"), "workmanship_bop_bop_entries")
        self.assertEqual(craft_entity_table_name("knowledge.onto_classes"), "workmanship_onto_classes")
        with self.assertRaises(ValueError):
            craft_entity_table_name("auth.users")

    def test_rule_engine_uses_craft_connection(self):
        source = (ROOT / "plugins/craft/craft_backend/rule_engine/checker.py").read_text(encoding="utf-8")
        self.assertIn("from ..data.connection import get_conn", source)
        self.assertNotIn("backend.db.connection", source)


if __name__ == "__main__":
    unittest.main()
