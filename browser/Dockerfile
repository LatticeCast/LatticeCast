# Browser host — Chromium binaries come pre-installed at /ms-playwright
# in the playwright/python image, but the `playwright` pip package is
# NOT pre-installed there. Layer it on so `python -m playwright
# run-server` works.
FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

RUN pip install --no-cache-dir --break-system-packages playwright==1.50.0

CMD ["python3", "-m", "playwright", "run-server", \
     "--host", "0.0.0.0", "--port", "4444"]
