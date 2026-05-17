FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /scripts

# Test runner deps only — playwright client lib + requests. No browsers,
# no direct DB. test-e2e remote-drives Chromium in the `browser` service
# via BROWSER_WS, and hits the BE through BASE_URL.
COPY pyproject.toml ./
ENV UV_HTTP_TIMEOUT=180
RUN uv pip install --system --no-cache -r pyproject.toml

CMD ["pytest", "--tb=short", "-q"]
