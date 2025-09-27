#!/usr/bin/env python
"""Test Celery tasks after fixes."""

from pathlib import Path
import sys
import time

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

from app.tasks.analytics import calculate_analytics
from app.tasks.celery_app import health_check

print("Testing Celery Tasks After Fixes")
print("=" * 50)

# Test 1: Health Check
print("\n1. Testing health_check task...")
result = health_check.delay()
print(f"   Task ID: {result.id}")

# Give it a moment to process
time.sleep(2)

# Check result
try:
    task_result = result.get(timeout=5)
    print(f"   ✓ Success! Result: {task_result}")
except Exception as e:
    print(f"   ✗ Failed: {e}")

# Test 2: Analytics (will go to analytics queue)
print("\n2. Testing calculate_analytics task...")
result = calculate_analytics.delay(days_back=1)
print(f"   Task ID: {result.id}")
print("   Note: This task goes to 'analytics' queue")

print("\n" + "=" * 50)
print("Remember to restart the worker after code changes!")
print("Run: celery -A app.tasks worker --loglevel=info -Q celery,analytics")
