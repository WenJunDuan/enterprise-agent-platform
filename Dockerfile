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
# pip 索引源。内网部署机实测：直连 pypi.org 被重置（`Recv failure: 连接被对方重置`），
# 经代理同样不通，清华镜像直连 200 —— 故默认走镜像，能直连 pypi 的环境用
# `--build-arg PIP_INDEX_URL=https://pypi.org/simple` 覆盖即可。
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_DEFAULT_TIMEOUT=120 \
    HOME=/home/app

WORKDIR /app

# Dependency layer (kept separate for build-cache reuse). Mirrors pyproject.toml.
RUN pip install \
      "anthropic>=0.117.0" \
      "claude-agent-sdk>=0.2.88" \
      "fastapi>=0.115.0" \
      "httpx>=0.28.1" \
      "jsonschema>=4.23.0" \
      "python-dotenv>=1.0.1" \
      "python-multipart>=0.0.30" \
      "typer>=0.12.0" \
      "uvicorn>=0.30.0" \
      "certifi>=2024.0"

# 可选 OCR 依赖层（文档识别 multi-ocr）。仅 --build-arg WITH_OCR=1 时装：
# - paddlepaddle + paddleocr[doc-parser]：保留完整 PaddleOCRVL pipeline 能力；
#   默认识别走 litellm OpenAI 兼容网关（OCR_VL_SERVER_URL），避免本地 layout
#   predictor 在部分 arm64 容器运行时崩溃；需完整 pipeline 时设 OCR_VL_USE_PADDLE_PIPELINE=1。
# - Office/Excel/PDF parsers：按后缀使用独立解析器，避免把旧格式交给 OOXML 解析器。
# - pymupdf：远端 VLM 仅收图片时，把扫描 PDF 按页渲染为 PNG。
# arm64 上 paddlepaddle wheel 可用性在构建时验证；失败则按官方索引指定 wheel 源。
ARG WITH_OCR
RUN if [ "$WITH_OCR" = "1" ]; then \
      pip install \
        paddlepaddle==3.2.2 \
        "paddleocr[doc-parser]==3.7.0" \
        paddlex==3.7.2 \
        openpyxl==3.1.5 \
        python-docx==1.2.0 \
        xlrd==2.0.2 \
        pyxlsb==1.0.10 \
        python-pptx==1.0.2 \
        Pillow==12.3.0 \
        pymupdf==1.27.2.3 \
        pypdf==6.14.2 \
        pdfplumber==0.11.10 ; \
    fi

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      gosu \
      libgl1 \
      libglib2.0-0 \
      libgomp1 \
    && if [ "$WITH_OCR" = "1" ]; then apt-get install -y --no-install-recommends \
      antiword \
      catdoc \
      fonts-liberation2 \
      fonts-noto-cjk \
      libreoffice-calc \
      libreoffice-impress \
      libreoffice-writer \
      procps \
      tesseract-ocr \
      tesseract-ocr-chi-sim \
      tesseract-ocr-eng; fi \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid "${APP_GID}" app \
    && useradd --uid "${APP_UID}" --gid app --create-home --home-dir /home/app app

# Application surface. .claude carries contracts/agents/hooks/skills/settings the
# SDK reads via setting_sources=["project"]; agent-front/dist is the prebuilt frontend;
# knowledge holds the audit rules (mounted volume overrides this baked default).
COPY --chown=app:app server ./server
COPY --chown=app:app shared ./shared
COPY --chown=app:app scripts/generate_document_formats.py ./scripts/generate_document_formats.py
COPY --chown=app:app scripts/smoke_document_formats.py ./scripts/smoke_document_formats.py
COPY --chown=app:app scripts/verify_office_macro_safety.py ./scripts/verify_office_macro_safety.py
COPY --chown=app:app scripts/document_format_fixtures ./scripts/document_format_fixtures
COPY --chown=app:app .claude ./.claude
COPY --chown=app:app agent-front/dist ./agent-front/dist
COPY --chown=app:app pyproject.toml README.md ./
COPY docker-entrypoint.sh ./docker-entrypoint.sh

RUN mkdir -p /app/data /app/knowledge /app/logs \
    && chown -R app:app /app /home/app \
    && chmod +x /app/docker-entrypoint.sh

USER root

EXPOSE 9999

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "server.api:app", \
     "--host", "0.0.0.0", "--port", "9999", "--no-server-header"]
