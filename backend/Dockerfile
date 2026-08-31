FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --gid 10001 app \
    && useradd \
        --uid 10001 \
        --gid 10001 \
        --no-create-home \
        --shell /usr/sbin/nologin \
        app

COPY requirements.lock /app/requirements.lock

RUN python -m pip install \
    --require-hashes \
    --requirement /app/requirements.lock

COPY --chown=10001:10001 alembic.ini /app/alembic.ini
COPY --chown=10001:10001 migrations /app/migrations
COPY --chown=10001:10001 app /app/app

USER 10001:10001

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
