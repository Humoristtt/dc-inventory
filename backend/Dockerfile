FROM python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254

ARG APP_REVISION
ARG PCRE2_VERSION=10.42-1+deb12u1

RUN test -n "$APP_REVISION" \
    && test "$APP_REVISION" != "unknown"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        "libpcre2-8-0=${PCRE2_VERSION}" \
    && rm -rf /var/lib/apt/lists/*
LABEL org.opencontainers.image.revision="${APP_REVISION}"

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
COPY --chown=10001:10001 scripts /app/scripts
COPY --chown=10001:10001 app /app/app

USER 10001:10001

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
