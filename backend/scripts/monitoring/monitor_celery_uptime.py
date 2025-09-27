#!/usr/bin/env python3
"""
Monitor Celery services to verify keep-alive is preventing spindown.
"""

from datetime import datetime
import time

import httpx

# Service endpoints
SERVICES = {
    "worker": "https://instructly-celery-worker.onrender.com/health",
    "beat": "https://instructly-celery-beat.onrender.com/health",
    "flower": {
        "url": "https://instructly-flower.onrender.com/api/workers",
        "auth": ("admin", "1F2Z5pQHTLD9cCHcFwMwHkhMm7RJWkbM"),
    },
}


def check_service(name, config):
    """Check if a service is responding."""
    start = time.time()
    try:
        if isinstance(config, dict):
            # Flower with auth
            response = httpx.get(config["url"], auth=config["auth"], timeout=30.0)
        else:
            # Simple health check
            response = httpx.get(config, timeout=30.0)

        duration = time.time() - start

        if response.status_code == 200:
            return {
                "status": "UP",
                "response_time": f"{duration:.2f}s",
                "cold_start": duration > 10,  # Likely cold start if >10s
            }
        else:
            return {"status": "ERROR", "code": response.status_code, "response_time": f"{duration:.2f}s"}
    except Exception as e:
        duration = time.time() - start
        return {"status": "DOWN", "error": str(e), "response_time": f"{duration:.2f}s"}


def monitor_services(duration_minutes=30, check_interval=60):
    """Monitor services for specified duration."""
    print(f"=== Monitoring Celery Services for {duration_minutes} minutes ===")
    print(f"Check interval: {check_interval} seconds")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\nIf services stay UP without cold starts, keep-alive is working!\n")

    checks = []
    start_time = time.time()
    check_count = 0

    while (time.time() - start_time) < (duration_minutes * 60):
        check_count += 1
        timestamp = datetime.now().strftime("%H:%M:%S")

        print(f"\n[Check #{check_count} at {timestamp}]")

        results = {}
        for service_name, config in SERVICES.items():
            result = check_service(service_name, config)
            results[service_name] = result

            status_str = f"{service_name.capitalize()}: {result['status']} ({result['response_time']})"
            if result.get("cold_start"):
                status_str += " ⚠️ COLD START DETECTED!"
            print(f"  {status_str}")

        checks.append({"timestamp": timestamp, "results": results})

        # Check for keep-alive task execution
        if check_count % 5 == 0:  # Every 5 checks
            print("\n  Keep-alive tasks should have run:")
            print("  - simple_ping: ~" + str(check_count // 5) + " times")
            print("  - ping_all_services: ~" + str(check_count // 10) + " times")

        if check_count < (duration_minutes * 60 / check_interval):
            time.sleep(check_interval)

    # Summary
    print("\n=== Monitoring Summary ===")
    total_checks = len(checks)

    for service in SERVICES.keys():
        up_count = sum(1 for c in checks if c["results"][service]["status"] == "UP")
        cold_starts = sum(1 for c in checks if c["results"][service].get("cold_start", False))

        print(f"\n{service.capitalize()}:")
        print(f"  Uptime: {up_count}/{total_checks} ({up_count/total_checks*100:.1f}%)")
        print(f"  Cold starts: {cold_starts}")

    print("\n=== Conclusion ===")
    all_up = all(c["results"][s]["status"] == "UP" for c in checks for s in SERVICES.keys())
    no_cold_starts = not any(c["results"][s].get("cold_start", False) for c in checks for s in SERVICES.keys())

    if all_up and no_cold_starts:
        print("✅ Keep-alive is working perfectly! No spindowns detected.")
    elif all_up:
        print("⚠️ Services stayed up but some cold starts detected.")
    else:
        print("❌ Service interruptions detected. Keep-alive may need adjustment.")


if __name__ == "__main__":
    # Monitor for 30 minutes with checks every 60 seconds
    monitor_services(duration_minutes=30, check_interval=60)
