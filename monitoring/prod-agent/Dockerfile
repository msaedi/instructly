FROM prom/prometheus:v2.55.0

COPY prometheus.yml.tmpl /etc/prometheus/prometheus.yml.tmpl

# Minimal, POSIX-sh safe entrypoint (no secret logging).
ENTRYPOINT ["/bin/sh","-c","\
  set -eu; \
  # Required envs (no secrets in logs) \
  req='BACKEND_SCHEME BACKEND_TARGET CLUSTER_LABEL PROM_REMOTE_WRITE_URL PROM_REMOTE_WRITE_USERNAME PROM_REMOTE_WRITE_PASSWORD METRICS_BASIC_AUTH_USER METRICS_BASIC_AUTH_PASS'; \
  for k in $req; do eval v=\\$$k; if [ -z \"${v:-}\" ]; then echo \"prom-agent: missing env $k\" >&2; exit 1; fi; done; \
  # Render effective config \
  awk -v A=\"$BACKEND_SCHEME\" \
      -v H=\"$BACKEND_TARGET\" \
      -v B=\"$CLUSTER_LABEL\" \
      -v C=\"$PROM_REMOTE_WRITE_URL\" \
      -v D=\"$PROM_REMOTE_WRITE_USERNAME\" \
      -v E=\"$PROM_REMOTE_WRITE_PASSWORD\" \
      -v F=\"$METRICS_BASIC_AUTH_USER\" \
      -v G=\"$METRICS_BASIC_AUTH_PASS\" \
      '{gsub(/\\$\\{BACKEND_SCHEME\\}/,A); \
        gsub(/\\$\\{BACKEND_TARGET\\}/,H); \
        gsub(/\\$\\{CLUSTER_LABEL\\}/,B); \
        gsub(/\\$\\{PROM_REMOTE_WRITE_URL\\}/,C); \
        gsub(/\\$\\{PROM_REMOTE_WRITE_USERNAME\\}/,D); \
        gsub(/\\$\\{PROM_REMOTE_WRITE_PASSWORD\\}/,E); \
        gsub(/\\$\\{METRICS_BASIC_AUTH_USER\\}/,F); \
        gsub(/\\$\\{METRICS_BASIC_AUTH_PASS\\}/,G); \
        print }' \
      /etc/prometheus/prometheus.yml.tmpl > /etc/prometheus/prometheus.yml; \
  # Start Prometheus \
  exec /bin/prometheus \
    --config.file=/etc/prometheus/prometheus.yml \
    --storage.tsdb.retention.time=1h \
    --web.listen-address=:8080 \
    --log.level=info \
"]
