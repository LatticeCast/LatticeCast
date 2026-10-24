FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# uv verifies HTTPS with its own bundled webpki-roots, not the system store. The
# base tag above has not been rebuilt since 2026-02 and carries uv 0.9.30, which
# still trusts the compromised emSign ECC Root CA - G3 (GHSA-hq85-5cpj-mr62), so
# every `uv pip install` in this build is MITM-able. The uv image publishes no
# 0.13.x python variant, hence the binary swap instead of a different base. It has
# to replace /usr/local/bin/uv: the base image's own copy lives there and wins on
# PATH, so /bin/uv would be shadowed.
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /usr/local/bin/

ARG DEPLOY_COMMIT=unknown
ENV DEPLOY_COMMIT=${DEPLOY_COMMIT}

# Drop the emSign ECC Root CA - G3 from the system store too: apt, git, curl and
# openssl in this image otherwise keep trusting the root Mozilla distrusted. The
# other emSign roots stay; only G3 was compromised.
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates supervisor git && \
    rm -f /usr/share/ca-certificates/mozilla/emSign_ECC_Root_CA_-_G3.crt && \
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
