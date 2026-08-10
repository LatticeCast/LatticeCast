"""Live announcement banner e2e.

Usage:
    docker compose --profile test exec e2e pytest test_announcement_banner.py -v --snapshot
"""

from __future__ import annotations

import time

from e2e_base import BASE, api


def test_server_announcement_reaches_banner_live(authed_page, admin_token, snapshot) -> None:
    """Create real announcement rows, then verify FE renders the list rather than only one row."""
    seed = int(time.time() * 1000)
    title_a = f"e2e-announcement-{seed}-a"
    title_b = f"e2e-announcement-{seed}-b"
    description_a = f"{title_a} description"
    description_b = f"{title_b} description"

    for title, description in ((title_a, description_a), (title_b, description_b)):
        create_response = api(
            "POST",
            "/api/v1/admin/announcements",
            admin_token,
            json={
                "type": "server",
                "title": title,
                "description": description,
            },
        )
        assert create_response.status_code == 201, create_response.text

    page = authed_page
    page.goto(f"{BASE}/", wait_until="networkidle")

    banner = page.get_by_test_id("announcement-banner")
    banner.wait_for(state="visible")
    banner.click()

    page.get_by_text(title_a, exact=True).wait_for(state="visible", timeout=10000)
    assert page.get_by_text(title_a, exact=True).is_visible()
    assert page.get_by_text(description_a, exact=True).is_visible()
    assert page.get_by_text(title_b, exact=True).is_visible()
    assert page.get_by_text(description_b, exact=True).is_visible()

    if snapshot:
        page.screenshot(path="/output/task_26_announcement_banner.png", full_page=True)
