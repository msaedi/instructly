#!/usr/bin/env python3
"""
RBAC Permission Testing Script
Tests all permission scenarios for student, instructor, and admin roles
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Dict, Optional

# Disable rate limiting for testing
os.environ["rate_limit_enabled"] = "false"

import httpx
from colorama import Fore, init

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

# Initialize colorama for colored output
init(autoreset=True)

# Test configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
TEST_PASSWORD = "Test1234"

# Test users based on seed data
TEST_USERS = {
    "student": {"email": "john.smith@example.com", "password": TEST_PASSWORD, "expected_role": "student"},
    "instructor": {"email": "sarah.chen@example.com", "password": TEST_PASSWORD, "expected_role": "instructor"},
    "admin": {"email": "admin@instainstru.com", "password": TEST_PASSWORD, "expected_role": "admin"},
}

# Permission test matrix
PERMISSION_TESTS = [
    # (endpoint, method, test_name, student_expected, instructor_expected, admin_expected)
    # Analytics endpoints
    ("search-analytics/search-trends", "GET", "View system analytics", 403, 403, 200),
    ("search-analytics/popular-searches", "GET", "View popular searches", 200, 200, 200),  # All authenticated users
    # Booking endpoints
    ("bookings/check-availability", "POST", "Check availability", 200, 200, 200),  # All can check
    ("bookings", "POST", "Create booking", 200, 403, 200),  # Students and admin can book
    ("bookings/123/complete", "POST", "Complete booking", 403, 200, 200),  # Instructors and admin
    ("bookings/send-reminders", "POST", "Send booking reminders", 403, 403, 200),  # Admin only
    # Availability endpoints
    ("availability/week", "GET", "View availability", 200, 200, 200),  # All can view
    ("availability/slots", "POST", "Manage availability", 403, 200, 200),  # Instructors and admin
    # User management
    ("users", "GET", "View all users", 403, 403, 200),  # Admin only
    ("auth/me", "GET", "View own profile", 200, 200, 200),  # All authenticated
    # Instructor endpoints
    ("instructors", "GET", "View instructors", 200, 200, 200),  # All can view
    ("instructor/profile", "PUT", "Manage instructor profile", 403, 200, 200),  # Instructors and admin
]


class RBACTester:
    def __init__(self):
        self.client = httpx.AsyncClient(base_url=API_BASE_URL, timeout=30.0)
        self.tokens: Dict[str, str] = {}
        self.results = []

    async def login_user(self, role: str) -> Optional[str]:
        """Login a test user and return their token"""
        user_data = TEST_USERS[role]
        try:
            response = await self.client.post(
                "/auth/login",
                data={
                    "username": user_data["email"],  # API expects username field but we use email
                    "password": user_data["password"],
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if response.status_code == 200:
                data = response.json()
                self.tokens[role] = data["access_token"]
                print(f"{Fore.GREEN}✓ Logged in as {role}: {user_data['email']}")

                # Get user info with permissions
                me_response = await self.client.get(
                    "/auth/me", headers={"Authorization": f"Bearer {data['access_token']}"}
                )

                if me_response.status_code == 200:
                    user_data = me_response.json()
                    if "permissions" in user_data:
                        print(f"  Permissions: {len(user_data['permissions'])} total")
                        # Show first few permissions
                        for perm in user_data["permissions"][:5]:
                            print(f"    - {perm}")
                        if len(user_data["permissions"]) > 5:
                            print(f"    ... and {len(user_data['permissions']) - 5} more")

                return data["access_token"]
            else:
                print(f"{Fore.RED}✗ Failed to login {role}: {response.status_code}")
                print(f"  Response: {response.text}")
                return None
        except Exception as e:
            print(f"{Fore.RED}✗ Error logging in {role}: {str(e)}")
            return None

    async def test_endpoint(self, endpoint: str, method: str, role: str, token: str) -> int:
        """Test an endpoint with a given role's token"""
        headers = {"Authorization": f"Bearer {token}"}

        # Add request body for POST endpoints
        json_data = None
        if endpoint == "bookings/check-availability" and method == "POST":
            json_data = {
                "instructor_id": 1,
                "booking_date": "2025-08-01",
                "start_time": "14:00:00",
                "end_time": "15:00:00",
                "instructor_service_id": 1,
            }
        elif endpoint == "bookings" and method == "POST":
            json_data = {
                "instructor_id": 1,
                "instructor_service_id": 1,
                "booking_date": "2025-08-01",
                "start_time": "14:00:00",
                "selected_duration": 60,
                "service_area": "Manhattan",
            }
        elif endpoint == "availability/slots" and method == "POST":
            json_data = {"date": "2025-08-01", "start_time": "09:00:00", "end_time": "17:00:00"}

        try:
            if method == "GET":
                response = await self.client.get(f"/{endpoint}", headers=headers)
            elif method == "POST":
                response = await self.client.post(f"/{endpoint}", headers=headers, json=json_data)
            elif method == "PUT":
                response = await self.client.put(f"/{endpoint}", headers=headers, json={})
            else:
                return 405  # Method not allowed

            return response.status_code
        except Exception as e:
            print(f"{Fore.YELLOW}  Warning: Error testing {endpoint}: {str(e)}")
            return 500

    async def run_permission_tests(self):
        """Run all permission tests"""
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"{Fore.CYAN}Running RBAC Permission Tests")
        print(f"{Fore.CYAN}{'='*80}\n")

        # First, login all users
        print(f"{Fore.YELLOW}1. Logging in test users...")
        for role in TEST_USERS:
            await self.login_user(role)
        print()

        # Check if all users logged in successfully
        if len(self.tokens) != len(TEST_USERS):
            print(f"{Fore.RED}Not all users logged in successfully. Aborting tests.")
            return

        # Run permission tests
        print(f"{Fore.YELLOW}2. Testing endpoint permissions...\n")

        # Print table header
        print(f"{'Endpoint':<40} {'Test':<30} {'Student':<10} {'Instructor':<12} {'Admin':<10}")
        print(f"{'-'*102}")

        for endpoint, method, test_name, student_exp, instructor_exp, admin_exp in PERMISSION_TESTS:
            results_row = {"endpoint": endpoint, "method": method, "test_name": test_name, "results": {}}

            row_output = f"{endpoint:<40} {test_name:<30}"

            # Test each role
            for role, expected in [("student", student_exp), ("instructor", instructor_exp), ("admin", admin_exp)]:
                if role in self.tokens:
                    actual = await self.test_endpoint(endpoint, method, role, self.tokens[role])
                    results_row["results"][role] = {
                        "expected": expected,
                        "actual": actual,
                        "passed": actual == expected,
                    }

                    # Format output
                    if actual == expected:
                        status = f"{Fore.GREEN}✓ {actual}"
                    else:
                        status = f"{Fore.RED}✗ {actual} (exp: {expected})"

                    if role == "student":
                        row_output += f" {status:<10}"
                    elif role == "instructor":
                        row_output += f" {status:<12}"
                    else:
                        row_output += f" {status:<10}"

            print(row_output)
            self.results.append(results_row)

        # Print summary
        self.print_summary()

    def print_summary(self):
        """Print test summary"""
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"{Fore.CYAN}Test Summary")
        print(f"{Fore.CYAN}{'='*80}\n")

        total_tests = 0
        passed_tests = 0

        for result in self.results:
            for role, test_result in result["results"].items():
                total_tests += 1
                if test_result["passed"]:
                    passed_tests += 1

        pass_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0

        if pass_rate == 100:
            print(f"{Fore.GREEN}✓ All tests passed! ({passed_tests}/{total_tests})")
        else:
            print(f"{Fore.YELLOW}⚠ {passed_tests}/{total_tests} tests passed ({pass_rate:.1f}%)")

            # Show failures
            print(f"\n{Fore.RED}Failed tests:")
            for result in self.results:
                for role, test_result in result["results"].items():
                    if not test_result["passed"]:
                        print(
                            f"  - {result['test_name']} for {role}: "
                            f"got {test_result['actual']}, expected {test_result['expected']}"
                        )

    async def test_permission_details(self):
        """Test detailed permission checking"""
        print(f"\n{Fore.YELLOW}3. Testing permission details...\n")

        # Test that each role has the correct permissions
        for role in ["student", "instructor", "admin"]:
            if role not in self.tokens:
                continue

            response = await self.client.get("/users/me", headers={"Authorization": f"Bearer {self.tokens[role]}"})

            if response.status_code == 200:
                user_data = response.json()
                permissions = user_data.get("permissions", [])

                print(f"{Fore.CYAN}{role.upper()} permissions ({len(permissions)} total):")

                # Check key permissions
                key_permissions = {
                    "student": ["create_bookings", "view_instructors", "view_instructor_availability"],
                    "instructor": ["manage_availability", "complete_bookings", "manage_instructor_profile"],
                    "admin": ["manage_users", "view_system_analytics", "manage_all_bookings"],
                }

                for perm in key_permissions.get(role, []):
                    if perm in permissions:
                        print(f"  {Fore.GREEN}✓ Has {perm}")
                    else:
                        print(f"  {Fore.RED}✗ Missing {perm}")

                # Check that roles don't have permissions they shouldn't
                forbidden_permissions = {
                    "student": ["manage_availability", "complete_bookings", "view_system_analytics"],
                    "instructor": ["create_bookings", "view_system_analytics", "manage_users"],
                    "admin": [],  # Admin should have everything
                }

                print(f"\n  Checking forbidden permissions:")
                for perm in forbidden_permissions.get(role, []):
                    if perm not in permissions:
                        print(f"  {Fore.GREEN}✓ Correctly lacks {perm}")
                    else:
                        print(f"  {Fore.RED}✗ Incorrectly has {perm}")
                print()

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()


async def main():
    """Run all RBAC tests"""
    # Check if backend is running
    try:
        # Health endpoint is at /health, not under /api
        test_response = httpx.get("http://localhost:8000/health", timeout=5.0)
        if test_response.status_code != 200:
            print(f"{Fore.RED}Backend is not healthy. Please start it first.")
            return
    except:
        print(f"{Fore.RED}Cannot connect to backend at http://localhost:8000")
        print(f"Please ensure the backend is running: uvicorn app.main:app --reload")
        return

    tester = RBACTester()
    try:
        await tester.run_permission_tests()
        await tester.test_permission_details()
    finally:
        await tester.close()

    print(f"\n{Fore.CYAN}Test complete! Check the results above.")
    print(f"\n{Fore.YELLOW}Next steps:")
    print(f"1. Fix any failing tests")
    print(f"2. Test frontend permission visibility")
    print(f"3. Create automated test suite")


if __name__ == "__main__":
    asyncio.run(main())
