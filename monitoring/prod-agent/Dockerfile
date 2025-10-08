FROM prom/prometheus:v2.55.0

# Template with placeholders – already in repo
COPY prometheus.yml.tmpl /etc/prometheus/prometheus.yml.tmpl

ENTRYPOINT ["/bin/sh","-lc", "\
  # Validate required envs (do NOT echo secrets) \n\
  required='BACKEND_TARGET CLUSTER_LABEL PROM_REMOTE_WRITE_URL PROM_REMOTE_WRITE_USERNAME PROM_REMOTE_WRITE_PASSWORD METRICS_BASIC_AUTH_USER METRICS_BASIC_AUTH_PASS'; \n\
  for v in $required; do eval '[ -n \"${'$v'}\" ]' || { echo \"prom-agent: missing $v\" >&2; exit 1; }; done; \n\
  # Render effective config via awk substitution \n\
  awk -v A=\"$BACKEND_TARGET\" \\\n\
      -v B=\"$CLUSTER_LABEL\" \\\n\
      -v C=\"$PROM_REMOTE_WRITE_URL\" \\\n\
      -v D=\"$PROM_REMOTE_WRITE_USERNAME\" \\\n\
      -v E=\"$PROM_REMOTE_WRITE_PASSWORD\" \\\n\
      -v U=\"$METRICS_BASIC_AUTH_USER\" \\\n\
      -v P=\"$METRICS_BASIC_AUTH_PASS\" ' \\\n\
    { gsub(/\\$\\{BACKEND_TARGET\\}/,A); \\\n\
      gsub(/\\$\\{CLUSTER_LABEL\\}/,B); \\\n\
      gsub(/\\$\\{PROM_REMOTE_WRITE_URL\\}/,C); \\\n\
      gsub(/\\$\\{PROM_REMOTE_WRITE_USERNAME\\}/,D); \\\n\
      gsub(/\\$\\{PROM_REMOTE_WRITE_PASSWORD\\}/,E); \\\n\
      gsub(/\\$\\{METRICS_BASIC_AUTH_USER\\}/,U); \\\n\
      gsub(/\\$\\{METRICS_BASIC_AUTH_PASS\\}/,P); \\\n\
      print }' /etc/prometheus/prometheus.yml.tmpl > /etc/prometheus/prometheus.yml; \n\
  # Launch Prometheus \n\
  exec /bin/prometheus \\\n\
    --config.file=/etc/prometheus/prometheus.yml \\\n\
    --storage.tsdb.retention.time=1h \\\n\
    --web.listen-address=:8080 \\\n\
    --log.level=info \n\
"]
