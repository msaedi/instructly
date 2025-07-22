#!/usr/bin/env python3
"""
Search Verification Report - Final verification that search functionality is working.
"""

import requests
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def test_search_api():
    """Test the search API with various queries."""
    base_url = "http://localhost:8000"

    console.print(
        Panel.fit(
            "[bold]Search API Verification Report[/bold]\n" "Testing the /api/search/instructors endpoint",
            title="InstaInstru Search Verification",
        )
    )

    # Test queries with expected results
    test_cases = [
        ("piano lessons", True),
        ("guitar lessons", True),
        ("math tutoring", True),
        ("data science", True),
        ("photography", True),
        ("yoga", True),
        ("programming", True),
        ("music", True),
        ("art", True),
        ("spanish", False),  # Expected no results
        ("cooking", False),  # Expected no results
        ("nonexistent service", False),  # Expected no results
    ]

    table = Table(title="Search API Test Results")
    table.add_column("Query", style="cyan")
    table.add_column("Results Found", style="green")
    table.add_column("Top Result", style="yellow")
    table.add_column("Match Score", style="magenta")
    table.add_column("Status", style="bold")

    total_tests = len(test_cases)
    passed_tests = 0

    for query, should_find_results in test_cases:
        try:
            # Make API request
            response = requests.get(f"{base_url}/api/search/instructors", params={"q": query}, timeout=10)

            if response.status_code == 200:
                data = response.json()
                total_found = data.get("total_found", 0)
                results = data.get("results", [])

                # Determine if test passed
                test_passed = (total_found > 0) == should_find_results

                if test_passed:
                    passed_tests += 1
                    status = "✅ PASS"
                else:
                    status = "❌ FAIL"

                # Get top result info
                if results:
                    top_result = results[0]
                    instructor_name = top_result.get("instructor", {}).get("name", "N/A")
                    service_name = top_result.get("service", {}).get("name", "N/A")
                    match_score = top_result.get("match_score", 0)
                    top_result_str = f"{instructor_name}: {service_name}"
                    score_str = f"{match_score:.1f}"
                else:
                    top_result_str = "No results"
                    score_str = "-"

                table.add_row(query, str(total_found), top_result_str, score_str, status)

            else:
                table.add_row(query, "API Error", f"Status: {response.status_code}", "-", "❌ FAIL")

        except requests.exceptions.RequestException as e:
            table.add_row(query, "Network Error", str(e)[:50], "-", "❌ FAIL")
        except Exception as e:
            table.add_row(query, "Error", str(e)[:50], "-", "❌ FAIL")

    console.print(table)

    # Summary
    console.print(f"\n[bold]Test Summary:[/bold]")
    console.print(f"Tests passed: [green]{passed_tests}/{total_tests}[/green]")

    if passed_tests == total_tests:
        console.print("\n🎉 [bold green]All tests passed! Search API is working correctly.[/bold green]")
    else:
        console.print(f"\n⚠️ [bold yellow]{total_tests - passed_tests} tests failed.[/bold yellow]")

    # Test complex queries
    console.print(f"\n[bold]Testing Complex Natural Language Queries:[/bold]")

    complex_queries = [
        "piano lessons under $100",
        "online math tutoring",
        "guitar lessons in-person",
        "data science over $100",
    ]

    for query in complex_queries:
        try:
            response = requests.get(f"{base_url}/api/search/instructors", params={"q": query}, timeout=10)
            if response.status_code == 200:
                data = response.json()
                total_found = data.get("total_found", 0)
                parsed = data.get("parsed", {})

                console.print(f"\n🔍 Query: '{query}'")
                console.print(f"  Results: {total_found}")
                console.print(
                    f"  Parsed constraints: price={parsed.get('price', {})}, location={parsed.get('location', {})}"
                )

                if data.get("results"):
                    result = data["results"][0]
                    instructor = result.get("instructor", {}).get("name", "Unknown")
                    service = result.get("service", {}).get("name", "Unknown")
                    offering = result.get("offering", {})
                    rate = offering.get("hourly_rate", 0)
                    console.print(f"  Top result: {instructor} - {service} (${rate}/hr)")
        except Exception as e:
            console.print(f"  Error: {e}")


if __name__ == "__main__":
    test_search_api()
