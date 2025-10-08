FROM prom/prometheus:v2.55.0

# Prometheus config template with placeholders
COPY prometheus.yml.tmpl /etc/prometheus/prometheus.yml.tmpl

ENTRYPOINT ["/bin/sh","-lc","\
  set -eu; \
  \
  # --- required envs (no secrets in logs) --- \
  req='BACKEND_TARGET CLUSTER_LABEL PROM_REMOTE_WRITE_URL PROM_REMOTE_WRITE_USERNAME PROM_REMOTE_WRITE_PASSWORD METRICS_BASIC_AUTH_USER METRICS_BASIC_AUTH_PASS'; \
  for k in $req; do v=\"$(eval echo \\$$k)\"; if [ -z \"${v:-}\" ]; then echo \"prom-agent: missing env $k\" >&2; exit 1; fi; done; \
  \
  # --- normalize BACKEND_TARGET to host:port (scheme is set in the template) --- \
  raw=\"$BACKEND_TARGET\"; \
  hp=\"${raw#http://}\"; hp=\"${hp#https://}\"; hp=\"${hp%%/*}\"; \
  case \"$hp\" in \
    *:*) norm=\"$hp\" ;; \
    *)   norm=\"$hp:443\" ;; \
  esac; \
  \
  # --- short visibility without secrets --- \
  passlen() { printf '%s' \"$1\" | wc -c | tr -d ' '; }; \
  echo \"prom-agent starting; scheme=https target=$norm cluster=$CLUSTER_LABEL user=$METRICS_BASIC_AUTH_USER pass_len=$(passlen \"$METRICS_BASIC_AUTH_PASS\")\"; \
  \
  # --- render effective Prometheus config --- \
  awk -v A=\"$norm\" \
      -v B=\"$CLUSTER_LABEL\" \
      -v C=\"$PROM_REMOTE_WRITE_URL\" \
      -v D=\"$PROM_REMOTE_WRITE_USERNAME\" \
      -v E=\"$PROM_REMOTE_WRITE_PASSWORD\" \
      -v F=\"$METRICS_BASIC_AUTH_USER\" \
      -v G=\"$METRICS_BASIC_AUTH_PASS\" \
      '{ gsub(/\\$\\{BACKEND_TARGET\\}/,A); \
         gsub(/\\$\\{CLUSTER_LABEL\\}/,B); \
         gsub(/\\$\\{PROM_REMOTE_WRITE_URL\\}/,C); \
         gsub(/\\$\\{PROM_REMOTE_WRITE_USERNAME\\}/,D); \
         gsub(/\\$\\{PROM_REMOTE_WRITE_PASSWORD\\}/,E); \
         gsub(/\\$\\{METRICS_BASIC_AUTH_USER\\}/,F); \
         gsub(/\\$\\{METRICS_BASIC_AUTH_PASS\\}/,G); \
         print }' \
      /etc/prometheus/prometheus.yml.tmpl > /etc/prometheus/prometheus.yml; \
  \
  # --- start Prometheus --- \
  exec /bin/prometheus \
    --config.file=/etc/prometheus/prometheus.yml \
    --storage.tsdb.retention.time=1h \
    --web.listen-address=:8080 \
    --log.level=info \
"]
