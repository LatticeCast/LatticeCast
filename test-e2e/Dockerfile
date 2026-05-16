FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /scripts

# Test runner deps only — psycopg2 for DB checks, requests for BE API,
# docker SDK to drive the separate .browser container for UI steps.
# Playwright/Chromium stay in the browser image; test-e2e does NOT run
# them itself.
COPY pyproject.toml ./
ENV UV_HTTP_TIMEOUT=180
RUN uv pip install --system --no-cache -r pyproject.toml

CMD ["tail", "-f", "/dev/null"]
