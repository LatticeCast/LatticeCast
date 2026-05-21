FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /scripts

ENV UV_HTTP_TIMEOUT=180 
ENV UV_CONCURRENT_DOWNLOADS=4
ENV UV_LINK_MODE=copy

# Test runner deps only — playwright client lib + requests. No browsers,
# no direct DB. e2e remote-drives Chromium in the `browser` service
# via BROWSER_WS, and hits the BE through BASE_URL.
COPY pyproject.toml uv.lock ./
RUN echo "precedence ::ffff:0:0/96 100" >> /etc/gai.conf
RUN uv sync --no-dev --frozen --verbose

CMD ["tail", "-f", "/dev/null"]
