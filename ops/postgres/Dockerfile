ARG GO_IMAGE=golang@sha256:e8c859f5632dcfde7b32d2012b4351728f6437930887c2f6a91ea242459e5514
ARG POSTGRES_IMAGE=postgres:18@sha256:4ef4dbc939d61acea57712655ddb4b4ab27419c913f94cca0cd57cb3ea3c2280

FROM ${GO_IMAGE} AS gosu-builder

ARG GOSU_COMMIT=6456aaa0f3c854d199d0f037f068eb97515b7513

RUN set -eux; \
    git clone https://github.com/tianon/gosu.git /src/gosu; \
    cd /src/gosu; \
    git checkout "${GOSU_COMMIT}"; \
    test "$(git rev-parse HEAD)" = "${GOSU_COMMIT}"; \
    CGO_ENABLED=0 go build \
      -trimpath \
      -buildvcs=false \
      -ldflags='-s -w' \
      -o /out/gosu \
      .

FROM ${POSTGRES_IMAGE}

ARG OPENSSL_VERSION=3.5.7-1~deb13u2

COPY --from=gosu-builder /out/gosu /usr/local/bin/gosu

RUN set -eux; \
    chmod 0755 /usr/local/bin/gosu; \
    apt-get update; \
    apt-get install -y --no-install-recommends --only-upgrade \
      "openssl=${OPENSSL_VERSION}" \
      "libssl3t64=${OPENSSL_VERSION}" \
      "openssl-provider-legacy=${OPENSSL_VERSION}"; \
    rm -rf /var/lib/apt/lists/*; \
    gosu --version; \
    gosu nobody true
