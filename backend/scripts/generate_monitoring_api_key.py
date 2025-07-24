#!/usr/bin/env python3
"""
Generate a secure API key for monitoring endpoints.

Usage:
    python scripts/generate_monitoring_api_key.py
"""

import secrets
import string


def generate_api_key(length: int = 32) -> str:
    """
    Generate a cryptographically secure API key.

    Args:
        length: Length of the API key (default: 32 characters)

    Returns:
        Secure random API key
    """
    # Use alphanumeric characters (no ambiguous characters like 0/O, 1/l/I)
    alphabet = string.ascii_letters + string.digits
    # Remove ambiguous characters
    alphabet = alphabet.replace("0", "").replace("O", "").replace("I", "").replace("l", "")

    return "".join(secrets.choice(alphabet) for _ in range(length))


def main():
    """Generate and display a monitoring API key."""
    print("🔐 Monitoring API Key Generator")
    print("=" * 50)

    # Generate key
    api_key = generate_api_key()

    print(f"\nYour monitoring API key:\n{api_key}")

    print("\n📝 Add this to your Render environment variables:")
    print(f"MONITORING_API_KEY={api_key}")

    print("\n🚀 Usage example:")
    print(f'curl -H "X-Monitoring-API-Key: {api_key}" \\')
    print("     https://your-app.onrender.com/api/monitoring/dashboard")

    print("\n⚠️  Security notes:")
    print("- Keep this key secret and secure")
    print("- Rotate regularly (monthly recommended)")
    print("- Never commit to version control")
    print("- Use different keys for different environments")


if __name__ == "__main__":
    main()
