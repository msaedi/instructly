# InstaInstru CI Database Image
#
# PURPOSE: Combines PostGIS and pgvector extensions for comprehensive CI testing
# REASON: No official image includes both extensions required by our platform
#
# Extensions included:
# - PostGIS 3.3.x: Required for address management, region boundaries, spatial queries
# - pgvector 0.8.x: Required for NL search embeddings and service similarity
# - pg_trgm: Required for fuzzy text search (included in PostgreSQL)
#
# DO NOT REMOVE - CI tests will fail without both extensions!
#
# To update: Modify this file and push to main, GitHub Actions will rebuild
# Image location: ghcr.io/msaedi/instructly-ci-postgres:14-postgis-pgvector
#
# Usage in CI:
#   services:
#     postgres:
#       image: ghcr.io/msaedi/instructly-ci-postgres:14-postgis-pgvector
#
# Manual rebuild:
#   Go to GitHub Actions → "Build CI Database Image" → Run workflow
#
# Security: Built from official sources only, no third-party dependencies

FROM postgis/postgis:14-3.3

LABEL maintainer="InstaInstru X-Team"
LABEL description="PostgreSQL 14 with PostGIS 3.3 and pgvector for CI"
LABEL org.opencontainers.image.source="https://github.com/YOUR_GITHUB_ORG/InstaInstru"

# Install pgvector from official PostgreSQL apt repository
# This is the official distribution method for pgvector
# Version installed: postgresql-14-pgvector (latest stable)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        postgresql-14-pgvector && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Verify that both PostGIS and pgvector extension files are present
# This is a build-time check to ensure the extensions were installed correctly
# Note: We can't actually create extensions here as PostgreSQL isn't running
RUN ls -la /usr/share/postgresql/14/extension/vector* && \
    ls -la /usr/share/postgresql/14/extension/postgis* && \
    echo "✅ Extension files verified"

# Health check to ensure PostgreSQL is ready to accept connections
# Used by CI to wait for database readiness before running tests
HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
    CMD pg_isready -U postgres
