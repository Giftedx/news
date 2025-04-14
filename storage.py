#!/usr/bin/env python3
"""
Storage interaction module
Handles uploading and deleting files from cloud storage (AWS S3 or compatible like Cloudflare R2).
Also manages local file cleanup.
"""

import logging
from datetime import datetime, timedelta
import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError
import config

# Configure logging
logger = logging.getLogger(__name__)

# --- Configuration from centralized config module ---
AWS_REGION = config.config.get(('storage', 'region'), 'us-east-1')
AWS_ACCESS_KEY_ID = config.config.get(('storage', 'aws_access_key_id'))
AWS_SECRET_ACCESS_KEY = config.config.get(('storage', 'aws_secret_access_key'))
S3_BUCKET_NAME = config.config.get(('storage', 'bucket_name'))
S3_ENDPOINT_URL = config.config.get(('storage', 'endpoint_url'))
ARCHIVE_RETENTION_DAYS = config.config.get(('general', 'retention_days'), 7)

# --- S3 Client Initialization (Lazy) ---
s3_client = None

def init_s3_client():
    """Initializes the S3 client if not already done."""
    # pylint: disable=global-statement
    global s3_client # Declare intent to modify the global variable
    if s3_client is None:
        if not S3_BUCKET_NAME:
            logger.error("S3_BUCKET_NAME environment variable is not set. Cannot initialize S3 client.")
            return False

        logger.info("Initializing S3 client for bucket: %s, region: %s", S3_BUCKET_NAME, AWS_REGION)
        try:
            session = boto3.Session(
                aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                region_name=AWS_REGION
            )
            s3_client = session.client('s3', endpoint_url=S3_ENDPOINT_URL)

            # Optional: Verify connection by listing buckets (requires list buckets permission)
            # s3_client.list_buckets()
            # logger.info("S3 client initialized and connection verified.")
            return True
        except (NoCredentialsError, PartialCredentialsError):
            logger.error("AWS credentials not found or incomplete. Please configure AWS credentials.")
            s3_client = None # Ensure client remains None if init fails
            return False
        except ClientError as e:
            # Handle potential endpoint or configuration errors
            logger.error("Error initializing S3 client: %s", e)
            s3_client = None
            return False
        except Exception as e: # Catch other potential issues during init
            # Using logger.exception to include traceback for unexpected errors
            logger.exception("An unexpected error occurred during S3 client initialization: %s", e)
            s3_client = None
            return False
    return True # Already initialized

def get_s3_client():
    """Returns the initialized S3 client, initializing it if necessary."""
    if s3_client is None:
        if not init_s3_client():
            return None
    return s3_client

# --- Storage Operations ---

def upload_to_s3(local_file_path, s3_key, dry_run=False):
    """Uploads a file to the configured S3 bucket."""
    client = get_s3_client()
    if not client:
        logger.error("S3 client not available. Cannot upload %s", local_file_path)
        return False

    if dry_run:
        logger.warning("[Dry Run] Would upload %s to s3://%s/%s", local_file_path, S3_BUCKET_NAME, s3_key)
        return True

    try:
        logger.info("Uploading %s to s3://%s/%s", local_file_path, S3_BUCKET_NAME, s3_key)
        client.upload_file(local_file_path, S3_BUCKET_NAME, s3_key)
        logger.info("Successfully uploaded %s", s3_key)
        return True
    except FileNotFoundError:
        logger.error("Local file not found for upload: %s", local_file_path)
        return False
    except NoCredentialsError:
        logger.error("AWS credentials not found for upload.")
        return False
    except ClientError as e:
        logger.error("S3 upload failed for %s: %s", s3_key, e)
        return False
    except Exception as e: # Catch other potential issues
        # Using logger.exception to include traceback for unexpected errors
        logger.exception("An unexpected error occurred during S3 upload of %s: %s", s3_key, e)
        return False

def upload_to_storage(local_file_path, s3_key, dry_run=False):
    """
    Wrapper function for upload_to_s3 to maintain consistent API.
    Uploads a file to the configured cloud storage.
    """
    return upload_to_s3(local_file_path, s3_key, dry_run)

def delete_from_storage(file_key, dry_run=False):
    """
    Deletes a file from the configured S3 bucket.
    """
    client = get_s3_client()
    if not client:
        logger.error("S3 client not available. Cannot delete %s", file_key)
        return False

    if dry_run:
        logger.warning("[Dry Run] Would delete %s from s3://%s", file_key, S3_BUCKET_NAME)
        return True

    try:
        logger.info("Deleting %s from s3://%s", file_key, S3_BUCKET_NAME)
        client.delete_object(Bucket=S3_BUCKET_NAME, Key=file_key)
        logger.info("Successfully deleted %s", file_key)
        return True
    except NoCredentialsError:
        logger.error("AWS credentials not found for delete operation.")
        return False
    except ClientError as e:
        logger.error("S3 delete failed for %s: %s", file_key, e)
        return False
    except Exception as e:
        # Using logger.exception to include traceback for unexpected errors
        logger.exception("An unexpected error occurred during S3 delete of %s: %s", file_key, e)
        return False

def list_storage_files():
    """
    Lists all files in the configured S3 bucket.
    
    Returns:
        list: A list of filenames (keys) in the S3 bucket, or None if there was an error.
    """
    client = get_s3_client()
    if not client:
        logger.error("S3 client not available. Cannot list files.")
        return None

    try:
        logger.info("Listing files in s3://%s", S3_BUCKET_NAME)
        response = client.list_objects_v2(Bucket=S3_BUCKET_NAME)
        
        # Check if any content exists
        if 'Contents' not in response:
            logger.info("No objects found in bucket %s", S3_BUCKET_NAME)
            return []

        files = [obj['Key'] for obj in response['Contents']]
        logger.info("Found %d files in storage.", len(files))
        
        # Handle pagination if there are more files
        while response['IsTruncated']:
            response = client.list_objects_v2(
                Bucket=S3_BUCKET_NAME,
                ContinuationToken=response['NextContinuationToken']
            )
            files.extend([obj['Key'] for obj in response['Contents']])
            logger.info("Retrieved additional %d files from paginated response.", len(response['Contents']))
        
        return files
    except NoCredentialsError:
        logger.error("AWS credentials not found for listing files.")
        return None
    except ClientError as e:
        logger.error("S3 list operation failed: %s", e)
        return None
    except Exception as e:
        # Using logger.exception to include traceback for unexpected errors
        logger.exception("An unexpected error occurred during S3 file listing: %s", e)
        return None

def get_file_url(file_key, expiration=3600):
    """
    Generates a presigned URL for accessing a file in the S3 bucket.
    
    Args:
        file_key: The key (filename) of the file in the S3 bucket.
        expiration: URL expiration time in seconds (default: 1 hour).
        
    Returns:
        str: Presigned URL for the file, or None if there was an error.
    """
    # Delegate to the generate_presigned_url function for consistency
    return generate_presigned_url(file_key, expiration=expiration, dry_run=False)

def list_archive_files(prefix="", dry_run=False):
    """Lists files in the S3 bucket, optionally filtered by prefix."""
    client = get_s3_client()
    if not client:
        logger.error("S3 client not available. Cannot list archive files.")
        return []

    if dry_run:
        logger.warning("[Dry Run] Would list files in s3://%s/%s", S3_BUCKET_NAME, prefix)
        # Return dummy data for dry run if needed for downstream logic
        return [
            {'Key': f'{prefix}dummy_archive_1.pdf', 'LastModified': datetime.now() - timedelta(days=1), 'Size': 12345},
            {'Key': f'{prefix}dummy_archive_2.pdf', 'LastModified': datetime.now() - timedelta(days=2), 'Size': 67890}
        ]

    try:
        logger.info("Listing files in s3://%s/%s", S3_BUCKET_NAME, prefix)
        paginator = client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=S3_BUCKET_NAME, Prefix=prefix)
        all_files = []
        for page in pages:
            if 'Contents' in page:
                all_files.extend(page['Contents'])
        logger.info("Found %d files matching prefix '%s'", len(all_files), prefix)
        return all_files
    except ClientError as e:
        logger.error("Failed to list S3 objects with prefix '%s': %s", prefix, e)
        return []
    except Exception as e: # Catch other potential issues
        # Using logger.exception to include traceback for unexpected errors
        logger.exception("An unexpected error occurred listing S3 files: %s", e)
        return []

def generate_presigned_url(s3_key, expiration=3600, dry_run=False):
    """Generates a presigned URL for an S3 object."""
    client = get_s3_client()
    if not client:
        logger.error("S3 client not available. Cannot generate presigned URL for %s", s3_key)
        return None

    if dry_run:
        logger.warning("[Dry Run] Would generate presigned URL for s3://%s/%s", S3_BUCKET_NAME, s3_key)
        return f"http://example.com/presigned-url/{s3_key}?simulated=true"

    try:
        logger.info("Generating presigned URL for %s (expires in %d seconds)", s3_key, expiration)
        url = client.generate_presigned_url('get_object',
                                           Params={'Bucket': S3_BUCKET_NAME, 'Key': s3_key},
                                           ExpiresIn=expiration)
        logger.debug("Generated presigned URL: %s", url) # Be cautious logging URLs if sensitive
        return url
    except ClientError as e:
        logger.error("Failed to generate presigned URL for %s: %s", s3_key, e)
        return None
    except Exception as e: # Catch other potential issues
        # Using logger.exception to include traceback for unexpected errors
        logger.exception("An unexpected error occurred generating presigned URL for %s: %s", s3_key, e)
        return None

def delete_old_files(retention_days, prefix="", dry_run=False):
    """Deletes files older than the specified retention period."""
    client = get_s3_client()
    if not client:
        logger.error("S3 client not available. Cannot delete old files.")
        return 0

    cutoff_date = datetime.now(datetime.now().astimezone().tzinfo) - timedelta(days=retention_days)
    logger.info("Deleting files older than %s (%d days) with prefix '%s'", cutoff_date.strftime('%Y-%m-%d'), retention_days, prefix)

    files_to_delete = []
    try:
        paginator = client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=S3_BUCKET_NAME, Prefix=prefix)

        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    # Ensure LastModified is timezone-aware for comparison
                    last_modified_aware = obj['LastModified'].astimezone(cutoff_date.tzinfo)
                    if last_modified_aware < cutoff_date:
                        files_to_delete.append({'Key': obj['Key']})
                        logger.debug("Marked for deletion: %s (Last Modified: %s)", obj['Key'], last_modified_aware)

        if not files_to_delete:
            logger.info("No files found older than %d days to delete.", retention_days)
            return 0
            
        # If in dry run mode, just log what would be deleted
        if dry_run:
            logger.info("[Dry Run] Would delete %d files older than %d days", 
                      len(files_to_delete), retention_days)
            for file_dict in files_to_delete:
                logger.info("[Dry Run] Would delete: %s", file_dict['Key'])
            return len(files_to_delete)
            
        # Delete files in batches of 1000 (S3 limit for bulk operations)
        deleted_count = 0
        # This inner try/except handles errors during the batch delete API call
        try:
            for i in range(0, len(files_to_delete), 1000):
                batch = files_to_delete[i:i+1000]
                response = client.delete_objects(
                    Bucket=S3_BUCKET_NAME,
                    Delete={
                        'Objects': batch,
                        'Quiet': False
                    }
                )
                
                # Log the results
                if 'Deleted' in response:
                    deleted_count += len(response['Deleted'])
                    for deleted in response['Deleted']:
                        logger.debug("Deleted: %s", deleted['Key'])
                        
                if 'Errors' in response and response['Errors']:
                    for error in response['Errors']:
                        logger.error("Error deleting %s: %s", error['Key'], error['Message'])
                        
            logger.info("Successfully deleted %d files older than %d days", deleted_count, retention_days)
            return deleted_count
        except ClientError as e: # Catch errors specifically from delete_objects
            logger.error("Error during bulk deletion API call: %s", e)
            # Return count of successfully deleted files before the error, if any
            return deleted_count 
            
    # These except blocks are now correctly aligned with the outer try block
    except ClientError as e:
        logger.error("Error listing or preparing files for deletion: %s", e)
        return 0
    except Exception as e:
        # Using logger.exception to include traceback for unexpected errors
        logger.exception("Unexpected error during file deletion process: %s", e)
        return 0