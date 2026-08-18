from backend.scripts import check_frontend_deployment as deployment


def test_check_covers_productized_plugin_center_assets(monkeypatch):
    bodies = {
        "/health": '"status"',
        "/ready": '"status"',
        "/": "AI00",
        "/web/settings/index.html": "plugin_center_model.js plugin_center_api.js plugin_center.js",
        "/web/settings/plugin_center_model.js": "AI00PluginCenterModel",
        "/web/settings/plugin_center_api.js": "createPluginCenterApi",
        "/web/settings/plugin_center.js": "Server-backed Capability V2 plugin center controller",
        "/web/admin/capability_governance/index.html": "governance_controller.js",
    }

    def fake_get(_base_url, path):
        content_type = "application/json" if path in {"/health", "/ready"} else (
                "text/html" if path in {"/", "/web/settings/index.html", "/web/admin/capability_governance/index.html"} else "text/javascript"
        )
        return 200, content_type, bodies[path]

    monkeypatch.setattr(deployment, "_get", fake_get)
    report = deployment.check("http://example.test")
    assert report["status"] == "passed"
    assert {row["path"] for row in report["checks"]} == set(bodies)
