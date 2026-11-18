"""One rule: admin-only endpoints live under /api/v1/admin, guarded once on the parent router."""

from __future__ import annotations

from fastapi.routing import iter_route_contexts

from main import app
from middleware.auth import require_admin

ADMIN_PREFIX = "/api/v1/admin/"


def _dependency_calls(dependant) -> set:
    calls = {dependant.call}
    for sub in dependant.dependencies:
        calls |= _dependency_calls(sub)
    return calls


def _api_routes() -> list:
    # FastAPI nests include_router() lazily; iter_route_contexts() flattens it and
    # gives each endpoint's effective path (with every parent prefix).
    routes = [route for route in iter_route_contexts(app.routes) if getattr(route, "dependant", None) is not None]
    assert len(routes) > 40, "route discovery found almost nothing: the guard tests would pass vacuously"
    return routes


def test_every_admin_path_requires_admin():
    admin_paths = [route.path for route in _api_routes() if route.path.startswith(ADMIN_PREFIX)]
    assert len(admin_paths) >= 8, f"expected the admin endpoints, found {admin_paths}"
    unguarded = [
        f"{sorted(route.methods)} {route.path}"
        for route in _api_routes()
        if route.path.startswith(ADMIN_PREFIX) and require_admin not in _dependency_calls(route.dependant)
    ]
    assert not unguarded, f"/admin routes without require_admin: {unguarded}"


def test_no_admin_guard_outside_the_admin_prefix():
    misplaced = [
        f"{sorted(route.methods)} {route.path}"
        for route in _api_routes()
        if not route.path.startswith(ADMIN_PREFIX) and require_admin in _dependency_calls(route.dependant)
    ]
    assert not misplaced, f"admin-only routes must move under {ADMIN_PREFIX}: {misplaced}"


def test_admin_endpoints_moved_here_and_old_paths_are_gone():
    paths = {route.path for route in _api_routes()}
    assert "/api/v1/admin/sso/clients" in paths
    assert "/api/v1/admin/storage/files" in paths
    assert "/api/v1/admin/users/{user_email}/allow-no-pwd" in paths
    assert "/api/v1/sso/clients" not in paths
    assert "/api/v1/storage/admin/files" not in paths
