"""
API Contract Tests for InstaInstru Platform

This test suite ensures that all API endpoints:
1. Return responses that match their declared response models
2. Never return raw dictionaries or manual JSON responses
3. Maintain consistent field names and types
4. Use proper HTTP status codes

The tests use a combination of static analysis and runtime validation
to catch contract violations early and prevent regression.
"""

import ast
import inspect
from pathlib import Path
import re
from typing import Any, List, Optional, Set

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.main import fastapi_app as app


class ContractViolation:
    """Represents a contract violation found during testing."""

    def __init__(self, endpoint: str, method: str, violation_type: str, details: str):
        self.endpoint = endpoint
        self.method = method
        self.violation_type = violation_type
        self.details = details

    def __str__(self):
        return f"{self.method} {self.endpoint}: {self.violation_type} - {self.details}"


class APIContractAnalyzer:
    """Analyzes API routes for contract compliance."""

    def __init__(self, app: FastAPI):
        self.app = app
        self.violations: List[ContractViolation] = []

    def analyze_all_routes(self) -> List[ContractViolation]:
        """Analyze all routes in the application."""
        for route in self.app.routes:
            if hasattr(route, "endpoint") and hasattr(route, "methods"):
                for method in route.methods:
                    self._analyze_endpoint(route.path, method, route.endpoint)
        return self.violations

    def _analyze_endpoint(self, path: str, method: str, endpoint: Any) -> None:
        """Analyze a single endpoint for contract compliance."""
        # Skip OpenAPI endpoints
        if path.startswith("/openapi") or path == "/docs" or path == "/redoc":
            return

        # Get the source code
        try:
            source = inspect.getsource(endpoint)
        except Exception:
            return

        # Skip SSE (Server-Sent Events) endpoints
        if "EventSourceResponse" in source:
            return  # SSE endpoints don't use regular response models

        # Check for response_model
        if method in ["GET", "POST", "PUT", "PATCH"]:
            route_decorator = self._find_route_decorator(source, method.lower())
            if route_decorator and "response_model=" not in route_decorator:
                # Some endpoints legitimately don't need response models (like DELETE)
                if method != "DELETE" and "status_code=status.HTTP_204_NO_CONTENT" not in source:
                    self.violations.append(
                        ContractViolation(
                            path,
                            method,
                            "MISSING_RESPONSE_MODEL",
                            "Endpoint does not declare a response_model",
                        )
                    )

        # Check for direct dictionary returns
        if self._has_direct_dict_return(source):
            self.violations.append(
                ContractViolation(
                    path,
                    method,
                    "DIRECT_DICT_RETURN",
                    "Endpoint returns a dictionary directly instead of a response model",
                )
            )

        # Check for manual JSON responses
        if self._has_manual_json_response(source):
            self.violations.append(
                ContractViolation(
                    path,
                    method,
                    "MANUAL_JSON_RESPONSE",
                    "Endpoint creates manual JSON responses instead of using response models",
                )
            )

    def _find_route_decorator(self, source: str, method: str) -> Optional[str]:
        """Find the route decorator in the source code."""
        pattern = rf"@router\.{method}\s*\([^)]+\)"
        match = re.search(pattern, source, re.DOTALL)
        return match.group(0) if match else None

    def _has_direct_dict_return(self, source: str) -> bool:
        """Check if the function returns a dictionary directly."""
        # Look for patterns like "return {" or "return dict(" or "return variable_dict"
        dict_return_patterns = [
            r"return\s+{",
            r"return\s+dict\(",
            r"return\s+\w+\.dict\(\)",  # Catches model.dict()
            r"return\s+\w+_dict\b",  # Catches variables named *_dict
        ]

        for pattern in dict_return_patterns:
            if re.search(pattern, source):
                # Make sure it's not returning a response model
                if not re.search(r"return\s+\w+Response\(", source):
                    return True

        # Also check for manual dictionary construction followed by return
        if re.search(r"\w+_dict\s*=\s*{", source) and re.search(r"return\s+\w+_dict", source):
            # Found a pattern like: user_dict = {...}; return user_dict
            if not re.search(r"return\s+\w+Response\(", source):
                return True

        return False

    def _has_manual_json_response(self, source: str) -> bool:
        """Check if the function creates manual JSON responses."""
        json_patterns = [
            r"JSONResponse\s*\(",
            r"\.json\(\)",
            r"json\.dumps\(",
        ]

        return any(re.search(pattern, source) for pattern in json_patterns)


class TestAPIContracts:
    """Test suite for API contract compliance."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return TestClient(app)

    @pytest.fixture
    def admin_headers(self):
        """Create admin authentication headers."""
        # For contract tests, we'll use a mock token
        # In real tests, this would create an actual admin user
        return {"Authorization": "Bearer mock_admin_token"}

    def test_no_contract_violations(self):
        """Test that there are no contract violations in the codebase."""
        analyzer = APIContractAnalyzer(app)
        violations = analyzer.analyze_all_routes()

        if violations:
            violation_messages = "\n".join(str(v) for v in violations)
            pytest.fail(f"Found {len(violations)} contract violations:\n{violation_messages}")

    def test_monitoring_endpoints_use_response_models(self, client, admin_headers):
        """Test that all monitoring endpoints use proper response models."""
        monitoring_endpoints = [
            ("/api/monitoring/dashboard", "get"),
            ("/api/monitoring/logs", "get"),
            ("/api/monitoring/celery-tasks", "get"),
            ("/api/monitoring/redis-status", "get"),
            ("/api/monitoring/performance", "get"),
        ]

        for endpoint, method in monitoring_endpoints:
            response = getattr(client, method)(endpoint, headers=admin_headers)

            # Check that response is valid JSON
            assert response.headers.get("content-type") == "application/json"

            # Check that response can be parsed
            data = response.json()
            assert isinstance(data, dict)

            # Check common fields that should be in response models
            if response.status_code == 200:
                # Most monitoring responses should have a timestamp
                if "timestamp" in data:
                    assert isinstance(data["timestamp"], str)

    def test_analytics_endpoints_use_response_models(self, client, admin_headers):
        """Test that all analytics endpoints use proper response models."""
        analytics_endpoints = [
            ("/api/analytics/search/search-trends", "get"),
            ("/api/analytics/search/popular-searches", "get"),
            ("/api/analytics/search/referrers", "get"),
            ("/api/analytics/search/search-analytics-summary", "get"),
            ("/api/analytics/search/conversion-metrics", "get"),
            ("/api/analytics/search/search-performance", "get"),
        ]

        for endpoint, method in analytics_endpoints:
            response = getattr(client, method)(endpoint, headers=admin_headers)

            # All analytics endpoints should return JSON
            assert response.headers.get("content-type") == "application/json"

            # Verify response structure
            data = response.json()

            # Analytics responses should never be raw lists at the top level
            # They should be wrapped in a response model
            if isinstance(data, list) and not endpoint.endswith("/search-trends"):
                pytest.fail(f"{endpoint} returns a raw list instead of a response model")

    def test_paginated_endpoints_use_paginated_response(self, client, admin_headers):
        """Test that paginated endpoints use PaginatedResponse model."""
        # These endpoints should use PaginatedResponse
        paginated_endpoints = [
            "/api/bookings",
            "/api/instructors",
            "/api/services",
        ]

        for endpoint in paginated_endpoints:
            response = client.get(endpoint, headers=admin_headers)

            if response.status_code == 200:
                data = response.json()

                # Check for PaginatedResponse structure
                assert "items" in data, f"{endpoint} missing 'items' field"
                assert "total" in data, f"{endpoint} missing 'total' field"
                assert "page" in data, f"{endpoint} missing 'page' field"
                assert "page_size" in data, f"{endpoint} missing 'page_size' field"
                assert "pages" in data, f"{endpoint} missing 'pages' field"

    def test_error_responses_are_consistent(self, client):
        """Test that error responses follow a consistent format."""
        # Try to access protected endpoints without auth
        protected_endpoints = [
            "/api/monitoring/dashboard",
            "/api/analytics/search/search-trends",
            "/api/v1/auth/me",
        ]

        for endpoint in protected_endpoints:
            response = client.get(endpoint)

            if response.status_code in [401, 403]:
                data = response.json()

                # Error responses should have 'detail' field
                assert "detail" in data, f"{endpoint} error response missing 'detail' field"

                # Should not have random error fields
                assert "error" not in data, f"{endpoint} has non-standard 'error' field"
                assert "message" not in data, f"{endpoint} has non-standard 'message' field"

    def test_response_field_naming_consistency(self, client, admin_headers):
        """Test that response fields follow consistent naming conventions."""
        # Test a sample of endpoints
        test_endpoints = [
            "/api/metrics/health",
            "/api/health",
            "/api/health/detailed",
        ]

        for endpoint in test_endpoints:
            response = client.get(endpoint, headers=admin_headers)

            if response.status_code == 200:
                data = response.json()

                # Check for consistent timestamp fields
                if "timestamp" in data:
                    # Should be ISO format string
                    assert isinstance(data["timestamp"], str)
                    assert "T" in data["timestamp"]  # ISO format

                # Check that we don't mix camelCase and snake_case
                self._check_field_naming_convention(data, endpoint)

    def _check_field_naming_convention(self, data: Any, context: str, path: str = "") -> None:
        """Recursively check that all fields use snake_case."""
        if isinstance(data, dict):
            for key, value in data.items():
                # Check if key is snake_case
                if not self._is_snake_case(key):
                    pytest.fail(f"{context}: Field '{path}.{key}' is not snake_case")

                # Recurse into nested structures
                self._check_field_naming_convention(value, context, f"{path}.{key}")
        elif isinstance(data, list) and data:
            # Check first element of list
            self._check_field_naming_convention(data[0], context, f"{path}[0]")

    def _is_snake_case(self, text: str) -> bool:
        """Check if a string is in snake_case format."""
        # Allow uppercase for acronyms like "HTTP" in "HTTP_200"
        return bool(re.match(r"^[a-z]+(_[a-z0-9]+)*$", text)) or bool(re.match(r"^[A-Z]+(_[0-9]+)?$", text))


class TestResponseModelCoverage:
    """Test that all response models are actually used."""

    def test_all_response_models_are_used(self):
        """Ensure that defined response models are actually used in endpoints."""
        # Get all response model classes
        response_models = self._find_response_models()

        # Get all used response models from routes
        used_models = self._find_used_response_models()

        # Find unused models
        unused_models = response_models - used_models

        # Some models might be base classes, used indirectly, or part of larger response objects
        allowed_unused = {
            "BaseModel",
            "PaginatedResponse",
            "BaseResponse",
            # Analytics and monitoring models (used in complex response objects)
            "UserBreakdown",
            "RequestMetrics",
            "SearchMetadata",
            "ServiceMetrics",
            "BatchOperationResult",
            "SearchReferrer",
            "SlowRequestInfo",
            "PerformanceRecommendation",
            "DailySearchTrend",
            "AlertDetail",
            "SearchEffectiveness",
            "ProblematicQuery",
            "MemoryMetrics",
            "SearchResult",
            "SlowQueryInfo",
            "PopularSearch",
            "AlertInfo",
            "GuestEngagement",
            "DailyAlertCount",
            "ResultDistribution",
            "GuestConversionMetrics",
            "SearchTypeMetrics",
            "DatabasePoolStatus",
            "CacheHealthStatus",
            "DateRange",
            "LiveAlertItem",
            "ServiceOffering",
            "ComponentHealth",
            "ErrorDetail",
            "InstructorInfo",
            "PerformanceMetrics",
            "ConversionBehavior",
            "SearchTotals",
            # Standard response models
            "ErrorResponse",
            "DeleteResponse",
            "HealthResponse",
            "MetricsResponse",
            "HealthLiteResponse",
            "RootResponse",
            # Privacy models (used in privacy endpoints)
            "PrivacyRetentionResponse",
            # Message models (used in composition and SSE)
            "MessageNotificationResponse",  # Used in notification system
            "MessageSenderResponse",  # Used in MessageResponse
            "MessageResponse",  # Used in SendMessageResponse and MessagesHistoryResponse
            # Search candidates (nested in response wrappers)
            "CandidateCategoryTrend",
            "CandidateServiceQuery",
            "CandidateTopService",
            # Nested strict response helpers
            "CategoryWithServices",
            "NeighborhoodItem",
            "TopCategoryItem",
            "TopCategoryServiceItem",
            "ServiceSearchMetadata",
            "AllServicesMetadata",
            "CategoryServiceDetail",
            "TopServicesMetadata",
            # Strict request companion declared in responses module
            "BetaSettingsUpdateRequest",
        }
        unused_models = unused_models - allowed_unused

        if unused_models:
            pytest.fail(f"Found unused response models: {', '.join(unused_models)}")

    def _find_response_models(self) -> Set[str]:
        """Find all response model classes in the schemas directory."""
        models = set()
        schemas_path = Path("app/schemas")

        for py_file in schemas_path.rglob("*_responses.py"):
            with open(py_file) as f:
                tree = ast.parse(f.read())

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    # Check if it inherits from BaseModel
                    for base in node.bases:
                        if isinstance(base, ast.Name) and "Model" in base.id:
                            models.add(node.name)
                        elif isinstance(base, ast.Attribute) and "Model" in base.attr:
                            models.add(node.name)

        return models

    def _find_used_response_models(self) -> Set[str]:
        """Find all response models actually used in routes."""
        used = set()
        routes_path = Path("app/routes")

        for py_file in routes_path.rglob("*.py"):
            with open(py_file) as f:
                content = f.read()

            # Find response_model= declarations
            pattern = r"response_model=(\w+)"
            matches = re.findall(pattern, content)
            used.update(matches)

            # Also find List[Model] patterns
            pattern = r"response_model=List\[(\w+)\]"
            matches = re.findall(pattern, content)
            used.update(matches)

        return used


class TestEndpointResponseValidation:
    """Runtime validation of endpoint responses."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return TestClient(app)

    @pytest.fixture
    def admin_headers(self):
        """Create admin authentication headers."""
        # For contract tests, we'll use a mock token
        # In real tests, this would create an actual admin user
        return {"Authorization": "Bearer mock_admin_token"}

    def test_response_matches_declared_model(self, client, admin_headers):
        """Test that actual responses match their declared response models."""
        # This test makes actual API calls and validates responses
        test_cases = [
            ("/api/health", None),  # Public endpoint
            ("/api/metrics/health", admin_headers),
            ("/api/metrics/performance", admin_headers),
        ]

        for endpoint, headers in test_cases:
            response = client.get(endpoint, headers=headers)

            if response.status_code == 200:
                # The response should be valid according to the schema
                # FastAPI automatically validates this, but we can double-check
                data = response.json()
                assert data is not None

                # Specific checks based on endpoint
                if endpoint == "/api/health":
                    assert "status" in data
                    assert "timestamp" in data
                elif endpoint == "/api/metrics/performance":
                    assert "endpoint_metrics" in data
                    assert "database_metrics" in data


if __name__ == "__main__":
    # Can be run standalone to check for violations
    analyzer = APIContractAnalyzer(app)
    violations = analyzer.analyze_all_routes()

    if violations:
        print(f"Found {len(violations)} contract violations:")
        for v in violations:
            print(f"  - {v}")
    else:
        print("Found 0 contract violations")
