"""Deployment status is public and reports each service's own version."""

import json

import requests
from playwright.sync_api import expect

from e2e_base import BASE


def test_deployment_status(page, snapshot):
    frontend = requests.get(f"{BASE}/status", timeout=10)
    assert frontend.status_code == 200
    assert frontend.headers["content-type"].startswith("application/json")
    frontend_status = frontend.json()
    assert frontend_status["status"] == "ok"
    assert frontend_status["version"] == "0.69.0"
    assert isinstance(frontend_status["commit"], str)

    backend = requests.get(f"{BASE}/api/v1/status", timeout=10)
    assert backend.status_code == 200
    backend_status = backend.json()
    assert backend_status["status"] == "ok"
    assert backend_status["db"] == "ok"
    assert backend_status["version"] == "0.69.0"
    assert isinstance(backend_status["commit"], str)
    spec = requests.get(f"{BASE}/api/v1/openapi.json", timeout=10)
    assert spec.status_code == 200
    assert backend_status["version"] == spec.json()["info"]["version"]

    response = page.goto(f"{BASE}/status")
    assert response.status == 200
    expect(page.locator("body")).to_contain_text(frontend_status["version"])
    assert json.loads(page.locator("body").inner_text()) == frontend_status
    if snapshot:
        page.screenshot(path="/output/deployment_status.png", full_page=True)
