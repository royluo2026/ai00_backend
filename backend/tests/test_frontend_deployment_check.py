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
        "/web/admin/capability_governance/index.html": (
            '<link rel="stylesheet" href="/assets/governance.css">'
            '<script src="governance_model.js"></script>'
            '<script src="governance_api.js"></script>'
            '<script src="governance_controller.js"></script>'
        ),
        "/web/admin/capability_governance/governance_model.js": "CapabilityGovernanceModel",
        "/web/admin/capability_governance/governance_api.js": "CapabilityGovernanceApi",
        "/web/admin/capability_governance/governance_controller.js": "CapabilityGovernanceController",
        "/assets/governance.css": ".governance-shell",
    }

    def fake_get(_base_url, path):
        content_type = "application/json" if path in {"/health", "/ready"} else (
            "text/html" if path in {"/", "/web/settings/index.html", "/web/admin/capability_governance/index.html"}
            else "text/css" if path.endswith(".css") else "text/javascript"
        )
        return 200, content_type, bodies[path]

    monkeypatch.setattr(deployment, "_get", fake_get)
    report = deployment.check("http://example.test")
    assert report["status"] == "passed"
    assert {row["path"] for row in report["checks"]} == set(bodies)


def test_check_accepts_current_settings_owned_plugin_center(monkeypatch):
    bodies = {
        "/health": '"status"',
        "/ready": '"status"',
        "/": "AI00",
        "/web/settings/index.html": '<div id="panel-plugin-market"></div><script src="settings.js?v=9"></script>',
        "/web/settings/settings.js": "panel-plugin-market",
        "/web/admin/capability_governance/index.html": (
            '<link rel="stylesheet" href="/assets/governance.css">'
            '<script src="governance_model.js"></script>'
            '<script src="governance_api.js"></script>'
            '<script src="governance_controller.js"></script>'
        ),
        "/web/admin/capability_governance/governance_model.js": "CapabilityGovernanceModel",
        "/web/admin/capability_governance/governance_api.js": "CapabilityGovernanceApi",
        "/web/admin/capability_governance/governance_controller.js": "CapabilityGovernanceController",
        "/assets/governance.css": ".governance-shell",
    }

    def fake_get(_base_url, path):
        content_type = "application/json" if path in {"/health", "/ready"} else (
            "text/html" if path in {"/", "/web/settings/index.html", "/web/admin/capability_governance/index.html"}
            else "text/css" if path.endswith(".css") else "text/javascript"
        )
        return 200, content_type, bodies[path]

    monkeypatch.setattr(deployment, "_get", fake_get)
    report = deployment.check("http://example.test")
    assert report["status"] == "passed"
    assert "/web/settings/settings.js" in {row["path"] for row in report["checks"]}
