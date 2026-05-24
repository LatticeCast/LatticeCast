FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && apt-get install -y ca-certificates && update-ca-certificates

WORKDIR /scripts

ENV UV_HTTP_TIMEOUT=180 
ENV UV_CONCURRENT_DOWNLOADS=4

RUN echo "precedence ::ffff:0:0/96 100" >> /etc/gai.conf
COPY pyproject.toml uv.lock .
RUN uv sync --no-dev --verbose

CMD ["tail", "-f", "/dev/null"]
