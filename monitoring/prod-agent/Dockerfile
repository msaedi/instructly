FROM prom/prometheus:v2.55.0

RUN apk add --no-cache gettext

COPY prometheus.yml.tmpl /etc/prometheus/prometheus.yml.tmpl

ENTRYPOINT ["/bin/sh","-lc", "\
  set -e; \
  envsubst '$${BACKEND_TARGET} $${CLUSTER_LABEL} $${PROM_REMOTE_WRITE_URL} $${PROM_REMOTE_WRITE_USERNAME} $${PROM_REMOTE_WRITE_PASSWORD} $${METRICS_BASIC_AUTH_USER} $${METRICS_BASIC_AUTH_PASS}' < /etc/prometheus/prometheus.yml.tmpl > /etc/prometheus/prometheus.yml; \
  exec /bin/prometheus \
    --config.file=/etc/prometheus/prometheus.yml \
    --storage.tsdb.retention.time=1h \
    --web.enable-lifecycle=false \
    --web.listen-address=:8080 \
    --log.format=logfmt \
"]
