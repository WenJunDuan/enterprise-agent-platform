# Enterprise Agent Platform — runtime image.
#
# Build on a networked box (can reach pypi via proxy), then `docker save` the
# image for offline transfer to an air-gapped target. The image is self-contained:
# claude-agent-sdk ships its platform `claude` CLI inside the wheel, so no Node is
# required at runtime. Frontend is the prebuilt agent-front/dist (served same-origin).
#
# The server resolves PROJECT_ROOT from the location of server/platform/paths.py,
# so the app must run in-place from /app (deps installed, package NOT installed).
# 基础镜像可参数化：内网 docker.io 被挡时走镜像源
# （如 --build-arg BASE_IMAGE=docker.m.daocloud.io/library/python:3.12-slim-bookworm）。
ARG BASE_IMAGE=python:3.12-slim-bookworm
FROM ${BASE_IMAGE}

ARG APP_UID=1000
ARG APP_GID=1000
# 文档识别(multi-ocr)依赖开关。默认 0=不装，保持 audit-only 镜像精简；
# 构建带 OCR 的镜像用 --build-arg WITH_OCR=1（镜像 +~GB）。
ARG WITH_OCR=0

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

# 可选 OCR 依赖层（文档识别 multi-ocr）。仅 --build-arg WITH_OCR=1 时装：
# - paddlepaddle + paddleocr[doc-parser]：保留完整 PaddleOCRVL pipeline 能力；
#   默认识别走 litellm OpenAI 兼容网关（OCR_VL_SERVER_URL），避免本地 layout
#   predictor 在部分 arm64 容器运行时崩溃；需完整 pipeline 时设 OCR_VL_USE_PADDLE_PIPELINE=1。
# - openpyxl/python-docx/pypdf：原生直读 Excel/Word/文本层 PDF。
# - pymupdf：远端 VLM 仅收图片时，把扫描 PDF 按页渲染为 PNG。
# arm64 上 paddlepaddle wheel 可用性在构建时验证；失败则按官方索引指定 wheel 源。
ARG WITH_OCR
RUN if [ "$WITH_OCR" = "1" ]; then \
      pip install \
        paddlepaddle \
        "paddleocr[doc-parser]>=3.4.0" \
        openpyxl python-docx pymupdf pypdf ; \
    fi

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      gosu \
      libgl1 \
      libglib2.0-0 \
      libgomp1 \
    && if [ "$WITH_OCR" = "1" ]; then apt-get install -y --no-install-recommends catdoc; fi \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid "${APP_GID}" app \
    && useradd --uid "${APP_UID}" --gid app --create-home --home-dir /home/app app

# Application surface. .claude carries contracts/agents/hooks/skills/settings the
# SDK reads via setting_sources=["project"]; agent-front/dist is the prebuilt frontend;
# knowledge holds the audit rules (mounted volume overrides this baked default).
COPY --chown=app:app server ./server
COPY --chown=app:app .claude ./.claude
COPY --chown=app:app agent-front/dist ./agent-front/dist
COPY --chown=app:app knowledge ./knowledge
COPY --chown=app:app pyproject.toml README.md ./
COPY docker-entrypoint.sh ./docker-entrypoint.sh

RUN mkdir -p /app/data /app/logs \
    && chown -R app:app /app /home/app \
    && chmod +x /app/docker-entrypoint.sh

USER root

EXPOSE 9999

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "server.api:app", \
     "--host", "0.0.0.0", "--port", "9999", "--no-server-header"]
