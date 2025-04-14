#!/usr/bin/env python3
"""
Main execution script for the newspaper emailer.
Parses command-line arguments, sets up logging, loads configuration,
and orchestrates the download, storage, and email process.
"""

import logging
import sys
import argparse
from datetime import date

# Local imports
import config as config_module  # Import our new centralized configuration
import main  # Assuming main.py contains the main logic

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
DEFAULT_CONFIG_PATH = 'config.yaml'
DEFAULT_ENV_PATH = '.env'


if __name__ == "__main__":
    # Argument Parsing
    main_parser = argparse.ArgumentParser(description="Run the newspaper download and email process.")
    main_parser.add_argument("--date", type=str, help="Target date in YYYY-MM-DD format. Defaults to today.")
    main_parser.add_argument("--config", type=str, default=DEFAULT_CONFIG_PATH, help=f"Path to the configuration file (default: {DEFAULT_CONFIG_PATH})")
    main_parser.add_argument("--env-file", type=str, default=DEFAULT_ENV_PATH, help=f"Path to the .env file (default: {DEFAULT_ENV_PATH})")
    main_parser.add_argument("--dry-run", action="store_true", help="Simulate the process without downloading, uploading, or sending emails.")
    main_parser.add_argument("--force-download", action="store_true", help="Force download even if file seems to exist.")
    args = main_parser.parse_args()

    # Load configuration from .env and YAML using our centralized config module
    logger.info("Loading configuration from %s and %s", args.env_file, args.config)
    config = config_module.load_config(env_file=args.env_file, config_path=args.config)
    
    # Validate essential configuration
    if not config.get(('newspaper', 'url')) or not config.get(('newspaper', 'username')) or not config.get(('newspaper', 'password')):
        logger.critical("Missing critical configuration. Please check your config file and environment variables.")
        sys.exit(1)

    # Determine target date
    target_date_str = args.date
    if not target_date_str:
        date_format = config.get(('general', 'date_format'), '%Y-%m-%d')
        target_date_str = date.today().strftime(date_format)
        logger.info("No target date specified, using today: %s", target_date_str)

    # Run the main process
    try:
        logger.info("Starting main newspaper process for date: %s", target_date_str)
        # Pass target_date_str, dry_run, and force_download flags
        success = main.main(target_date_str=target_date_str, dry_run=args.dry_run, force_download=args.force_download)
        if success:
            logger.info("Newspaper process completed successfully for %s.", target_date_str)
            sys.exit(0)
        else:
            logger.error("Newspaper process failed for %s.", target_date_str)
            sys.exit(1)
    except Exception as e:
        logger.exception("An unexpected error occurred during the main process: %s", e)
        sys.exit(1)