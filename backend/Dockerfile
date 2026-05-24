FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates supervisor && \
    update-ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH"

ENV UV_HTTP_TIMEOUT=180
ENV UV_CONCURRENT_DOWNLOADS=4
RUN echo "precedence ::ffff:0:0/96 100" >> /etc/gai.conf

COPY pyproject.toml uv.lock .
RUN uv sync --no-dev --verbose

COPY ./src/ ./src/
RUN mkdir -p /app/src/workspace

COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
