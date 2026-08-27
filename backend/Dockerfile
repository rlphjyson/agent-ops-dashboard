FROM python:3.12-slim

WORKDIR /app

# Both agent engines ultimately need the native `claude` binary -- the SDK engine is a thin
# wrapper around it (confirmed by reading claude-agent-sdk's own subprocess_cli.py), and the CLI
# engine shells out to it directly. Needs Node.js to install, same as prreview-ai's review engine.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates git \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && apt-get purge -y curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app ./app

# [postgres] extra included: SQLite's file-based storage doesn't survive most hosting
# platforms' ephemeral/non-persistent container disks, so any real deployment needs Postgres.
RUN pip install --no-cache-dir ".[postgres]"

RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
