import os

print("Environment variables that might affect testing mode:\n")
for key in os.environ:
    if any(word in key.lower() for word in ["test", "env", "mode"]):
        print(f"{key}: {os.environ[key]}")
