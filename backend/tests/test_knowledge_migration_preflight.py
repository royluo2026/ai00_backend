import unittest

from backend.scripts.knowledge_migration_preflight import evaluate


class KnowledgeMigrationPreflightTests(unittest.TestCase):
    def _complete_env(self):
        env = {
            "AI00_DDL_DB_URL": "mysql://ddl:secret@db:2881/workmanship",
            "USERS_DB_URL": "mysql://base:secret@db:2881/workmanship",
            "AI00_KNOWLEDGE_ACCEPTANCE_TENANT_GID": "tenant-1",
            "AI00_KNOWLEDGE_ACCEPTANCE_SPACE_GID": "migration-space",
            "AI00_KNOWLEDGE_ACCEPTANCE_ACTOR_GID": "operator-1",
            "AI00_DEPLOYMENT_ENV": "staging",
            "AI00_KNOWLEDGE_ACCEPTANCE_WRITE_TOKEN": "I_UNDERSTAND_SOURCE_IS_RETAINED",
        }
        for name in (
            "OIS_IDENTIFY", "OIS_ENV", "OIS_OIS3_URL", "OIS_REGION", "OIS_LICLOUD_APPID",
            "OIS_IDAAS_URL", "OIS_IDAAS_CLIENT_ID", "OIS_IDAAS_CLIENT_SECRET",
            "OIS_IDAAS_SERVICE_ID",
        ):
            env[name] = "configured"
        return env

    def test_complete_staging_configuration_passes_without_exposing_values(self):
        checks = evaluate(self._complete_env(), module_probe=lambda _name: True)
        self.assertTrue(all(item.status == "pass" for item in checks))
        rendered = "\n".join(item.detail for item in checks)
        self.assertNotIn("secret", rendered)

    def test_production_environment_is_refused(self):
        env = self._complete_env()
        env["AI00_DEPLOYMENT_ENV"] = "prod"
        checks = {item.name: item for item in evaluate(env, module_probe=lambda _name: True)}
        self.assertEqual(checks["NON_PRODUCTION_ENV"].status, "fail")

    def test_write_acknowledgement_must_match_exactly(self):
        env = self._complete_env()
        env["AI00_KNOWLEDGE_ACCEPTANCE_WRITE_TOKEN"] = "yes"
        checks = {item.name: item for item in evaluate(env, module_probe=lambda _name: True)}
        self.assertEqual(checks["WRITE_ACKNOWLEDGEMENT"].status, "fail")

    def test_missing_dependencies_and_ois_fail_closed(self):
        env = self._complete_env()
        del env["OIS_IDAAS_CLIENT_SECRET"]
        checks = evaluate(env, module_probe=lambda _name: False)
        self.assertTrue(any(item.name == "OIS_CONFIG" and item.status == "fail" for item in checks))
        self.assertTrue(any(item.name.startswith("module:") and item.status == "fail" for item in checks))


if __name__ == "__main__":
    unittest.main()
