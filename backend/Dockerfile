FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates supervisor git && \
    update-ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV UV_HTTP_TIMEOUT=180
ENV UV_CONCURRENT_DOWNLOADS=4
RUN echo "precedence ::ffff:0:0/96 100" >> /etc/gai.conf

COPY pyproject.toml uv.lock .
RUN uv pip install --system  --verbose -r pyproject.toml

COPY ./src/ ./src/
RUN mkdir -p /app/src/workspace

COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
