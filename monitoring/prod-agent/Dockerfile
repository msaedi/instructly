FROM prom/prometheus:v2.55.0

COPY prometheus.yml.tmpl /etc/prometheus/prometheus.yml.tmpl

ENTRYPOINT ["/bin/sh","-lc", "\
  # Validate required envs (no secrets in logs) \
  test -n \"$BACKEND_TARGET\" -a -n \"$CLUSTER_LABEL\" -a -n \"$PROM_REMOTE_WRITE_URL\" -a -n \"$PROM_REMOTE_WRITE_USERNAME\" -a -n \"$PROM_REMOTE_WRITE_PASSWORD\" || { echo 'prom-agent: missing required envs' >&2; exit 1; }; \
  # Render effective config via awk substitution \
  awk -v A=\"$BACKEND_TARGET\" -v B=\"$CLUSTER_LABEL\" -v C=\"$PROM_REMOTE_WRITE_URL\" -v D=\"$PROM_REMOTE_WRITE_USERNAME\" -v E=\"$PROM_REMOTE_WRITE_PASSWORD\" ' \
    {gsub(/\\$\\{BACKEND_TARGET\\}/,A); \
     gsub(/\\$\\{CLUSTER_LABEL\\}/,B); \
     gsub(/\\$\\{PROM_REMOTE_WRITE_URL\\}/,C); \
     gsub(/\\$\\{PROM_REMOTE_WRITE_USERNAME\\}/,D); \
     gsub(/\\$\\{PROM_REMOTE_WRITE_PASSWORD\\}/,E); \
     print }' /etc/prometheus/prometheus.yml.tmpl > /etc/prometheus/prometheus.yml; \
  # Launch Prometheus \
  exec /bin/prometheus \
    --config.file=/etc/prometheus/prometheus.yml \
    --storage.tsdb.retention.time=1h \
    --web.listen-address=:8080 \
    --log.level=info \
"]
