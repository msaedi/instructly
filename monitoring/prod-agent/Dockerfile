FROM prom/prometheus:v2.55.0
COPY prometheus.yml.tmpl /etc/prometheus/prometheus.yml.tmpl

ENTRYPOINT ["/bin/sh","-lc", "\
  set -e; \
  # Render template
  awk -v A=\"$BACKEND_TARGET\" \
      -v B=\"$CLUSTER_LABEL\" \
      -v C=\"$PROM_REMOTE_WRITE_URL\" \
      -v D=\"$PROM_REMOTE_WRITE_USERNAME\" \
      -v E=\"$PROM_REMOTE_WRITE_PASSWORD\" \
      -v F=\"$BACKEND_SCHEME\" \
    '{gsub(/\\$\\{BACKEND_TARGET\\}/,A); \
      gsub(/\\$\\{CLUSTER_LABEL\\}/,B); \
      gsub(/\\$\\{PROM_REMOTE_WRITE_URL\\}/,C); \
      gsub(/\\$\\{PROM_REMOTE_WRITE_USERNAME\\}/,D); \
      gsub(/\\$\\{PROM_REMOTE_WRITE_PASSWORD\\}/,E); \
      gsub(/\\$\\{BACKEND_SCHEME\\}/,F); \
      print}' \
    /etc/prometheus/prometheus.yml.tmpl > /etc/prometheus/prometheus.yml; \
  echo \"prom-agent starting; target=$BACKEND_SCHEME://$BACKEND_TARGET cluster=$CLUSTER_LABEL\"; \
  exec /bin/prometheus \
    --config.file=/etc/prometheus/prometheus.yml \
    --storage.tsdb.retention.time=1h \
    --web.listen-address=:8080 \
    --log.level=debug \
    --log.format=logfmt \
"]
