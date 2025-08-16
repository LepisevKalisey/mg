#!/usr/bin/env python3

"""Run all MG Digest components."""

import asyncio
import logging
import multiprocessing
import os
import signal
import sys
import time

from app.common.config import load_config
from app.common.logging import setup_logging

logger = setup_logging()


def run_watcher():
    """Run the Telegram watcher."""
    from app.watcher import main as watcher_main
    logger.info("Starting Telegram watcher...")
    watcher_main()


def run_scheduler():
    """Run the scheduler."""
    from app.worker.scheduler import main as scheduler_main
    logger.info("Starting scheduler...")
    scheduler_main()


def run_web():
    """Run the web server."""
    from app.web import main as web_main
    logger.info("Starting web server...")
    web_main()


def signal_handler(sig, frame):
    """Handle signals."""
    logger.info(f"Received signal {sig}, shutting down...")
    sys.exit(0)


def main():
    """Run all components."""
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Load config
    config = load_config()
    
    # Create processes
    processes = []
    
    # Start watcher
    if config.get("ENABLE_WATCHER", "true").lower() == "true":
        watcher_process = multiprocessing.Process(target=run_watcher)
        watcher_process.start()
        processes.append(("watcher", watcher_process))
        logger.info(f"Watcher process started with PID {watcher_process.pid}")
    
    # Start scheduler
    if config.get("ENABLE_SCHEDULER", "true").lower() == "true":
        scheduler_process = multiprocessing.Process(target=run_scheduler)
        scheduler_process.start()
        processes.append(("scheduler", scheduler_process))
        logger.info(f"Scheduler process started with PID {scheduler_process.pid}")
    
    # Start web server
    if config.get("ENABLE_WEB", "true").lower() == "true":
        web_process = multiprocessing.Process(target=run_web)
        web_process.start()
        processes.append(("web", web_process))
        logger.info(f"Web server process started with PID {web_process.pid}")
    
    # Monitor processes
    try:
        while True:
            for name, process in processes:
                if not process.is_alive():
                    logger.error(f"{name.capitalize()} process died, restarting...")
                    if name == "watcher":
                        process = multiprocessing.Process(target=run_watcher)
                    elif name == "scheduler":
                        process = multiprocessing.Process(target=run_scheduler)
                    elif name == "web":
                        process = multiprocessing.Process(target=run_web)
                    
                    process.start()
                    logger.info(f"{name.capitalize()} process restarted with PID {process.pid}")
            
            time.sleep(5)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down...")
    finally:
        # Terminate all processes
        for name, process in processes:
            logger.info(f"Terminating {name} process...")
            process.terminate()
            process.join()
        
        logger.info("All processes terminated")


if __name__ == "__main__":
    main()