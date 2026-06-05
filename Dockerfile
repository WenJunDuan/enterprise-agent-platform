# Enterprise Agent Platform — runtime image.
#
# Build on a networked box (can reach pypi via proxy), then `docker save` the
# image for offline transfer to an air-gapped target. The image is self-contained:
# claude-agent-sdk ships its platform `claude` CLI inside the wheel, so no Node is
# required at runtime. Frontend is the prebuilt ui/dist (served same-origin).
#
# The server resolves PROJECT_ROOT from the location of server/platform/paths.py,
# so the app must run in-place from /app (deps installed, package NOT installed).
FROM python:3.12-slim-bookworm

ARG APP_UID=1000
ARG APP_GID=1000

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/home/app

WORKDIR /app

# Dependency layer (kept separate for build-cache reuse). Mirrors pyproject.toml.
RUN pip install \
      "claude-agent-sdk>=0.2.88" \
      "fastapi>=0.115.0" \
      "jsonschema>=4.23.0" \
      "python-dotenv>=1.0.1" \
      "python-multipart>=0.0.30" \
      "typer>=0.12.0" \
      "uvicorn>=0.30.0"

RUN groupadd --gid "${APP_GID}" app \
    && useradd --uid "${APP_UID}" --gid app --create-home --home-dir /home/app app

# Application surface. .claude carries contracts/agents/hooks/skills/settings the
# SDK reads via setting_sources=["project"]; ui/dist is the prebuilt frontend;
# knowledge holds the audit rules (mounted volume overrides this baked default).
COPY --chown=app:app server ./server
COPY --chown=app:app .claude ./.claude
COPY --chown=app:app ui/dist ./ui/dist
COPY --chown=app:app knowledge ./knowledge
COPY --chown=app:app pyproject.toml README.md ./

RUN mkdir -p /app/data /app/logs \
    && chown -R app:app /app /home/app

USER app

EXPOSE 9999

CMD ["python", "-m", "uvicorn", "server.api:app", \
     "--host", "0.0.0.0", "--port", "9999", "--no-server-header"]
