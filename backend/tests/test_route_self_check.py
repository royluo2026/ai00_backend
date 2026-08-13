from backend import main


def test_every_critical_route_is_registered():
    registered = {
        (method.upper(), path)
        for path, operations in main.app.openapi()["paths"].items()
        for method in operations
        if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}
    }

    assert set(main._CRITICAL_ROUTE_SPECS) <= registered
