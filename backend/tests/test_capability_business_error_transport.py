import unittest

from backend.capabilities.models_next import CapabilityBusinessError
from backend.routers.capabilities import _business_error_http_exception


class CapabilityBusinessErrorTransportTests(unittest.TestCase):
    def test_router_owns_http_status_and_preserves_stable_error_contract(self):
        error = CapabilityBusinessError(
            "version_not_published",
            "BOP version is not published",
            details={"version_gid": "v1"},
        )

        http_error = _business_error_http_exception(error)

        self.assertEqual(http_error.status_code, 409)
        self.assertEqual(
            http_error.detail,
            {
                "code": "version_not_published",
                "message": "BOP version is not published",
                "retryable": False,
                "details": {"version_gid": "v1"},
            },
        )

    def test_unknown_business_error_uses_unprocessable_status(self):
        http_error = _business_error_http_exception(
            CapabilityBusinessError("domain_constraint_failed", "Constraint failed")
        )

        self.assertEqual(http_error.status_code, 422)


if __name__ == "__main__":
    unittest.main()
