from __future__ import annotations

"""
API module for MG Digest system.

This module provides a FastAPI-based REST API for interacting with the MG Digest system.
It includes endpoints for managing sources, digests, and user settings.
"""

__all__ = ["create_app", "run_app"]

from .app import create_app, run_app