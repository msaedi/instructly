# Redis 7 Alpine for minimal resource usage
FROM redis:7-alpine

# Copy custom Redis configuration
COPY ./redis/redis.conf /usr/local/etc/redis/redis.conf

# Expose Redis port
EXPOSE 6379

# Health check to ensure Redis is running
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD redis-cli ping || exit 1

# Run Redis with custom configuration
CMD ["redis-server", "/usr/local/etc/redis/redis.conf"]
