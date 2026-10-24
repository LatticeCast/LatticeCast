FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# uv verifies HTTPS with its own bundled webpki-roots: this base tag carries uv
# 0.9.30, which still trusts the compromised emSign ECC Root CA - G3
# (GHSA-hq85-5cpj-mr62). Take the fixed binary from the plain uv image, into
# /usr/local/bin so it shadows the base image's own uv on PATH.
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /usr/local/bin/

RUN apt-get update && apt-get install -y ca-certificates && \
    rm -f /usr/share/ca-certificates/mozilla/emSign_ECC_Root_CA_-_G3.crt && \
    update-ca-certificates

WORKDIR /scripts

ENV UV_HTTP_TIMEOUT=180
ENV UV_CONCURRENT_DOWNLOADS=4

RUN echo "precedence ::ffff:0:0/96 100" >> /etc/gai.conf
COPY pyproject.toml uv.lock .
RUN uv pip install --system  --verbose -r pyproject.toml

CMD ["tail", "-f", "/dev/null"]
