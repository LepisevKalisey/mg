#!/usr/bin/env python
"""
Entry point for running the MG Digest watcher component.

This script imports and calls the main function from the watcher module.
"""

import asyncio
import logging

from app.watcher import main
from app.common.logging import setup_logging

logger = setup_logging()

if __name__ == "__main__":
    try:
        logger.info("Starting MG Digest watcher")
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("MG Digest watcher stopped")
    except Exception as e:
        logger.exception(f"Error in MG Digest watcher: {e}")
        exit(1)