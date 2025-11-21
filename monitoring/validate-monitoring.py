#!/usr/bin/env python3
"""
InstaInstru Monitoring Validation Suite

This script validates that the monitoring infrastructure is working correctly by:
1. Connecting to Prometheus
2. Verifying expected metrics exist
3. Generating synthetic traffic
4. Checking metrics appear within 30 seconds
5. Verifying alert rules are evaluated
6. Producing a validation report

Usage: python monitoring/validate-monitoring.py
"""

import sys
import time
import json
import asyncio
from datetime import datetime
from typing import Dict, List, Set, Optional

try:
    import httpx
except ImportError:
    print("ERROR: httpx is required. Install with: pip install httpx")
    sys.exit(1)

try:
    from colorama import init, Fore, Style
    # Initialize colorama for cross-platform colored output
    init(autoreset=True)
    COLORS_AVAILABLE = True
except ImportError:
    # Fallback when colorama is not available
    class MockColor:
        def __getattr__(self, name):
            return ""

    Fore = MockColor()
    Style = MockColor()
    COLORS_AVAILABLE = False

# Configuration
PROMETHEUS_URL = "http://localhost:9090"
BACKEND_URL = "http://localhost:8000"
GRAFANA_URL = "http://localhost:3003"
GRAFANA_USER = "admin"
GRAFANA_PASSWORD = "GrafanaPassword123!"
VALIDATION_TIMEOUT = 30  # seconds to wait for metrics

# Expected metrics from @measure_operation decorators
EXPECTED_SERVICE_METRICS = {
    "instainstru_service_operation_duration_seconds": {
        "type": "histogram",
        "labels": ["service", "operation"],
        "services": [
            "AuthService", "InstructorService",
            "AvailabilityService", "BookingService",
            "EmailService", "CacheService", "SlotManager", "ConflictChecker",
            "NotificationService", "PasswordResetService", "BulkOperationService",
            "WeekOperationService", "PresentationService", "TemplateService"
        ]
    },
    "instainstru_service_operations_total": {
        "type": "counter",
        "labels": ["service", "operation", "status"]
    },
    "instainstru_errors_total": {
        "type": "counter",
        "labels": ["service", "operation", "error_type"]
    }
}

# Expected HTTP metrics
EXPECTED_HTTP_METRICS = {
    "instainstru_http_requests_total": {
        "type": "counter",
        "labels": ["method", "endpoint", "status_code"]
    },
    "instainstru_http_request_duration_seconds": {
        "type": "histogram",
        "labels": ["method", "endpoint", "status_code"]
    },
    "instainstru_http_requests_in_progress": {
        "type": "gauge",
        "labels": []
    }
}

# Expected cache metrics
EXPECTED_CACHE_METRICS = {
    "instainstru_cache_hits_total": {
        "type": "counter",
        "labels": ["cache_name"]
    },
    "instainstru_cache_misses_total": {
        "type": "counter",
        "labels": ["cache_name"]
    },
    "instainstru_cache_evictions_total": {
        "type": "counter",
        "labels": ["cache_name", "reason"]
    }
}

# Expected database metrics
EXPECTED_DB_METRICS = {
    "instainstru_db_query_duration_seconds": {
        "type": "histogram",
        "labels": ["query_type", "table"]
    },
    "instainstru_db_pool_connections_used": {
        "type": "gauge",
        "labels": []
    },
    "instainstru_db_pool_connections_max": {
        "type": "gauge",
        "labels": []
    }
}

# Expected alert rules
EXPECTED_ALERTS = [
    "High Error Rate (> 1%)",
    "Service Degradation",
    "High Response Time (P95 > 500ms)",
    "High Request Load (> 1000 req/s)",
    "Low Cache Hit Rate (< 70%)"
]


class MonitoringValidator:
    def __init__(self):
        self.prometheus_client = httpx.AsyncClient(base_url=PROMETHEUS_URL)
        self.backend_client = httpx.AsyncClient(base_url=BACKEND_URL)
        self.grafana_client = httpx.AsyncClient(
            base_url=GRAFANA_URL,
            auth=(GRAFANA_USER, GRAFANA_PASSWORD)
        )
        self.validation_results = {
            "timestamp": datetime.now().isoformat(),
            "prometheus_connection": False,
            "backend_connection": False,
            "grafana_connection": False,
            "metrics_found": {},
            "metrics_missing": {},
            "alerts_found": [],
            "alerts_missing": [],
            "synthetic_traffic_generated": False,
            "metrics_appeared": False,
            "dashboard_data_available": False,
            "issues": []
        }

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.prometheus_client.aclose()
        await self.backend_client.aclose()
        await self.grafana_client.aclose()

    def print_header(self, text: str):
        """Print a formatted header"""
        print(f"\n{Fore.CYAN}{'=' * 60}")
        print(f"{Fore.CYAN}{text:^60}")
        print(f"{Fore.CYAN}{'=' * 60}{Style.RESET_ALL}\n")

    def print_status(self, status: str, success: bool):
        """Print a status message with color"""
        icon = "✓" if success else "✗"
        color = Fore.GREEN if success else Fore.RED
        print(f"{color}[{icon}] {status}{Style.RESET_ALL}")

    async def check_prometheus_connection(self) -> bool:
        """Check if Prometheus is accessible"""
        try:
            response = await self.prometheus_client.get("/api/v1/query", params={"query": "up"})
            if response.status_code == 200:
                self.validation_results["prometheus_connection"] = True
                return True
        except Exception as e:
            self.validation_results["issues"].append(f"Prometheus connection failed: {str(e)}")
        return False

    async def check_backend_connection(self) -> bool:
        """Check if backend is accessible"""
        try:
            response = await self.backend_client.get("/health")
            if response.status_code == 200:
                self.validation_results["backend_connection"] = True
                return True
        except Exception as e:
            self.validation_results["issues"].append(f"Backend connection failed: {str(e)}")
        return False

    async def check_grafana_connection(self) -> bool:
        """Check if Grafana is accessible"""
        try:
            response = await self.grafana_client.get("/api/health")
            if response.status_code == 200:
                self.validation_results["grafana_connection"] = True
                return True
        except Exception as e:
            self.validation_results["issues"].append(f"Grafana connection failed: {str(e)}")
        return False

    async def query_prometheus(self, query: str) -> Optional[Dict]:
        """Execute a Prometheus query"""
        try:
            response = await self.prometheus_client.get(
                "/api/v1/query",
                params={"query": query}
            )
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            self.validation_results["issues"].append(f"Prometheus query failed: {query} - {str(e)}")
        return None

    async def get_metric_names(self) -> Set[str]:
        """Get all metric names from Prometheus"""
        result = await self.query_prometheus("group by(__name__)({__name__=~'instainstru_.*'})")
        if result and result.get("data", {}).get("result"):
            return {item["metric"]["__name__"] for item in result["data"]["result"]}
        return set()

    async def verify_metrics(self):
        """Verify all expected metrics exist"""
        print(f"{Fore.YELLOW}Checking metrics...{Style.RESET_ALL}")

        metric_names = await self.get_metric_names()
        all_expected = {}

        # Combine all expected metrics
        all_expected.update(EXPECTED_SERVICE_METRICS)
        all_expected.update(EXPECTED_HTTP_METRICS)
        all_expected.update(EXPECTED_CACHE_METRICS)
        all_expected.update(EXPECTED_DB_METRICS)

        for metric_name, metric_info in all_expected.items():
            if metric_name in metric_names:
                self.validation_results["metrics_found"][metric_name] = metric_info["type"]
                self.print_status(f"Found metric: {metric_name}", True)

                # Check for specific service labels
                if metric_name == "instainstru_service_operation_duration_seconds":
                    await self.verify_service_metrics(metric_name, metric_info["services"])
            else:
                self.validation_results["metrics_missing"][metric_name] = metric_info["type"]
                self.print_status(f"Missing metric: {metric_name}", False)

    async def verify_service_metrics(self, metric_name: str, expected_services: List[str]):
        """Verify service-specific metrics"""
        result = await self.query_prometheus(f"group by(service)({metric_name}_count)")
        if result and result.get("data", {}).get("result"):
            found_services = {item["metric"].get("service", "") for item in result["data"]["result"]}
            for service in expected_services:
                if service in found_services:
                    print(f"  {Fore.GREEN}✓ {service}{Style.RESET_ALL}")
                else:
                    print(f"  {Fore.YELLOW}○ {service} (no data yet){Style.RESET_ALL}")

    async def generate_synthetic_traffic(self):
        """Generate various types of requests to populate metrics"""
        print(f"\n{Fore.YELLOW}Generating synthetic traffic...{Style.RESET_ALL}")

        endpoints = [
            # Successful requests
            ("GET", "/health", 200),
            ("GET", "/api/instructors", 200),
            ("GET", "/api/public/instructors", 200),
            ("GET", "/metrics/prometheus", 200),

            # Error requests
            ("GET", "/api/nonexistent", 404),
            ("POST", "/api/auth/login", 422),  # Invalid payload
            ("GET", "/api/admin/users", 401),  # Unauthorized

            # Instructor operations
            ("GET", "/api/public/instructors/01J5TESTINSTR0000000000001/availability", 200),
            ("GET", "/api/instructors/profile", 401),  # Needs auth
        ]

        tasks = []
        for method, endpoint, expected_status in endpoints:
            # Generate multiple requests for each endpoint
            for i in range(5):
                if method == "GET":
                    tasks.append(self.backend_client.get(endpoint))
                elif method == "POST":
                    tasks.append(self.backend_client.post(endpoint, json={"invalid": "data"}))

        # Execute all requests concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = sum(1 for r in results if not isinstance(r, Exception))
        error_count = len(results) - success_count

        self.validation_results["synthetic_traffic_generated"] = True
        self.print_status(
            f"Generated {len(results)} requests ({success_count} successful, {error_count} errors)",
            True
        )

    async def wait_for_metrics(self) -> bool:
        """Wait for metrics to appear in Prometheus"""
        print(f"\n{Fore.YELLOW}Waiting for metrics to appear (max {VALIDATION_TIMEOUT}s)...{Style.RESET_ALL}")

        start_time = time.time()
        metrics_to_check = [
            "instainstru_http_requests_total",
            "instainstru_http_request_duration_seconds_count"
        ]

        while time.time() - start_time < VALIDATION_TIMEOUT:
            all_found = True
            for metric in metrics_to_check:
                result = await self.query_prometheus(f"increase({metric}[1m])")
                if not result or not result.get("data", {}).get("result"):
                    all_found = False
                    break

            if all_found:
                elapsed = time.time() - start_time
                self.validation_results["metrics_appeared"] = True
                self.print_status(f"Metrics appeared after {elapsed:.1f} seconds", True)
                return True

            await asyncio.sleep(2)

        self.print_status(f"Metrics did not appear within {VALIDATION_TIMEOUT} seconds", False)
        self.validation_results["issues"].append("Metrics propagation timeout")
        return False

    async def verify_alerts(self):
        """Verify alert rules are configured and being evaluated"""
        print(f"\n{Fore.YELLOW}Checking alert rules...{Style.RESET_ALL}")

        try:
            # Get alert rules from Grafana
            response = await self.grafana_client.get("/api/v1/provisioning/alert-rules")
            if response.status_code == 200:
                rules = response.json()
                found_alerts = set()

                for rule_group in rules:
                    for rule in rule_group.get("rules", []):
                        title = rule.get("title", "")
                        if title in EXPECTED_ALERTS:
                            found_alerts.add(title)
                            self.validation_results["alerts_found"].append(title)
                            self.print_status(f"Alert configured: {title}", True)

                # Check for missing alerts
                for alert in EXPECTED_ALERTS:
                    if alert not in found_alerts:
                        self.validation_results["alerts_missing"].append(alert)
                        self.print_status(f"Alert missing: {alert}", False)
            else:
                self.validation_results["issues"].append(f"Failed to fetch alerts: HTTP {response.status_code}")
        except Exception as e:
            self.validation_results["issues"].append(f"Alert verification failed: {str(e)}")

    async def verify_dashboard_data(self):
        """Verify dashboards can query data"""
        print(f"\n{Fore.YELLOW}Checking dashboard data availability...{Style.RESET_ALL}")

        # Check if key metrics have data for dashboards
        dashboard_queries = [
            ("Request Rate", "sum(rate(instainstru_http_requests_total[5m]))"),
            ("Error Rate", "sum(rate(instainstru_http_requests_total{status_code=~'5..'}[5m]))"),
            ("P95 Latency", "histogram_quantile(0.95, sum(rate(instainstru_http_request_duration_seconds_bucket[5m])) by (le))"),
            ("Active Services", "count(group by(service)(instainstru_service_operation_duration_seconds_count))")
        ]

        data_available = True
        for query_name, query in dashboard_queries:
            result = await self.query_prometheus(query)
            if result and result.get("data", {}).get("result"):
                self.print_status(f"Dashboard data available: {query_name}", True)
            else:
                self.print_status(f"No data for: {query_name}", False)
                data_available = False

        self.validation_results["dashboard_data_available"] = data_available

    def generate_report(self) -> str:
        """Generate validation report"""
        report = []
        report.append("\n" + "=" * 60)
        report.append("MONITORING VALIDATION REPORT")
        report.append("=" * 60)
        report.append(f"Timestamp: {self.validation_results['timestamp']}")
        report.append("")

        # Connection Status
        report.append("CONNECTION STATUS:")
        report.append(f"  Prometheus: {'✓' if self.validation_results['prometheus_connection'] else '✗'}")
        report.append(f"  Backend:    {'✓' if self.validation_results['backend_connection'] else '✗'}")
        report.append(f"  Grafana:    {'✓' if self.validation_results['grafana_connection'] else '✗'}")
        report.append("")

        # Metrics Summary
        found_count = len(self.validation_results['metrics_found'])
        missing_count = len(self.validation_results['metrics_missing'])
        total_count = found_count + missing_count

        report.append("METRICS SUMMARY:")
        report.append(f"  Total Expected: {total_count}")
        report.append(f"  Found:         {found_count}")
        report.append(f"  Missing:       {missing_count}")

        if missing_count > 0:
            report.append("\n  Missing Metrics:")
            for metric in self.validation_results['metrics_missing']:
                report.append(f"    - {metric}")
        report.append("")

        # Alerts Summary
        alerts_found = len(self.validation_results['alerts_found'])
        alerts_missing = len(self.validation_results['alerts_missing'])

        report.append("ALERTS SUMMARY:")
        report.append(f"  Total Expected: {len(EXPECTED_ALERTS)}")
        report.append(f"  Configured:    {alerts_found}")
        report.append(f"  Missing:       {alerts_missing}")

        if alerts_missing > 0:
            report.append("\n  Missing Alerts:")
            for alert in self.validation_results['alerts_missing']:
                report.append(f"    - {alert}")
        report.append("")

        # Validation Results
        report.append("VALIDATION RESULTS:")
        report.append(f"  Synthetic Traffic Generated: {'✓' if self.validation_results['synthetic_traffic_generated'] else '✗'}")
        report.append(f"  Metrics Appeared:           {'✓' if self.validation_results['metrics_appeared'] else '✗'}")
        report.append(f"  Dashboard Data Available:   {'✓' if self.validation_results['dashboard_data_available'] else '✗'}")
        report.append("")

        # Issues
        if self.validation_results['issues']:
            report.append("ISSUES FOUND:")
            for issue in self.validation_results['issues']:
                report.append(f"  - {issue}")
            report.append("")

        # Overall Status
        all_connections = all([
            self.validation_results['prometheus_connection'],
            self.validation_results['backend_connection'],
            self.validation_results['grafana_connection']
        ])

        metrics_ok = missing_count == 0 and self.validation_results['metrics_appeared']
        alerts_ok = alerts_missing == 0

        overall_status = all([
            all_connections,
            metrics_ok,
            alerts_ok,
            self.validation_results['dashboard_data_available']
        ])

        report.append("OVERALL STATUS: " + ("✓ PASS" if overall_status else "✗ FAIL"))
        report.append("=" * 60)

        # Save detailed JSON report
        with open("monitoring/validation-report.json", "w") as f:
            json.dump(self.validation_results, f, indent=2)
        report.append("\nDetailed report saved to: monitoring/validation-report.json")

        return "\n".join(report)

    async def run_validation(self):
        """Run complete validation suite"""
        self.print_header("iNSTAiNSTRU Monitoring Validation")

        # Step 1: Check connections
        print(f"{Fore.YELLOW}Checking connections...{Style.RESET_ALL}")
        prometheus_ok = await self.check_prometheus_connection()
        self.print_status("Prometheus connection", prometheus_ok)

        backend_ok = await self.check_backend_connection()
        self.print_status("Backend connection", backend_ok)

        grafana_ok = await self.check_grafana_connection()
        self.print_status("Grafana connection", grafana_ok)

        if not all([prometheus_ok, backend_ok]):
            print(f"\n{Fore.RED}Cannot continue without Prometheus and Backend connections{Style.RESET_ALL}")
            return False

        # Step 2: Verify existing metrics
        await self.verify_metrics()

        # Step 3: Generate synthetic traffic
        await self.generate_synthetic_traffic()

        # Step 4: Wait for metrics to appear
        await self.wait_for_metrics()

        # Step 5: Verify alerts (if Grafana is available)
        if grafana_ok:
            await self.verify_alerts()
        else:
            print(f"\n{Fore.YELLOW}Skipping alert verification (Grafana not available){Style.RESET_ALL}")

        # Step 6: Verify dashboard data
        await self.verify_dashboard_data()

        # Generate and display report
        report = self.generate_report()
        print(report)

        # Return overall pass/fail
        return "PASS" in report


async def main():
    """Main entry point"""
    async with MonitoringValidator() as validator:
        success = await validator.run_validation()
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Validation interrupted by user{Style.RESET_ALL}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Fore.RED}Validation failed with error: {str(e)}{Style.RESET_ALL}")
        sys.exit(1)
