"""
Privacy Auditor Module - Core privacy compliance testing for InstaInstru.

This module provides comprehensive privacy auditing capabilities that can be used by:
1. GitHub Actions (CI/CD pipeline) - Pre-deployment validation
2. Celery Beat (Production) - Continuous monitoring
3. Local development - Developer testing

The auditor ensures that privacy rules are enforced across all API endpoints,
preventing exposure of sensitive data like full last names, emails, phone numbers, etc.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import logging
from pathlib import Path
import re
import time
import traceback
from typing import Any, Dict, List, Optional, Tuple, cast

import httpx
import yaml  # type: ignore[import-untyped]  # third-party package lacks typing stubs

logger = logging.getLogger(__name__)


class ViolationSeverity(str, Enum):
    """Severity levels for privacy violations."""

    HIGH = "HIGH"  # Exposes PII that should never be visible
    MEDIUM = "MEDIUM"  # Incorrect format but not fully exposed
    LOW = "LOW"  # Minor issues, formatting problems
    INFO = "INFO"  # Informational, not a violation


class EndpointCategory(str, Enum):
    """Categories of endpoints for testing."""

    PUBLIC = "public"
    AUTHENTICATED = "authenticated"
    ADMIN = "admin"
    INSTRUCTOR = "instructor"
    STUDENT = "student"


@dataclass
class PrivacyRule:
    """A single privacy rule to check."""

    name: str
    description: str
    forbidden_fields: List[str] = field(default_factory=list)
    allowed_fields: List[str] = field(default_factory=list)
    field_format: Dict[str, str] = field(
        default_factory=dict
    )  # e.g., {"name": "first_name last_initial"}
    severity: ViolationSeverity = ViolationSeverity.HIGH


@dataclass
class Violation:
    """A privacy violation found during audit."""

    endpoint: str
    method: str
    violation_type: str
    message: str
    severity: ViolationSeverity
    field_path: str = ""  # JSON path to the violating field
    example_value: Any = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EndpointTest:
    """Test case for an endpoint."""

    path: str
    method: str
    category: EndpointCategory
    auth_required: bool = False
    test_as_users: List[str] = field(default_factory=list)  # Email addresses to test as
    params: Dict[str, Any] = field(default_factory=dict)
    body: Optional[Dict[str, Any]] = None
    expected_status: int = 200


@dataclass
class AuditResult:
    """Complete audit result."""

    summary: Dict[str, Any]
    violations: List[Violation]
    endpoints_tested: List[EndpointTest]
    execution_time: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    coverage: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "summary": self.summary,
            "violations": [asdict(v) for v in self.violations],
            "endpoints_tested": [asdict(e) for e in self.endpoints_tested],
            "execution_time": self.execution_time,
            "timestamp": self.timestamp.isoformat(),
            "coverage": self.coverage,
        }


class PrivacyAuditor:
    """
    Core privacy auditor that tests API endpoints for compliance.

    This auditor can be used in multiple contexts:
    - CI/CD pipelines (GitHub Actions)
    - Production monitoring (Celery Beat)
    - Local development testing
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        test_mode: bool = True,
        config_file: Optional[str] = None,
        verbose: bool = False,
    ):
        """
        Initialize the privacy auditor.

        Args:
            base_url: Base URL of the API to test
            test_mode: If True, uses test data. If False, production-safe tests only
            config_file: Optional path to YAML configuration file
            verbose: Enable verbose logging
        """
        self.base_url = base_url.rstrip("/")
        self.test_mode = test_mode
        self.verbose = verbose
        self.violations: List[Violation] = []
        self.config: Dict[str, Any] = self._load_config(config_file)
        self.filter_category: Optional[str] = None
        self.filter_endpoint: Optional[str] = None
        self._setup_logging()

        # Test users (only used in test_mode)
        self.test_users = {
            "instructors": ["sarah.chen@example.com", "michael.rodriguez@example.com"],
            "students": ["john.smith@example.com", "emma.johnson@example.com"],
        }

        # Authentication tokens cache
        self.auth_tokens: Dict[str, str] = {}

        # HTTP client with connection pooling
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0, follow_redirects=True)

    def _load_config(self, config_file: Optional[str]) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        default_config: Dict[str, Any] = {
            "rules": {
                "public_endpoints": {
                    "forbidden_fields": ["last_name", "email", "phone", "zip_code"],
                    "allowed_fields": ["id", "first_name", "last_initial"],
                },
                "student_view_instructor": {
                    "forbidden_fields": ["last_name", "email", "phone", "zip_code"],
                    "name_format": "first_name last_initial",
                },
                "instructor_self_view": {"allowed_fields": "*"},
            },
            "skip_endpoints": ["/health", "/metrics", "/docs", "/openapi.json", "/redoc"],
            "timeout": 300,  # 5 minutes max
        }

        if config_file and Path(config_file).exists():
            with open(config_file, "r") as f:
                user_config = cast(Dict[str, Any], yaml.safe_load(f) or {})
                # Merge with defaults
                default_config.update(user_config)

        return default_config

    def _setup_logging(self) -> None:
        """Configure logging based on verbosity."""
        level = logging.DEBUG if self.verbose else logging.INFO
        logging.basicConfig(
            level=level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    async def _authenticate_user(self, email: str, password: str = "Test1234") -> Optional[str]:
        """Authenticate a user and return their token."""
        if email in self.auth_tokens:
            return self.auth_tokens[email]

        try:
            response = await self.client.post(
                "/auth/login", data={"username": email, "password": password}
            )
            if response.status_code == 200:
                data = response.json()
                token = cast(Optional[str], data.get("access_token"))
                if token is not None:
                    self.auth_tokens[email] = token
                return token
        except Exception as e:
            logger.error(f"Failed to authenticate {email}: {e}")

        return None

    def _check_field_recursively(
        self, data: Any, field_name: str, path: str = ""
    ) -> List[Tuple[str, Any]]:
        """
        Recursively check for a field in nested data structures.

        Returns list of (path, value) tuples where field was found.
        """
        findings: List[Tuple[str, Any]] = []

        if isinstance(data, dict):
            for key, value in data.items():
                current_path = f"{path}.{key}" if path else key
                if key == field_name:
                    findings.append((current_path, value))
                findings.extend(self._check_field_recursively(value, field_name, current_path))
        elif isinstance(data, list):
            for i, item in enumerate(data):
                current_path = f"{path}[{i}]"
                findings.extend(self._check_field_recursively(item, field_name, current_path))

        return findings

    def _check_privacy_violations(
        self, data: Any, rules: PrivacyRule, endpoint: str, method: str
    ) -> List[Violation]:
        """Check data against privacy rules and return violations."""
        violations: List[Violation] = []

        # Check for forbidden fields
        for field_name in rules.forbidden_fields:
            findings = self._check_field_recursively(data, field_name)
            for path, value in findings:
                violations.append(
                    Violation(
                        endpoint=endpoint,
                        method=method,
                        violation_type="forbidden_field",
                        message=f"Field '{field_name}' should not be exposed",
                        severity=rules.severity,
                        field_path=path,
                        example_value=value,
                    )
                )

        # Check field formats (e.g., name should be "FirstName L.")
        for field_name, expected_format in rules.field_format.items():
            findings = self._check_field_recursively(data, field_name)
            for path, value in findings:
                if not self._matches_format(value, expected_format):
                    violations.append(
                        Violation(
                            endpoint=endpoint,
                            method=method,
                            violation_type="incorrect_format",
                            message=f"Field '{field_name}' has incorrect format. Expected: {expected_format}",
                            severity=ViolationSeverity.MEDIUM,
                            field_path=path,
                            example_value=value,
                        )
                    )

        return violations

    def _matches_format(self, value: Any, format_spec: str) -> bool:
        """Check if a value matches the expected format."""
        if format_spec == "first_name last_initial":
            # Should be like "John D." or "Sarah C."
            pattern = r"^[A-Za-z]+\s[A-Z]\.$"
            return bool(re.match(pattern, str(value)))
        return True

    async def _test_endpoint(
        self, endpoint: EndpointTest, as_user: Optional[str] = None
    ) -> List[Violation]:
        """Test a single endpoint for privacy violations."""
        violations: List[Violation] = []
        headers: Dict[str, str] = {}

        # Add authentication if required
        if endpoint.auth_required and as_user:
            token = await self._authenticate_user(as_user)
            if token:
                headers["Authorization"] = f"Bearer {token}"
            else:
                logger.warning(f"Failed to authenticate as {as_user}")
                return violations

        try:
            # Make the HTTP request
            if endpoint.method.upper() == "GET":
                response = await self.client.get(
                    endpoint.path, params=endpoint.params, headers=headers
                )
            elif endpoint.method.upper() == "POST":
                response = await self.client.post(
                    endpoint.path, json=endpoint.body, headers=headers
                )
            else:
                # Add other methods as needed
                response = await self.client.request(
                    endpoint.method,
                    endpoint.path,
                    params=endpoint.params,
                    json=endpoint.body,
                    headers=headers,
                )

            # Check response
            if response.status_code == endpoint.expected_status:
                try:
                    data = response.json()

                    # Determine which rules to apply
                    if endpoint.category == EndpointCategory.PUBLIC:
                        rules = PrivacyRule(
                            name="public_endpoints",
                            description="Public endpoint privacy rules",
                            forbidden_fields=self.config["rules"]["public_endpoints"][
                                "forbidden_fields"
                            ],
                            allowed_fields=self.config["rules"]["public_endpoints"][
                                "allowed_fields"
                            ],
                        )
                    elif (
                        endpoint.category == EndpointCategory.STUDENT
                        and as_user in self.test_users["students"]
                    ):
                        rules = PrivacyRule(
                            name="student_view",
                            description="Student viewing data",
                            forbidden_fields=self.config["rules"]["student_view_instructor"][
                                "forbidden_fields"
                            ],
                            field_format={"instructor_name": "first_name last_initial"},
                        )
                    else:
                        # Default rules
                        rules = PrivacyRule(
                            name="default",
                            description="Default privacy rules",
                            forbidden_fields=["password", "password_hash"],
                        )

                    # Check for violations
                    endpoint_violations = self._check_privacy_violations(
                        data, rules, endpoint.path, endpoint.method
                    )
                    violations.extend(endpoint_violations)

                except json.JSONDecodeError:
                    # Response is not JSON, skip privacy checks
                    pass

        except Exception as e:
            logger.error(f"Error testing endpoint {endpoint.path}: {e}")
            if self.verbose:
                traceback.print_exc()

        return violations

    def _discover_endpoints(self) -> List[EndpointTest]:
        """
        Discover endpoints to test.

        In a real implementation, this would dynamically discover from FastAPI app.
        For now, we'll define critical endpoints manually.
        """
        # Check for filters
        filter_category = self.filter_category
        filter_endpoint = self.filter_endpoint

        endpoints: List[EndpointTest] = [
            # Public endpoints
            EndpointTest(
                path="/api/search/instructors",
                method="GET",
                category=EndpointCategory.PUBLIC,
                params={"q": "piano", "limit": 5},
            ),
            EndpointTest(
                path="/services/search",
                method="GET",
                category=EndpointCategory.PUBLIC,
                params={"q": "yoga"},
            ),
            EndpointTest(
                path="/api/public/instructors/01J5TESTINSTR0000000000001/availability",
                method="GET",
                category=EndpointCategory.PUBLIC,
                params={"start_date": "2025-01-20", "end_date": "2025-01-27"},
            ),
            EndpointTest(
                path="/instructors/",
                method="GET",
                category=EndpointCategory.PUBLIC,
                params={"service_catalog_id": 1, "limit": 10},
            ),
            # Authenticated student endpoints
            EndpointTest(
                path="/api/bookings",
                method="GET",
                category=EndpointCategory.STUDENT,
                auth_required=True,
                test_as_users=["john.smith@example.com"],
            ),
            EndpointTest(
                path="/api/bookings/1",
                method="GET",
                category=EndpointCategory.STUDENT,
                auth_required=True,
                test_as_users=["john.smith@example.com"],
            ),
            # Authenticated instructor endpoints
            EndpointTest(
                path="/api/instructor/profile",
                method="GET",
                category=EndpointCategory.INSTRUCTOR,
                auth_required=True,
                test_as_users=["sarah.chen@example.com"],
            ),
        ]

        # Apply category filter if specified
        if filter_category:
            category_map = {
                "public": EndpointCategory.PUBLIC,
                "auth": EndpointCategory.STUDENT,  # Map auth to STUDENT
                "admin": EndpointCategory.ADMIN,
            }
            if filter_category in category_map:
                target_category = category_map[filter_category]
                endpoints = [e for e in endpoints if e.category == target_category]

        # Apply endpoint filter if specified
        if filter_endpoint:
            endpoints = [e for e in endpoints if filter_endpoint in e.path]

        # Filter out skipped endpoints
        skip_patterns = self.config.get("skip_endpoints", [])
        filtered: List[EndpointTest] = []
        for endpoint in endpoints:
            skip = False
            for pattern in skip_patterns:
                if pattern in endpoint.path:
                    skip = True
                    break
            if not skip:
                filtered.append(endpoint)

        return filtered

    async def audit(self) -> AuditResult:
        """
        Run the complete privacy audit.

        Returns:
            AuditResult with all findings
        """
        start_time = time.time()
        self.violations = []

        # Discover endpoints
        endpoints = self._discover_endpoints()
        logger.info(f"Testing {len(endpoints)} endpoints")

        # Test each endpoint
        for endpoint in endpoints:
            if endpoint.test_as_users:
                # Test with specific users
                for user in endpoint.test_as_users:
                    violations = await self._test_endpoint(endpoint, user)
                    self.violations.extend(violations)
            else:
                # Test without authentication (public endpoint)
                violations = await self._test_endpoint(endpoint)
                self.violations.extend(violations)

        # Calculate coverage
        total_endpoints = len(endpoints)
        public_tested = len([e for e in endpoints if e.category == EndpointCategory.PUBLIC])
        auth_tested = len([e for e in endpoints if e.auth_required])

        # Build result
        execution_time = time.time() - start_time
        result = AuditResult(
            summary={
                "total_endpoints": total_endpoints,
                "passed": total_endpoints - len(self.violations),
                "failed": len(self.violations) if self.violations else 0,
                "execution_time": f"{execution_time:.2f}s",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            violations=self.violations,
            endpoints_tested=endpoints,
            execution_time=execution_time,
            coverage={
                "public_endpoints": f"{public_tested}/{public_tested}",
                "authenticated_endpoints": f"{auth_tested}/{auth_tested}",
                "total": f"{total_endpoints}/{total_endpoints}",
            },
        )

        return result

    async def close(self) -> None:
        """Clean up resources."""
        await self.client.aclose()

    def generate_report(self, result: AuditResult, format: str = "json") -> str:
        """
        Generate a report in the specified format.

        Args:
            result: Audit result to report on
            format: Output format (json, markdown, html)

        Returns:
            Formatted report string
        """
        if format == "json":
            return json.dumps(result.to_dict(), indent=2, default=str)

        elif format == "markdown":
            report: List[str] = ["# Privacy Audit Report\n"]
            report.append(
                f"**Date**: {result.timestamp.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}\n"
            )
            report.append(f"**Execution Time**: {result.execution_time:.2f}s\n")
            report.append("\n## Summary\n")
            report.append(f"- Total Endpoints Tested: {result.summary['total_endpoints']}\n")
            report.append(f"- Passed: {result.summary['passed']}\n")
            report.append(f"- Failed: {result.summary['failed']}\n")

            if result.violations:
                report.append("\n## Violations Found\n")
                for v in result.violations:
                    report.append(f"\n### {v.severity} - {v.endpoint}\n")
                    report.append(f"- **Method**: {v.method}\n")
                    report.append(f"- **Issue**: {v.message}\n")
                    report.append(f"- **Field Path**: `{v.field_path}`\n")
                    if v.example_value:
                        report.append(f"- **Example**: `{v.example_value}`\n")
            else:
                report.append("\n✅ **No violations found!**\n")

            report.append("\n## Coverage\n")
            for category, coverage in result.coverage.items():
                report.append(f"- {category}: {coverage}\n")

            return "".join(report)

        else:
            raise ValueError(f"Unsupported format: {format}")


# Convenience function for running audit
async def run_privacy_audit(
    base_url: str = "http://localhost:8000",
    test_mode: bool = True,
    config_file: Optional[str] = None,
    verbose: bool = False,
    output_format: str = "json",
    filter_category: Optional[str] = None,
    filter_endpoint: Optional[str] = None,
) -> Tuple[AuditResult, str]:
    """
    Run a privacy audit and return results.

    Args:
        base_url: API base URL
        test_mode: Use test data
        config_file: Optional config file path
        verbose: Enable verbose output
        output_format: Report format (json, markdown)

    Returns:
        Tuple of (AuditResult, formatted_report)
    """
    auditor = PrivacyAuditor(
        base_url=base_url, test_mode=test_mode, config_file=config_file, verbose=verbose
    )

    # Store filters for use in audit
    auditor.filter_category = filter_category
    auditor.filter_endpoint = filter_endpoint

    try:
        result = await auditor.audit()
        report = auditor.generate_report(result, format=output_format)
        return result, report
    finally:
        await auditor.close()
