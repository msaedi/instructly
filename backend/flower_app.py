#!/usr/bin/env python3
"""
Flower monitoring app for Celery.

This runs Flower with basic authentication for production use.
"""

import subprocess
import sys

# Just run the minimal flower script
subprocess.run([sys.executable, "flower_minimal.py"])
