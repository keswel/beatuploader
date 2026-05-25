# syntax=docker/dockerfile:1.7
#
# Production image for the Beatuploader backend.
#
# Single-stage on top of Microsoft's Playwright Python image, which already
# bundles Chromium + system deps (libnss3, libxkbcommon, etc.) — saves us from
# debugging headless-chrome on a vanilla python:slim base. The image is ~1.3GB;
# unavoidable when Playwright is in the dep tree.
#
# Run on a single worker until you swap the in-memory rate limiter + asyncio
# background jobs for Redis + a real queue. See CLAUDE.md "Pitfalls".

FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# pyproject.toml declares `packages = ["app"]`, so the editable install needs
# the `app/` directory to exist at install time. Copy source first, then install.
# This loses the layer-cache trick for code-only changes, but Playwright's base
# image dominates total build time anyway (~30s pull vs ~5s pip install).
COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
RUN pip install --no-cache-dir -e .

# Storage volume mount point. Bind /app/storage to a persistent volume on the
# host (Render disk, Fly volume, K8s PVC). Otherwise uploads and the BeatStars
# session cookies vanish on every redeploy.
RUN mkdir -p /app/storage
VOLUME ["/app/storage"]

EXPOSE 8000

# --proxy-headers: trust X-Forwarded-{For,Proto} so the rate limiter sees the
#   real client IP and HSTS/HTTPS detection works when behind a reverse proxy.
# --forwarded-allow-ips: which upstream IPs we trust the headers from. "*" is
#   fine inside a managed PaaS where the only inbound is the platform's proxy;
#   tighten if you run on bare metal.
# Single worker — see header comment.
#
# PORT env var: Render/Fly/Railway inject a port at container start. Default
# to 8000 for `docker run` without -e PORT. `exec` form replaces the shell so
# uvicorn becomes PID 1 and receives SIGTERM directly — without `exec`, /bin/sh
# would intercept the signal and uvicorn never gets a clean shutdown.
ENV PORT=8000
CMD exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port $PORT \
    --workers 1 \
    --proxy-headers \
    --forwarded-allow-ips '*'
