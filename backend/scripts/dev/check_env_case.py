import os

print("Checking for is_testing in all cases:\n")

# Check all variations
variations = ["is_testing", "IS_TESTING", "Is_Testing", "IS_testing", "istesting", "ISTESTING", "IsTesting"]

for var in variations:
    value = os.environ.get(var)
    if value is not None:
        print(f"Found {var} = {value}")

# Check if any env var contains 'is_testing'
print("\nAll env vars containing 'is_testing' (case insensitive):")
for key, value in os.environ.items():
    if "is_testing" in key.lower():
        print(f"{key} = {value}")

# Check the actual .env file
print("\nChecking .env file for is_testing:")
with open(".env", "r") as f:
    for line in f:
        if "is_testing" in line.lower() and not line.strip().startswith("#"):
            print(f"Found: {line.strip()}")
