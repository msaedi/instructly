import sys

print("Checking if test modules are imported:\n")

# Check for test-related modules
test_modules = [m for m in sys.modules if "test" in m or "conftest" in m]
if test_modules:
    print("Found test modules in sys.modules:")
    for mod in sorted(test_modules):
        print(f"  - {mod}")
else:
    print("No test modules found in sys.modules")

# Check Python path
print(f"\nPython path includes tests? {any('test' in p for p in sys.path)}")
print(f"First few paths: {sys.path[:5]}")
