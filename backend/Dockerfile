FROM python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254

ARG APP_REVISION
ARG PCRE2_VERSION=10.42-1+deb12u1
ARG PCRE2_AMD64_SHA256=81c5502941118a24d47af69a17b8b0b9548d75cc6d72b3eb3fe01047b46fa10e
ARG PCRE2_ARM64_SHA256=d178d33697eef877c2c27733141b7f8520fee66a329ae5809e8c8eae3709efa3

RUN test -n "$APP_REVISION" \
    && test "$APP_REVISION" != "unknown"

# Debian security package indexes can rotate while the signed pool artifact
# remains available. Install the exact fixed artifact by version + SHA-256
# instead of depending on a moving apt index.
RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in \
        amd64) checksum="${PCRE2_AMD64_SHA256}" ;; \
        arm64) checksum="${PCRE2_ARM64_SHA256}" ;; \
        *) echo "unsupported architecture: $arch" >&2; exit 1 ;; \
    esac; \
    url="https://security.debian.org/debian-security/pool/updates/main/p/pcre2/libpcre2-8-0_${PCRE2_VERSION}_${arch}.deb"; \
    python -c "import urllib.request; urllib.request.urlretrieve('${url}', '/tmp/libpcre2.deb')"; \
    echo "${checksum}  /tmp/libpcre2.deb" | sha256sum --check -; \
    dpkg -i /tmp/libpcre2.deb; \
    rm -f /tmp/libpcre2.deb
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
