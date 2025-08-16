# InstaInstru CI Database Image
# Combines PostGIS + pgvector for complete test coverage
FROM postgis/postgis:14-3.3

LABEL maintainer="InstaInstru X-Team"
LABEL description="PostgreSQL 14 with PostGIS 3.3 and pgvector for CI"
LABEL org.opencontainers.image.source="https://github.com/YOUR_GITHUB_ORG/InstaInstru"

# Install pgvector from official PostgreSQL apt repository
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        postgresql-14-pgvector && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Just verify the extension files exist (not running psql)
RUN ls -la /usr/share/postgresql/14/extension/vector* && \
    ls -la /usr/share/postgresql/14/extension/postgis* && \
    echo "✅ Extension files verified"

# Health check
HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
    CMD pg_isready -U postgres
