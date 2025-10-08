FROM prom/prometheus:v2.55.0

COPY prometheus.yml.tmpl /etc/prometheus/prometheus.yml.tmpl

ENTRYPOINT ["/bin/sh","-lc", "\
  set -eu; \
  # --- required envs --- \
  req='BACKEND_SCHEME BACKEND_TARGET CLUSTER_LABEL PROM_REMOTE_WRITE_URL PROM_REMOTE_WRITE_USERNAME PROM_REMOTE_WRITE_PASSWORD METRICS_BASIC_AUTH_USER METRICS_BASIC_AUTH_PASS'; \
  for k in $req; do eval v=\$$k; if [ -z \"${v:-}\" ]; then echo \"prom-agent: missing env $k\" >&2; exit 1; fi; done; \
  # --- mask/length so we know agent sees the vars --- \
  len() { printf '%s' \"$1\" | wc -c | tr -d ' '; }; \
  echo \"prom-agent starting; scheme=$BACKEND_SCHEME target=$BACKEND_TARGET cluster=$CLUSTER_LABEL user=$METRICS_BASIC_AUTH_USER pass_len=$(len \"$METRICS_BASIC_AUTH_PASS\")\"; \
  # --- render effective config --- \
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
  echo '==== effective /etc/prometheus/prometheus.yml (redacted) ===='; \
  sed -n '1,200p' /etc/prometheus/prometheus.yml | sed 's/password: .*/password: \"***REDACTED***\"/'; \
  # --- optional local auth smoke (set SMOKE_AUTH=1) --- \
  if [ \"${SMOKE_AUTH:-0}\" = \"1\" ]; then \
    METRICS_URL=\"$BACKEND_SCHEME://$BACKEND_TARGET/metrics\"; \
    echo \"smoke: GET $METRICS_URL without auth (expect 401)\"; \
    wget -q --server-response --spider --no-check-certificate --timeout=10 --tries=1 \"$METRICS_URL\" 2>&1 | sed -n '1,3p' || true; \
    echo \"smoke: GET $METRICS_URL with basic auth (expect 200)\"; \
    wget -q --server-response --no-check-certificate --timeout=10 --tries=1 \
         --http-user=\"$METRICS_BASIC_AUTH_USER\" \
         --http-password=\"$METRICS_BASIC_AUTH_PASS\" \
         -O - \"$METRICS_URL\" 2>&1 | sed -n '1,10p' || true; \
  fi; \
  # --- start prometheus (debug log to see scrape auth results) --- \
  exec /bin/prometheus \
    --config.file=/etc/prometheus/prometheus.yml \
    --storage.tsdb.retention.time=1h \
    --web.listen-address=:8080 \
    --log.level=debug \
"]
