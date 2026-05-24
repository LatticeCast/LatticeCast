FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

RUN apt-get update && apt-get install -y ca-certificates && update-ca-certificates
RUN apt-get update && apt-get install -y --no-install-recommends cron supervisor git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV UV_HTTP_TIMEOUT=180 
ENV UV_CONCURRENT_DOWNLOADS=4
RUN echo "precedence ::ffff:0:0/96 100" >> /etc/gai.conf

COPY pyproject.toml .
RUN uv pip install --system  --verbose -r pyproject.toml

# Copy source
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
