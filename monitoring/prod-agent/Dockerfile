FROM prom/prometheus:v2.55.0

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends gettext-base ca-certificates; \
    rm -rf /var/lib/apt/lists/*

COPY prometheus.yml.tmpl /etc/prometheus/prometheus.yml.tmpl

ENTRYPOINT ["/bin/sh","-lc", "\
  envsubst < /etc/prometheus/prometheus.yml.tmpl > /etc/prometheus/prometheus.yml && \
  exec /bin/prometheus \
    --config.file=/etc/prometheus/prometheus.yml \
    --storage.tsdb.retention.time=1h \
    --web.enable-lifecycle=false \
    --web.listen-address=:8080 \
    --log.format=logfmt \
"]
