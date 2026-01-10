#!/usr/bin/env python3
"""
Generate VAPID keys for web push notifications.

Run once, then add the keys to your environment variables.
KEEP THE PRIVATE KEY SECRET - never commit it to version control!

Usage:
    python scripts/generate_vapid_keys.py
"""

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from py_vapid.utils import b64urlencode
from pywebpush import Vapid


def main() -> None:
    vapid = Vapid()
    vapid.generate_keys()

    private_value = vapid.private_key.private_numbers().private_value
    private_key = b64urlencode(private_value.to_bytes(32, "big"))
    public_key = b64urlencode(
        vapid.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    )

    print("\n" + "=" * 60)
    print("VAPID Keys Generated Successfully!")
    print("=" * 60)
    print("\nAdd these to your .env file:\n")
    print(f"VAPID_PUBLIC_KEY={public_key}")
    print(f"VAPID_PRIVATE_KEY={private_key}")
    print("\n" + "=" * 60)
    print("IMPORTANT: Keep VAPID_PRIVATE_KEY secret.")
    print("Never commit it to version control.")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
