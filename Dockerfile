FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r pos && useradd -r -g pos -d /home/pos -m pos

WORKDIR /app

COPY pyproject.toml README.md ./
COPY pos_service ./pos_service
RUN pip install -U pip && pip install .

COPY alembic.ini ./
COPY alembic ./alembic

RUN mkdir -p /data && chown -R pos:pos /data /app

USER pos

EXPOSE 8080

CMD ["sh", "-c", "alembic upgrade head && uvicorn pos_service.main:app --host 0.0.0.0 --port 8080"]
