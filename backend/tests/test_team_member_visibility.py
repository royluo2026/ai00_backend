import ast
import unittest
from pathlib import Path


class TeamMemberVisibilityTests(unittest.TestCase):
    def test_member_listing_checks_current_team_or_admin_scope(self):
        path = Path(__file__).resolve().parents[1] / "routers/teams.py"
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == "list_team_members")
        source = ast.get_source_segment(text, node) or ""
        self.assertIn('current_user.get("team_id")', source)
        self.assertIn('grant.get("scope_gid")', source)
        self.assertIn('role != "super_admin"', source)
        self.assertIn("HTTPException(status_code=403", source)


if __name__ == "__main__":
    unittest.main()