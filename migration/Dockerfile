FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# uv verifies HTTPS with its own bundled webpki-roots, not the system store. This
# base tag has not been rebuilt since 2026-02 and carries uv 0.9.30, which still
# trusts the compromised emSign ECC Root CA - G3 (GHSA-hq85-5cpj-mr62), so the
# install below is MITM-able. The uv image publishes no 0.13.x python variant,
# hence the binary swap instead of a different base; it must land in
# /usr/local/bin to shadow the base image's own uv on PATH.
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /usr/local/bin/

# Docker CLI (for spinning up temp PG in tests)
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl gnupg && \
    rm -f /usr/share/ca-certificates/mozilla/emSign_ECC_Root_CA_-_G3.crt && \
    update-ca-certificates && \
    install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable" \
      > /etc/apt/sources.list.d/docker.list && \
    apt-get update && apt-get install -y --no-install-recommends docker-ce-cli && \
    rm -rf /var/lib/apt/lists/*

RUN uv pip install --system psycopg2-binary sqlfluff

WORKDIR /jetbase
