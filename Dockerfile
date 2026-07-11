# OpenMontage — Backlot board + full pipeline toolchain.
#
# Serves the Backlot dashboard (backlot/server.py) on 0.0.0.0:2383 so it can
# sit behind a Cloudflare Tunnel. Same image also runs the MCP server
# (mcp_server/asgi.py, port 2384 via docker-compose.yml's `mcp` service) and
# is the image invoke_tool's isolated subprocess runs inside — so every free,
# local (no API key) generation tool lives here too: ffmpeg, Piper TTS,
# ManimCE (+LaTeX for MathTex), and Remotion (+ its own headless browser).
# CPU-only; comfyui_video/local_diffusion need a real GPU and are
# deliberately NOT installed here.
FROM python:3.11-slim

# --- system deps ---
# ffmpeg/curl/gnupg/ca-certificates/Node: base toolchain (unchanged).
# build-essential/pkg-config/python3-dev/libcairo2-dev/libpango1.0-dev:
#   pycairo/pangocairo, required to build/import manim at all.
# texlive*: LaTeX for Manim's MathTex (plain Text() scenes don't need it,
#   but "ready to use" means formulas work too). Not texlive-full (~5GB+) --
#   this subset covers amsmath/amssymb and friends without that.
# libnss3.../fonts-liberation: headless Chromium's runtime deps (Remotion's
#   own downloaded browser, not a system chromium package) -- this is the
#   standard Puppeteer/Playwright Debian dependency list.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg curl gnupg ca-certificates \
        build-essential pkg-config python3-dev libcairo2-dev libpango1.0-dev \
        texlive texlive-latex-extra texlive-fonts-extra texlive-latex-recommended \
        texlive-science texlive-extra-utils \
        libnss3 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
        libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 \
        libasound2 libpangocairo-1.0-0 libx11-6 libxcb1 libxext6 \
        fonts-liberation libappindicator3-1 xdg-utils libu2f-udev libvulkan1 \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- python deps (cached separately from source for faster rebuilds) ---
# requirements-free-tools.txt: piper-tts + manim, kept out of the core
# requirements.txt so a plain dev checkout isn't forced into this weight.
COPY requirements.txt requirements-free-tools.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-free-tools.txt

# --- Remotion: install deps from the manifest before the full COPY so a
# source-only change doesn't invalidate this layer (npm install + browser
# download are the slow, network-heavy parts). ---
COPY remotion-composer/package.json remotion-composer/package-lock.json* remotion-composer/
RUN cd remotion-composer && npm install \
    && npx remotion browser ensure

# --- Piper TTS: the installed CLI has no auto-download flag (see
# tools/audio/piper_tts.py) -- it only resolves a bare model name against
# files already in --data-dir. Pre-fetch the tool's own default voice so
# it's usable immediately; PIPER_VOICES_DIR (lib/paths.py) defaults to
# <repo_root>/.piper-voices, which resolves to /app/.piper-voices here. ---
RUN mkdir -p /app/.piper-voices && cd /app/.piper-voices \
    && curl -fsSL -O https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx \
    && curl -fsSL -O https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json

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
