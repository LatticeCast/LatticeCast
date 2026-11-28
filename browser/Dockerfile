# Browser host — Chromium binaries come pre-installed at /ms-playwright
# in the playwright/python image, but the `playwright` pip package is
# NOT pre-installed there. Layer it on so `python -m playwright
# run-server` works.
FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

RUN pip install --no-cache-dir --break-system-packages playwright==1.50.0

# Forwards localhost:${NGX_PORT} to the proxy container (see docker-compose.yml).
RUN apt-get update && apt-get install -y --no-install-recommends socat && \
    rm -rf /var/lib/apt/lists/*

CMD ["python3", "-m", "playwright", "run-server", \
     "--host", "0.0.0.0", "--port", "4444"]
