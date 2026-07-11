# OpenMontage — Backlot board + full pipeline toolchain.
#
# Serves the Backlot dashboard (backlot/server.py) on 0.0.0.0:2383 so it can
# sit behind a Cloudflare Tunnel. Node + ffmpeg are included so pipelines can
# also be *run* inside this container later (e.g. `docker exec` + an agent
# CLI) — the board itself only needs Python.
FROM python:3.11-slim

# --- system deps: ffmpeg for media, Node 22 for Remotion/HyperFrames ---
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg curl gnupg ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- python deps (cached separately from source for faster rebuilds) ---
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# --- app source ---
COPY . .

# projects/ and music_library/ are meant to be bind-mounted at runtime so
# board state and royalty-free tracks survive rebuilds/redeploys.
RUN mkdir -p projects music_library

ENV PYTHONUNBUFFERED=1 \
    BACKLOT_PORT=2383

EXPOSE 2383

# backlot/__main__.py's `serve` command hardcodes host=127.0.0.1, which is
# unreachable from outside the container. Invoke uvicorn directly instead so
# we can bind 0.0.0.0 without patching the CLI.
CMD ["python", "-m", "uvicorn", "backlot.server:app", "--host", "0.0.0.0", "--port", "2383"]
