FROM prom/prometheus:v2.55.0

COPY prometheus.yml.tmpl /etc/prometheus/prometheus.yml.tmpl

ENTRYPOINT ["/bin/sh","-lc", "\
  set -eux; \
  echo '==== prom-agent envs (redacted) ===='; \
  echo BACKEND_TARGET=${BACKEND_TARGET:-'(empty)'}; \
  echo CLUSTER_LABEL=${CLUSTER_LABEL:-'(empty)'}; \
  test -n \"${PROM_REMOTE_WRITE_URL:-}\" || { echo 'PROM_REMOTE_WRITE_URL is empty' >&2; exit 1; }; \
  test -n \"${PROM_REMOTE_WRITE_USERNAME:-}\" || { echo 'PROM_REMOTE_WRITE_USERNAME is empty' >&2; exit 1; }; \
  test -n \"${PROM_REMOTE_WRITE_PASSWORD:-}\" || { echo 'PROM_REMOTE_WRITE_PASSWORD is empty' >&2; exit 1; }; \
  awk -v A=\"$BACKEND_TARGET\" \
      -v B=\"$CLUSTER_LABEL\" \
      -v C=\"$PROM_REMOTE_WRITE_URL\" \
      -v D=\"$PROM_REMOTE_WRITE_USERNAME\" \
      -v E=\"$PROM_REMOTE_WRITE_PASSWORD\" \
    '{gsub(/\\$\\{BACKEND_TARGET\\}/,A); \
      gsub(/\\$\\{CLUSTER_LABEL\\}/,B); \
      gsub(/\\$\\{PROM_REMOTE_WRITE_URL\\}/,C); \
      gsub(/\\$\\{PROM_REMOTE_WRITE_USERNAME\\}/,D); \
      gsub(/\\$\\{PROM_REMOTE_WRITE_PASSWORD\\}/,E); \
      print}' \
    /etc/prometheus/prometheus.yml.tmpl > /etc/prometheus/prometheus.yml; \
  echo '==== effective /etc/prometheus/prometheus.yml ===='; \
  sed -n '1,200p' /etc/prometheus/prometheus.yml; \
  echo '==== starting Prometheus ===='; \
  exec /bin/prometheus \
    --config.file=/etc/prometheus/prometheus.yml \
    --storage.tsdb.retention.time=1h \
    --web.listen-address=:8080 \
    --log.level=debug \
    --log.format=logfmt \
"]
