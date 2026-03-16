FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends cron supervisor && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies
COPY pyproject.toml ./
RUN uv sync --no-dev

ENV PATH="/app/.venv/bin:$PATH"

# Copy source and migrations
COPY ./src/ ./src/
RUN mkdir -p /app/src/workspace /app/src/log

# Cron
COPY daily.sh daily.sh
RUN chmod +x /app/daily.sh
COPY crontab /mycron
RUN chmod 644 /mycron && crontab /mycron

# Supervisor
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
