# First real container for the automation/ pipeline (issue #34, parent #32).
# Blinkit requires real Chrome (channel="chrome"), not bundled Chromium, to
# get past Cloudflare's bot detection — see automation/blinkit_scraper.py.
#
# Real Chrome has no Linux ARM64 build. Cloud Run defaults to linux/amd64,
# so this is a non-issue there — but on Apple Silicon, build explicitly with:
#   docker build --platform linux/amd64 -t tcb-automation .
FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chrome

COPY . .

# No default CMD — invoke a specific script at `docker run` time, e.g.:
#   docker run --env-file .env.dev -v "$(pwd)/data:/app/data" tcb-automation \
#     python automation/blinkit_scraper.py --dry-run
ENTRYPOINT ["python"]
