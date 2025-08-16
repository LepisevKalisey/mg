#!/usr/bin/env python3

"""Main entry point for MG Digest Bot."""

import sys
from app.common.logging import setup_logging

logger = setup_logging()

if __name__ == "__main__":
    logger.info("Starting MG Digest Bot...")
    from run_all import main
    sys.exit(main())