from backend import main


def test_every_critical_route_is_registered():
    registered = {
        (method.upper(), path)
        for path, operations in main.app.openapi()["paths"].items()
        for method in operations
        if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}
    }

    assert set(main._CRITICAL_ROUTE_SPECS) <= registered


def test_workbench_home_compatibility_routes_are_registered():
    paths = main.app.openapi()["paths"]

    assert "get" in paths["/api/workbench/home"]
    assert "get" in paths["/api/workbench/panel1"]
