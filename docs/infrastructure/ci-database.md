# CI Database Infrastructure

## Overview
InstaInstru uses a custom PostgreSQL image for CI/CD that includes both PostGIS and pgvector extensions, which are required for our spatial features and natural language search.

## Architecture Decision

### Problem
- No official PostgreSQL image includes both PostGIS and pgvector
- CI tests fail without both extensions enabled
- Security concerns with community-built images

### Solution
- Custom image built from official PostGIS base + pgvector
- Automated builds via GitHub Actions
- Hosted on GitHub Container Registry (ghcr.io)

### Security
- Built in-house from official base images
- No third-party dependencies
- Automated security updates via dependabot
- Scanned by GitHub security features

## Image Components

| Component | Version | Purpose |
|-----------|---------|---------|
| PostgreSQL | 14 | Core database engine |
| PostGIS | 3.3.4 | Spatial queries for addresses and regions |
| pgvector | 0.8.0 | Embeddings for NL search |
| pg_trgm | 1.6 | Fuzzy text matching |

## Build Pipeline

### 1. Source Files
- **Dockerfile**: `.github/docker/postgres-ci/Dockerfile`
- **Build Action**: `.github/workflows/build-ci-database.yml`

### 2. Build Process
```yaml
# Triggered on:
- Push to main (Dockerfile changes)
- Manual workflow dispatch
- Weekly schedule (security updates)

# Build features:
- Multi-platform support (amd64, arm64)
- Docker buildx with caching
- Layer caching for faster rebuilds
```

### 3. Registry Details
- **Location**: GitHub Container Registry (ghcr.io)
- **Image**: `ghcr.io/msaedi/instructly-ci-postgres:14-postgis-pgvector`
- **Tags**:
  - `14-postgis-pgvector` (stable, recommended)
  - `latest` (current build)
  - Commit SHA tags for specific versions

## Usage in CI

### GitHub Actions Configuration
```yaml
# .github/workflows/backend-ci.yml
services:
  postgres:
    image: ghcr.io/msaedi/instructly-ci-postgres:14-postgis-pgvector
    env:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: instainstru_test
    options: >-
      --health-cmd pg_isready
      --health-interval 10s
      --health-timeout 5s
      --health-retries 5
```

### Extensions Created Automatically
The image automatically creates required extensions on database initialization:
- PostGIS extension for spatial features
- pgvector extension for embeddings
- pg_trgm for text search

## Local Testing

### Run the Image Locally
```bash
# Start the container
docker run -d \
  --name instructly-ci-db \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=instainstru_test \
  -p 5433:5432 \
  ghcr.io/msaedi/instructly-ci-postgres:14-postgis-pgvector

# Verify extensions
docker exec instructly-ci-db psql -U postgres -d instainstru_test -c "\dx"

# Stop and remove
docker stop instructly-ci-db && docker rm instructly-ci-db
```

### Test Migrations Locally
```bash
# Set test database URL
export DATABASE_URL="postgresql://postgres:postgres@localhost:5433/instainstru_test"

# Run migrations
cd backend
alembic upgrade head

# Run tests
pytest tests/
```

## Maintenance Tasks

### Routine Updates

#### Monthly Security Patches
```bash
# Rebuild with latest security patches
# Go to: Actions → "Build CI Database Image" → Run workflow
```

#### Update PostgreSQL Version
```dockerfile
# In .github/docker/postgres-ci/Dockerfile
FROM postgis/postgis:15-3.4  # Update version here
```

#### Update pgvector Version
```dockerfile
# May require updating apt sources or build method
RUN apt-get update && apt-get install -y \
    postgresql-14-pgvector=0.9.0  # Update version
```

### Troubleshooting

#### Common Issues

1. **CI Tests Failing with "extension not found"**
   - Verify image tag in workflow file
   - Check if image was successfully built
   - Ensure migrations create extensions

2. **Build Failures**
   - Check GitHub Actions logs
   - Verify Dockerfile syntax
   - Ensure base image exists

3. **Performance Issues**
   - Use specific tags, not :latest
   - Enable registry caching
   - Consider regional mirrors

#### Verification Commands
```bash
# Check if extensions are available
SELECT * FROM pg_available_extensions
WHERE name IN ('postgis', 'vector', 'pg_trgm');

# Verify PostGIS
SELECT PostGIS_version();

# Verify pgvector
SELECT vector_version();
```

## Security Considerations

### Best Practices
1. **Never use community images** - Build from official sources
2. **Pin versions** - Don't use :latest in production
3. **Regular rebuilds** - Weekly automated builds for patches
4. **Scan images** - GitHub security scanning enabled
5. **Minimal surface** - Only required extensions installed

### Access Control
- Image is public read (required for CI)
- Write access limited to repository maintainers
- Build triggered only from main branch

## Migration Path

### Adding New Extensions
1. Update Dockerfile to install extension
2. Update this documentation
3. Test locally with new image
4. Push changes to trigger rebuild
5. Update CI workflow to use new tag

### Upgrading PostgreSQL Major Version
1. Create new branch for testing
2. Update base image in Dockerfile
3. Build and test extensively
4. Create new tag (e.g., `15-postgis-pgvector`)
5. Gradually migrate CI to new version
6. Update all documentation

## Related Documentation
- [CI/CD Setup](../ci-cd/github-actions.md)
- [Database Migrations](../database/migrations.md)
- [PostGIS Spatial Features](../architecture/spatial-architecture.md)
- [NL Search with pgvector](../search/nl-search-architecture.md)

## Quick Reference

### Image Location
```
ghcr.io/msaedi/instructly-ci-postgres:14-postgis-pgvector
```

### Manual Rebuild
```
GitHub → Actions → "Build CI Database Image" → Run workflow
```

### Local Testing
```bash
docker run -d -p 5433:5432 \
  -e POSTGRES_PASSWORD=postgres \
  ghcr.io/msaedi/instructly-ci-postgres:14-postgis-pgvector
```

---

*Last Updated: December 2024*
*Maintained by: InstaInstru Platform Team*
