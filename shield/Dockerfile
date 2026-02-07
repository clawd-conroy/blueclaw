FROM python:3.12.8-slim

# System deps for Cisco scanner + clawhub
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# ClawHub CLI (pin version)
RUN npm install -g clawhub@1

# Cisco skill-scanner (pin version)
RUN pip install --no-cache-dir cisco-ai-skill-scanner==0.1.0

# Shield aggregator
WORKDIR /app
COPY shield/scripts/shield-aggregator.py .

# AT Proto creds passed as env vars at runtime:
#   BLUESKY_USERNAME, BLUESKY_PASSWORD, BLUECLAW_APPVIEW

ENTRYPOINT ["python3", "shield-aggregator.py"]
CMD ["all", "--top", "100", "--dry-run"]
