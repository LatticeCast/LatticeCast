"""task-26: exercise the repaired announcement controller/store/banner flow.

Usage:
    docker compose --profile test exec e2e pytest test_announcement_banner.py -v --snapshot
"""

import json

from e2e_base import BASE


ANNOUNCEMENTS_URL = "**/api/v1/announcements/query"
SERVER_ANNOUNCEMENTS_LQL = 'table("announcement") | filter(Type = "server")'
ANNOUNCEMENT_TITLE = "Scheduled maintenance"
ANNOUNCEMENT_DESCRIPTION = (
    "LatticeCast will be read-only on Sunday at 02:00 UTC.\n"
    "Please save your work beforehand."
)


def test_server_announcement_reaches_derived_banner(authed_page, snapshot) -> None:
    """The controller response updates the store and renders only the server banner."""
    page = authed_page

    def fulfill_announcements(route) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "rows": [
                        {"Type": "app", "Title": "Do not show this banner"},
                        {
                            "Type": "server",
                            "Title": ANNOUNCEMENT_TITLE,
                            "Description": ANNOUNCEMENT_DESCRIPTION,
                        },
                    ]
                }
            ),
        )

    page.route(ANNOUNCEMENTS_URL, fulfill_announcements)
    try:
        with page.expect_response(
            lambda response: response.url.endswith("/api/v1/announcements/query")
            and response.request.method == "POST"
        ) as response_info:
            page.goto(f"{BASE}/", wait_until="domcontentloaded")

        response = response_info.value
        assert response.status == 200
        assert response.request.post_data_json == {"lql": SERVER_ANNOUNCEMENTS_LQL}

        banner = page.get_by_test_id("announcement-banner")
        banner.wait_for(state="visible")
        assert banner.get_by_text(ANNOUNCEMENT_TITLE, exact=True).is_visible()
        assert banner.get_by_text(ANNOUNCEMENT_DESCRIPTION, exact=True).is_visible()
        assert not page.get_by_text("Do not show this banner", exact=True).is_visible()

        if snapshot:
            page.screenshot(path="/output/task_26_announcement_banner.png", full_page=True)
    finally:
        page.unroute(ANNOUNCEMENTS_URL, fulfill_announcements)
