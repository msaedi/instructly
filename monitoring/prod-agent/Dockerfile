FROM prom/prometheus:v2.55.0

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
