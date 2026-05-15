FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

WORKDIR /app

# Install playwright + DB connector + HTTP client
RUN pip install --no-cache-dir playwright==1.50.0 psycopg2-binary requests

# Copy scripts
COPY *.py ./

# Create output directory
RUN mkdir -p /output

CMD ["tail", "-f", "/dev/null"]
