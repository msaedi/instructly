#!/bin/bash
# Run Celery with test database

# Check if USE_TEST_DATABASE is set
if [ "$USE_TEST_DATABASE" = "true" ]; then
    echo "Running Celery with TEST database..."
    # Override DATABASE_URL with test database URL
    export DATABASE_URL="${test_database_url:-postgresql://postgres:postgres@localhost:5432/instainstru_test}"
else
    echo "Running Celery with PRODUCTION database..."
fi

# Run Celery worker
celery -A app.tasks worker --loglevel=info -Q celery,analytics
