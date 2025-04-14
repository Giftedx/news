import os
import logging
from datetime import date, timedelta, datetime

# Import project modules
import website
import storage
import email_sender
import config

# Logging setup - BasicConfig might be called upstream in run_newspaper.py
# Ensure logger works even if run standalone (though not intended)
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')

# Get configuration from centralized config module
NEWSPAPER_URL = config.config.get(('newspaper', 'url'))
USERNAME = config.config.get(('newspaper', 'username'))
PASSWORD = config.config.get(('newspaper', 'password'))
EMAIL_SENDER_ADDRESS = config.config.get(('email', 'sender'))
EMAIL_RECIPIENTS = config.config.get(('email', 'recipients'), [])
EMAIL_SUBJECT_TEMPLATE = config.config.get(('email', 'subject_template'))

# Constants from configuration
RETENTION_DAYS = config.config.get(('general', 'retention_days'), 7)
DATE_FORMAT = config.config.get(('general', 'date_format'), '%Y-%m-%d')
FILENAME_TEMPLATE = "{date}_newspaper.{format}" # Use format placeholder
THUMBNAIL_FILENAME_TEMPLATE = "{date}_thumbnail.jpg"

# --- Helper Functions ---

def get_past_papers_from_storage(target_date: date, days=None):
    """
    Get links to newspapers from the past 'days' up to target_date from cloud storage.
    """
    if days is None:
        days = RETENTION_DAYS # Use config value if not provided
    past_papers_links = []
    logger.info("Retrieving past %d paper links from storage up to %s.", days, target_date.strftime(DATE_FORMAT))
    try:
        # Assuming storage.list_storage_files exists despite potential linter error
        all_files = storage.list_storage_files() # pylint: disable=no-member
        if not all_files:
            logger.warning("No files found in cloud storage.")
            return []

        logger.info("Found %d files in storage. Filtering for the last %d days.", len(all_files), days)

        # Filter and sort files based on date in filename
        dated_files = []
        for filename in all_files:
            try:
                # Extract date part assuming format YYYY-MM-DD at the start
                date_str = filename.split('_')[0]
                file_date = datetime.strptime(date_str, DATE_FORMAT).date()
                # Only consider actual newspaper files (ignore thumbnails etc.)
                if "newspaper" in filename and (filename.endswith(".pdf") or filename.endswith(".html")):
                    dated_files.append((file_date, filename))
            except (ValueError, IndexError):
                logger.warning("Could not parse date from filename: %s. Skipping.", filename)
                continue # Skip files that don't match the expected naming convention

        # Sort by date descending (most recent first)
        dated_files.sort(key=lambda x: x[0], reverse=True)

        # Get links for the required number of days up to the target_date
        cutoff_date = target_date - timedelta(days=days -1) # Inclusive date range

        for file_date, filename in dated_files:
            if file_date >= cutoff_date and file_date <= target_date: # Ensure we don't include future dates if running for the past
                try:
                    # Assuming storage.get_file_url exists despite potential linter error
                    url = storage.get_file_url(filename) # pylint: disable=no-member
                    if url:
                        past_papers_links.append((file_date.strftime(DATE_FORMAT), url))
                    else:
                        logger.warning("Could not get URL for file: %s", filename)
                except storage.ClientError as url_ce: # Catch specific storage errors for URL generation
                    logger.error("Storage client error getting URL for %s: %s", filename, url_ce)
                except Exception as url_e: # Catch other unexpected errors during URL generation
                    # Using logger.exception to include traceback
                    logger.exception("Unexpected error getting URL for %s: %s", filename, url_e)
            # Stop adding once we have enough days or go past the cutoff
            if len(past_papers_links) >= days:
                break

        # Ensure the list is sorted chronologically for the email template if needed
        past_papers_links.sort(key=lambda x: x[0], reverse=True) # Keep most recent first for display logic
        logger.info("Collected %d past paper links from storage.", len(past_papers_links))
        return past_papers_links

    except storage.ClientError as ce: # Catch specific storage errors
        logger.error("Storage client error retrieving past papers: %s", ce)
        return []
    except Exception as e: # General fallback for listing/processing
        # Using logger.exception to include traceback
        logger.exception("Error retrieving past papers from storage: %s", e)
        return []


def cleanup_old_files(target_date: date, days_to_keep=None, dry_run: bool = False):
    """
    Remove files older than 'days_to_keep' relative to target_date from cloud storage.
    """
    if days_to_keep is None:
        days_to_keep = RETENTION_DAYS # Use config value if not provided
    try:
        # Assuming storage.list_storage_files exists
        # pylint: disable=no-member ; Pylint struggles with lazy S3 client init in storage module
        all_files = storage.list_storage_files()
        if not all_files:
            logger.info("No files found in storage, skipping cleanup.")
            return # Nothing to clean

        logger.info("Checking %d files for cleanup (older than %d days relative to %s).", len(all_files), days_to_keep, target_date.strftime(DATE_FORMAT))
        cutoff_date = target_date - timedelta(days=days_to_keep) # Files strictly older than this date

        deleted_count = 0
        for filename in all_files:
            try:
                # Extract date part assuming format YYYY-MM-DD at the start
                date_str = filename.split('_')[0]
                file_date = datetime.strptime(date_str, DATE_FORMAT).date()

                if file_date < cutoff_date:
                    logger.info("Attempting to delete old file: %s (Date: %s)", filename, file_date)
                    # Pass dry_run flag to storage.delete_from_storage
                    # Assuming storage.delete_from_storage exists
                    # pylint: disable=no-member ; Pylint struggles with lazy S3 client init in storage module
                    if storage.delete_from_storage(filename, dry_run=dry_run):
                        deleted_count += 1
                        logger.info("Successfully deleted %s%s", filename, (" (Dry Run)" if dry_run else ""))
                    else:
                        # delete_from_storage should log its own errors/warnings
                        pass # Already logged in delete_from_storage
            except (ValueError, IndexError):
                logger.warning("Could not parse date from filename for cleanup: %s. Skipping.", filename)
                continue # Skip files that don't match the expected naming convention

        logger.info("Cleanup complete. %s %d old files.", ('Simulated deleting' if dry_run else 'Deleted'), deleted_count)

    except storage.ClientError as ce: # Catch specific storage errors
        logger.error("Storage client error during cleanup: %s", ce)
    except Exception as e: # General fallback
        # Using logger.exception to include traceback
        logger.exception("Error during old file cleanup: %s", e)


# --- Main Execution Logic ---
def main(target_date_str: str | None = None, dry_run: bool = False, force_download: bool = False):
    """Main function to run the newspaper downloader for a specific date."""
    try:
        # Step 1: Validate configuration
        logger.info("Step 1: Validating configuration...")
        if not config.load():
            logger.critical("Configuration validation failed. Exiting.")
            return False

        # Step 2: Determine target date
        target_date = date.today() if not target_date_str else datetime.strptime(target_date_str, '%Y-%m-%d').date()
        logger.info("Step 2: Target date determined as %s", target_date)

        # Step 3: Download newspaper
        logger.info("Step 3: Downloading newspaper for %s...", target_date)
        newspaper_filename = f"{target_date.strftime('%Y-%m-%d')}_newspaper.pdf"
        newspaper_path = os.path.join(config.config.get(('paths', 'download_dir')), newspaper_filename)
        download_success, file_format = website.login_and_download(
            base_url=config.config.get(('newspaper', 'url')),
            username=config.config.get(('newspaper', 'username')),
            password=config.config.get(('newspaper', 'password')),
            save_path=newspaper_path,
            target_date=target_date_str,
            dry_run=dry_run,
            force_download=force_download
        )
        if not download_success:
            logger.error("Failed to download newspaper for %s. Exiting.", target_date)
            return False

        logger.info("Newspaper downloaded successfully: %s", newspaper_path)

        # Step 4: Get Paper Links (Today's and Past)
        logger.info("Step 4: Retrieving paper links from storage for %s...", target_date)
        today_paper_url = storage.get_file_url(newspaper_filename)
        if not today_paper_url:
            logger.error("Could not get URL for newspaper file: %s. Exiting.", newspaper_filename)
            return False
        logger.info("Retrieved URL for %s: %s", newspaper_filename, today_paper_url)

        past_papers_links = storage.get_past_papers_from_storage(target_date=target_date, days=config.config.get(('general', 'retention_days')))

        # Step 5: Send Email
        logger.info("Step 5: Sending email...")
        email_success = email_sender.send_email(
            target_date=target_date,
            today_paper_url=today_paper_url,
            past_papers=past_papers_links,
            thumbnail_path=None, # Assuming thumbnail generation is optional
            dry_run=dry_run
        )
        if not email_success:
            logger.error("Failed to send email for %s. Exiting.", target_date)
            return False

        logger.info("Email sent successfully for %s.", target_date)
        return True

    except ValueError as e:
        logger.error("Value error occurred: %s", e)
        return False
    except AttributeError as e:
        logger.error("Attribute error occurred: %s", e)
        return False
    except Exception as e:
        logger.exception("An unexpected error occurred in the main pipeline: %s", e)
        return False

# This block is mostly for testing/standalone runs, main execution is via run_newspaper.py
if __name__ == "__main__":
    logger.warning("main.py should ideally be run via run_newspaper.py to ensure proper configuration.")
    # Example of running for today in non-dry-run mode if executed directly
    today_date_str = date.today().strftime(DATE_FORMAT)
    success = main(target_date_str=today_date_str, dry_run=False) # Corrected: Pass target_date_str
    if not success:
        exit(1)
