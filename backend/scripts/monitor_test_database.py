#!/usr/bin/env python3
"""
Monitor the test database before and after running tests.
"""

from datetime import datetime

import psycopg2
from rich.console import Console
from rich.table import Table

console = Console()

# Test database connection
TEST_DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "instainstru_test",
    "user": "postgres",
    "password": "postgres",
}


def check_service_catalog_state():
    """Check the current state of service_catalog table."""
    try:
        conn = psycopg2.connect(**TEST_DB_CONFIG)
        cur = conn.cursor()

        # Get counts
        cur.execute("SELECT COUNT(*), MAX(id) FROM service_catalog")
        total_count, max_id = cur.fetchone()

        # Get count by patterns
        cur.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE id <= 250) as seed_data,
                COUNT(*) FILTER (WHERE id > 250) as test_data,
                COUNT(*) FILTER (WHERE name LIKE 'Service %') as service_n_pattern,
                COUNT(*) FILTER (WHERE name LIKE '%Test%') as test_pattern
            FROM service_catalog
        """
        )
        seed_count, test_count, service_n_count, test_pattern_count = cur.fetchone()

        # Get recent services
        cur.execute(
            """
            SELECT id, name, created_at
            FROM service_catalog
            WHERE created_at > CURRENT_TIMESTAMP - INTERVAL '5 minutes'
            ORDER BY id DESC
            LIMIT 5
        """
        )
        recent_services = cur.fetchall()

        cur.close()
        conn.close()

        return {
            "timestamp": datetime.now(),
            "total_count": total_count,
            "max_id": max_id,
            "seed_count": seed_count,
            "test_count": test_count,
            "service_n_count": service_n_count,
            "test_pattern_count": test_pattern_count,
            "recent_services": recent_services,
        }

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return None


def display_state(state, title):
    """Display the database state."""
    console.print(f"\n[bold blue]{title}[/bold blue]")
    console.print(f"Timestamp: {state['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")

    # Summary table
    summary = Table(title="Service Catalog Summary")
    summary.add_column("Metric", style="cyan")
    summary.add_column("Count", style="green")

    summary.add_row("Total Services", str(state["total_count"]))
    summary.add_row("Maximum ID", str(state["max_id"]))
    summary.add_row("Seed Data (ID ≤ 250)", str(state["seed_count"]))
    summary.add_row("Test Data (ID > 250)", str(state["test_count"]))
    summary.add_row("'Service N' Pattern", str(state["service_n_count"]))
    summary.add_row("Contains 'Test'", str(state["test_pattern_count"]))

    console.print(summary)

    # Recent services
    if state["recent_services"]:
        console.print("\n[yellow]Recently created services (last 5 minutes):[/yellow]")
        for id, name, created_at in state["recent_services"]:
            console.print(f"  ID {id}: {name} (created: {created_at})")


def main():
    """Monitor database state."""
    console.print("[bold]Test Database Monitor[/bold]")
    console.print("=" * 60)

    # Check current state
    state = check_service_catalog_state()
    if state:
        display_state(state, "Current Database State")

        # Show what to expect
        console.print("\n[bold]Expected State After Reset:[/bold]")
        console.print("• Total Services: 250")
        console.print("• Maximum ID: 250")
        console.print("• Test Data: 0")

        console.print("\n[bold]To reset and check:[/bold]")
        console.print("1. Run: [cyan]python scripts/reset_and_seed_database_enhanced.py[/cyan]")
        console.print("2. Run: [cyan]python scripts/monitor_test_database.py[/cyan]")
        console.print("3. Run tests: [cyan]pytest tests/test_service_catalog_enhancements.py -v[/cyan]")
        console.print("4. Run: [cyan]python scripts/monitor_test_database.py[/cyan] again")


if __name__ == "__main__":
    main()
