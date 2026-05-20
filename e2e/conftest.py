"""Shared pytest fixtures for LatticeCast e2e tests.

Fixtures auto-discovered by pytest — test files declare them by parameter name.
"""

from __future__ import annotations

import time

import pytest
from playwright.sync_api import sync_playwright

from e2e_base import BASE, api, connect_browser, login, seed_login_info


def pytest_addoption(parser):
    parser.addoption("--snapshot", action="store_true", default=False, help="Enable screenshots")


@pytest.fixture()
def snapshot(request):
    return request.config.getoption("--snapshot")


@pytest.fixture(scope="session")
def browser():
    pw = sync_playwright().start()
    b = connect_browser(pw)
    yield b
    b.close()
    pw.stop()


@pytest.fixture()
def page(browser):
    p = browser.new_page(viewport={"width": 1400, "height": 900})
    yield p
    p.close()


@pytest.fixture(scope="session")
def admin_token():
    return login("lattice")


@pytest.fixture()
def authed_page(browser, admin_token):
    p = browser.new_page(viewport={"width": 1400, "height": 900})
    seed_login_info(p, admin_token, "lattice", role="admin")
    yield p
    p.close()


@pytest.fixture()
def workspace(admin_token):
    suffix = int(time.time() * 1000) % 10_000_000
    ws_name = f"test-ws-{suffix}"
    r = api("POST", "/api/v1/workspaces", admin_token, json={"workspace_name": ws_name})
    assert r.status_code == 201, f"create workspace: {r.status_code} {r.text[:200]}"
    ws_id = r.json()["workspace_id"]
    yield ws_id, ws_name
    api("DELETE", f"/api/v1/workspaces/{ws_id}", admin_token)


@pytest.fixture()
def pm_table(admin_token, workspace):
    ws_id, ws_name = workspace
    suffix = int(time.time() * 1000) % 10_000_000
    table_id = f"pm-{suffix}"
    r = api(
        "POST", "/api/v1/tables/template/pm", admin_token,
        json={"table_id": table_id, "workspace_name": ws_name},
    )
    assert r.status_code == 201, f"create PM table: {r.status_code} {r.text[:200]}"
    schema = r.json()
    yield table_id, ws_id, schema.get("columns", []), schema.get("views", [])
