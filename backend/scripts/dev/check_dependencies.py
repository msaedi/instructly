#!/usr/bin/env python3
# backend/scripts/check_dependencies.py
"""
Dependency checker to detect circular dependencies in the service layer.

Run this regularly to ensure clean architecture.
"""

import ast
from pathlib import Path
from typing import Dict, List, Set

import matplotlib.pyplot as plt
import networkx as nx


class DependencyAnalyzer(ast.NodeVisitor):
    """Extract imports from Python files."""

    def __init__(self, module_name: str):
        self.module_name = module_name
        self.imports = set()
        self.from_imports = set()

    def visit_Import(self, node):
        for alias in node.names:
            self.imports.add(alias.name)

    def visit_ImportFrom(self, node):
        if node.module:
            self.from_imports.add(node.module)


def analyze_service_dependencies(service_dir: Path) -> Dict[str, Set[str]]:
    """Analyze dependencies between service files."""
    dependencies = {}

    for py_file in service_dir.glob("*.py"):
        if py_file.name == "__init__.py":
            continue

        module_name = py_file.stem

        with open(py_file, "r") as f:
            try:
                tree = ast.parse(f.read())
                analyzer = DependencyAnalyzer(module_name)
                analyzer.visit(tree)

                # Filter for internal service dependencies
                internal_deps = set()
                for imp in analyzer.from_imports:
                    if "services." in imp:
                        # Extract service name
                        parts = imp.split(".")
                        if "services" in parts:
                            idx = parts.index("services")
                            if idx + 1 < len(parts):
                                dep_name = parts[idx + 1]
                                if dep_name != module_name:  # Don't include self
                                    internal_deps.add(dep_name)

                # Also check for direct service imports in __init__ methods
                with open(py_file, "r") as f2:
                    content = f2.read()
                    # Look for service dependencies in __init__
                    if "__init__" in content:
                        for service in [
                            "availability_service",
                            "booking_service",
                            "conflict_checker",
                            "slot_manager",
                            "notification_service",
                            "week_operation_service",
                            "bulk_operation_service",
                            "presentation_service",
                        ]:
                            if service in content and service != module_name:
                                # Extract the actual service module name
                                service_module = service.replace("_service", "")
                                if "service" not in service_module:
                                    service_module += "_service"
                                internal_deps.add(service_module)

                dependencies[module_name] = internal_deps

            except SyntaxError as e:
                print(f"Error parsing {py_file}: {e}")

    return dependencies


def find_circular_dependencies(dependencies: Dict[str, Set[str]]) -> List[List[str]]:
    """Find circular dependencies using graph analysis."""
    # Create directed graph
    G = nx.DiGraph()

    for module, deps in dependencies.items():
        for dep in deps:
            G.add_edge(module, dep)

    # Find cycles
    try:
        cycles = list(nx.simple_cycles(G))
        return cycles
    except:
        return []


def visualize_dependencies(dependencies: Dict[str, Set[str]], output_file: str = "service_dependencies.png"):
    """Create a visual graph of service dependencies."""
    G = nx.DiGraph()

    # Add all nodes first
    all_services = set(dependencies.keys())
    for deps in dependencies.values():
        all_services.update(deps)

    for service in all_services:
        G.add_node(service)

    # Add edges
    for module, deps in dependencies.items():
        for dep in deps:
            G.add_edge(module, dep)

    # Create layout
    plt.figure(figsize=(12, 8))

    # Use spring layout for better visualization
    pos = nx.spring_layout(G, k=3, iterations=50)

    # Draw nodes
    node_colors = []
    for node in G.nodes():
        if node == "base":
            node_colors.append("lightblue")
        elif "service" in node:
            node_colors.append("lightgreen")
        else:
            node_colors.append("lightcoral")

    nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=2000)

    # Draw edges
    nx.draw_networkx_edges(G, pos, edge_color="gray", arrows=True, arrowsize=20, arrowstyle="->")

    # Draw labels
    nx.draw_networkx_labels(G, pos, font_size=8, font_weight="bold")

    # Find and highlight circular dependencies
    cycles = find_circular_dependencies(dependencies)
    if cycles:
        # Highlight circular dependency edges in red
        cycle_edges = []
        for cycle in cycles:
            for i in range(len(cycle)):
                next_i = (i + 1) % len(cycle)
                cycle_edges.append((cycle[i], cycle[next_i]))

        nx.draw_networkx_edges(
            G,
            pos,
            edgelist=cycle_edges,
            edge_color="red",
            width=3,
            arrows=True,
            arrowsize=20,
            arrowstyle="->",
        )

    plt.title("Service Layer Dependencies", fontsize=16, fontweight="bold")
    plt.axis("of")
    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches="tight")
    plt.close()

    print(f"Dependency graph saved to {output_file}")


def generate_dependency_report(dependencies: Dict[str, Set[str]], cycles: List[List[str]]):
    """Generate a detailed dependency report."""
    print("\n" + "=" * 60)
    print("SERVICE DEPENDENCY ANALYSIS REPORT")
    print("=" * 60)

    print("\n1. Service Dependencies:")
    print("-" * 40)
    for service, deps in sorted(dependencies.items()):
        if deps:
            print(f"\n{service}:")
            for dep in sorted(deps):
                print(f"  → {dep}")
        else:
            print(f"\n{service}: (no dependencies)")

    print("\n2. Dependency Statistics:")
    print("-" * 40)
    dep_counts = {s: len(d) for s, d in dependencies.items()}
    for service, count in sorted(dep_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {service}: {count} dependencies")

    # Calculate reverse dependencies (who depends on this service)
    reverse_deps = {}
    for service, deps in dependencies.items():
        for dep in deps:
            if dep not in reverse_deps:
                reverse_deps[dep] = set()
            reverse_deps[dep].add(service)

    print("\n3. Most Depended Upon Services:")
    print("-" * 40)
    for service, dependents in sorted(reverse_deps.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"  {service}: used by {len(dependents)} services")
        for dependent in sorted(dependents):
            print(f"    ← {dependent}")

    print("\n4. Circular Dependencies:")
    print("-" * 40)
    if cycles:
        print("⚠️  WARNING: Circular dependencies detected!")
        for i, cycle in enumerate(cycles, 1):
            print(f"\n  Cycle {i}: {' → '.join(cycle)} → {cycle[0]}")
    else:
        print("✅ No circular dependencies found!")

    # Recommend refactoring if needed
    if cycles:
        print("\n5. Refactoring Recommendations:")
        print("-" * 40)
        print("Consider these strategies to break circular dependencies:")
        print("  1. Extract shared interfaces to a separate module")
        print("  2. Use dependency injection more extensively")
        print("  3. Apply the Dependency Inversion Principle")
        print("  4. Consider using events/observers pattern")
        print("  5. Move shared logic to a utility service")


def main():
    """Run the dependency analysis."""
    # Get service directory
    backend_dir = Path(__file__).parent.parent
    service_dir = backend_dir / "app" / "services"

    if not service_dir.exists():
        print(f"Service directory not found: {service_dir}")
        return

    print(f"Analyzing services in: {service_dir}")

    # Analyze dependencies
    dependencies = analyze_service_dependencies(service_dir)

    # Find circular dependencies
    cycles = find_circular_dependencies(dependencies)

    # Generate report
    generate_dependency_report(dependencies, cycles)

    # Create visualization
    try:
        visualize_dependencies(dependencies)
    except ImportError:
        print("\nNote: Install matplotlib and networkx for dependency visualization:")
        print("  pip install matplotlib networkx")

    # Return exit code based on circular dependencies
    return 1 if cycles else 0


if __name__ == "__main__":
    exit(main())
