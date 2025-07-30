# Redis 7 Alpine for minimal resource usage
FROM redis:7-alpine

# Copy custom Redis configuration
COPY redis.conf /usr/local/etc/redis/redis.conf

# Run Redis with custom configuration
# Note: No EXPOSE or HEALTHCHECK - this is a private TCP service
CMD ["redis-server", "/usr/local/etc/redis/redis.conf"]
