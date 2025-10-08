FROM prom/prometheus:v2.55.0

COPY prometheus.yml.tmpl /etc/prometheus/prometheus.yml.tmpl

ENTRYPOINT ["/bin/sh","-lc", "\
  set -eu; \
  # --- required envs (no secrets in logs) --- \
  req='BACKEND_TARGET CLUSTER_LABEL PROM_REMOTE_WRITE_URL PROM_REMOTE_WRITE_USERNAME PROM_REMOTE_WRITE_PASSWORD METRICS_BASIC_AUTH_USER METRICS_BASIC_AUTH_PASS'; \
  for k in $req; do eval v=\\$$k; if [ -z \"${v:-}\" ]; then echo \"prom-agent: missing env $k\" >&2; exit 1; fi; done; \
  # --- mask + lengths so we know agent sees the vars --- \
  len() { printf '%s' \"$1\" | wc -c | tr -d ' '; }; \
  echo \"prom-agent starting; target=https://$BACKEND_TARGET cluster=$CLUSTER_LABEL user=$METRICS_BASIC_AUTH_USER pass_len=$(len \"$METRICS_BASIC_AUTH_PASS\")\"; \
  # --- optional local smoke (set SMOKE_AUTH=1 on the agent) --- \
  if [ \"${SMOKE_AUTH:-0}\" = \"1\" ]; then \
    METRICS_URL=\"https://$BACKEND_TARGET/metrics\"; \
    echo \"smoke: GET $METRICS_URL with basic auth (user=$METRICS_BASIC_AUTH_USER)\"; \
    # busybox wget supports --http-user/--http-password \
    if wget -q --server-response --spider \
          --no-check-certificate \
          --timeout=10 \
          --tries=1 \
          --http-user=\"$METRICS_BASIC_AUTH_USER\" \
          --http-password=\"$METRICS_BASIC_AUTH_PASS\" \
          \"$METRICS_URL\" 2>&1 | sed -n '1,3p'; then \
      echo \"smoke: /metrics reachable\"; \
    else \
      echo \"smoke: /metrics failed (see status above)\" >&2; \
    fi; \
  fi; \
  # --- render effective config --- \
  awk -v A=\"$BACKEND_TARGET\" \
      -v B=\"$CLUSTER_LABEL\" \
      -v C=\"$PROM_REMOTE_WRITE_URL\" \
      -v D=\"$PROM_REMOTE_WRITE_USERNAME\" \
      -v E=\"$PROM_REMOTE_WRITE_PASSWORD\" \
      -v F=\"$METRICS_BASIC_AUTH_USER\" \
      -v G=\"$METRICS_BASIC_AUTH_PASS\" \
      '{gsub(/\\$\\{BACKEND_TARGET\\}/,A); \
        gsub(/\\$\\{CLUSTER_LABEL\\}/,B); \
        gsub(/\\$\\{PROM_REMOTE_WRITE_URL\\}/,C); \
        gsub(/\\$\\{PROM_REMOTE_WRITE_USERNAME\\}/,D); \
        gsub(/\\$\\{PROM_REMOTE_WRITE_PASSWORD\\}/,E); \
        gsub(/\\$\\{METRICS_BASIC_AUTH_USER\\}/,F); \
        gsub(/\\$\\{METRICS_BASIC_AUTH_PASS\\}/,G); \
        print }' \
      /etc/prometheus/prometheus.yml.tmpl > /etc/prometheus/prometheus.yml; \
  # --- start prometheus --- \
  exec /bin/prometheus \
    --config.file=/etc/prometheus/prometheus.yml \
    --storage.tsdb.retention.time=1h \
    --web.listen-address=:8080 \
    --log.level=info \
"]
