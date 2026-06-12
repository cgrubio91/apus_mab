"""
Backend APU App — Compatibility Wrapper
All logic now lives in src/presentation/main.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.presentation.main import create_app, app

__all__ = ["create_app", "app"]
