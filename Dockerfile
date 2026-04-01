FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . /app
RUN pip install --no-cache-dir -e .

# Image metadata keeps the default port; runtime can override it via APP_SERVER_PORT.
EXPOSE 8000

CMD ["sh", "-c", "uvicorn server.api:app --host 0.0.0.0 --port ${APP_SERVER_PORT:-8000}"]
