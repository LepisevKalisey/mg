#!/usr/bin/env python3

"""Main entry point for MG Digest Bot."""

import sys
import os
from app.common.logging import setup_logging

logger = setup_logging()

def main():
    """Run the application."""
    logger.info("Starting MG Digest Bot...")
    from run_all import main as run_all_main
    return run_all_main()

if __name__ == "__main__":
    sys.exit(main())