FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

RUN apt-get update && apt-get install -y ca-certificates && update-ca-certificates

WORKDIR /scripts

ENV UV_HTTP_TIMEOUT=180 
ENV UV_CONCURRENT_DOWNLOADS=4
RUN echo "precedence ::ffff:0:0/96 100" >> /etc/gai.conf

COPY pyproject.toml .
RUN uv pip install --system  --verbose -r pyproject.toml

CMD ["tail", "-f", "/dev/null"]
