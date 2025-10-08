FROM prom/prometheus:v2.55.0

# Copy templated config
COPY prometheus.yml.tmpl /etc/prometheus/prometheus.yml.tmpl

# Render the template with awk (no package installs needed), then run Prometheus
# We replace the five placeholders used in the template.
ENTRYPOINT ["/bin/sh","-lc", "\
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
    /etc/prometheus/prometheus.yml.tmpl > /etc/prometheus/prometheus.yml && \
  exec /bin/prometheus \
    --config.file=/etc/prometheus/prometheus.yml \
    --storage.tsdb.retention.time=1h \
    --web.enable-lifecycle=false \
    --web.listen-address=:8080 \
    --log.format=logfmt \
"]
