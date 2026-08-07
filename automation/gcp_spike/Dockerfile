FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

WORKDIR /app
COPY check_session.py .

# Blinkit requires real Chrome (channel="chrome"), not just bundled Chromium.
# supabase: for the `db` mode's connectivity check (mirrors tcb/db.py's REST client).
RUN pip install --no-cache-dir playwright==1.48.0 supabase \
    && playwright install --with-deps chrome

ENTRYPOINT ["python", "check_session.py"]
