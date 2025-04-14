#!/usr/bin/env python3
"""
Email sending module
Handles composing and sending emails using SMTP or SendGrid.
"""

import os
import logging
import smtplib
from smtplib import SMTPAuthenticationError, SMTPConnectError
import socket # Import socket for gaierror
import base64
import mimetypes
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition, ContentId
from jinja2 import Environment, FileSystemLoader, select_autoescape
from datetime import date

# Import centralized configuration
import config

# Configure logging
logger = logging.getLogger(__name__)

# --- Configuration from centralized config module ---
SMTP_HOST = config.config.get(('email', 'smtp_host'))
SMTP_PORT = config.config.get(('email', 'smtp_port'), 587)
SMTP_USER = config.config.get(('email', 'smtp_user'))
SMTP_PASSWORD = config.config.get(('email', 'smtp_password'))
SENDGRID_API_KEY = config.config.get(('email', 'sendgrid_api_key'))
EMAIL_FROM = config.config.get(('email', 'sender'))
EMAIL_TO = config.config.get(('email', 'recipients'), [])
EMAIL_SUBJECT_PREFIX = config.config.get(('email', 'subject_template'), 'Daily Newspaper').split(' - ')[0]
TEMPLATE_DIR = config.config.get(('paths', 'template_dir'), 'templates')
TEMPLATE_NAME = config.config.get(('paths', 'template_name'), 'email_template.html')

# --- Jinja2 Environment Setup ---
template_loader = FileSystemLoader(TEMPLATE_DIR)
env = Environment(
    loader=template_loader,
    autoescape=select_autoescape(['html', 'xml'])
)

# --- Email Sending Functions ---

def send_email(target_date: date, today_paper_url: str, past_papers: list, thumbnail_path: str | None = None, dry_run: bool = False):
    """
    Compose and send an email with the newspaper details.

    Args:
        target_date: The date for the newspaper
        today_paper_url: URL to today's newspaper
        past_papers: List of tuples (date_str, url) for past papers
        thumbnail_path: Path to the thumbnail image file (optional)
        dry_run: If True, only log the actions without sending the email

    Returns:
        bool: True if the email was sent or simulated to be sent successfully, False otherwise
    """
    # Corrected syntax: Ensure this block is properly indented and part of the function
    if not EMAIL_FROM or not EMAIL_TO:
        logger.error("Email FROM or TO address not configured. Cannot send email.")
        return False

    # Handle both string and list types for recipients
    if isinstance(EMAIL_TO, str):
        recipients = [email.strip() for email in EMAIL_TO.split(',') if email.strip()]
    elif isinstance(EMAIL_TO, list):
        recipients = [email.strip() for email in EMAIL_TO if email and isinstance(email, str)]
    else:
        logger.error("EMAIL_TO must be either a string or a list.")
        return False
        
    if not recipients:
        logger.error("No valid recipient email addresses found in EMAIL_TO.")
        return False
        
    subject = f"{EMAIL_SUBJECT_PREFIX} - {target_date.strftime('%Y-%m-%d')}"

    # Check if template directory exists
    template_dir_path = os.path.abspath(TEMPLATE_DIR)
    if not os.path.isdir(template_dir_path):
        logger.error("Template directory not found: %s", template_dir_path)
        return False
        
    # Check if template file exists
    template_path = os.path.join(template_dir_path, TEMPLATE_NAME)
    if not os.path.isfile(template_path):
        logger.error("Email template file not found: %s", template_path)
        return False
        
    try:
        template = env.get_template(TEMPLATE_NAME)
        # Prepare template context
        context = {
            'date': target_date.strftime('%A, %B %d, %Y'),
            'today_paper_url': today_paper_url,
            'past_papers': past_papers, # List of tuples (date_str, url)
            'has_thumbnail': thumbnail_path is not None
        }
        html_content = template.render(context)
    except Exception as e: # Catch template rendering errors
        logger.exception("Failed to render email template '%s': %s", TEMPLATE_NAME, e) # Use logger.exception
        return False

    if dry_run:
        logger.warning("Dry Run: Would send email with subject '%s' to %s", subject, ", ".join(recipients))
        logger.debug("Dry Run: Email HTML content:\n%s", html_content)
        return True # Simulate success

    # Determine sending method
    if SENDGRID_API_KEY:
        logger.info("Using SendGrid to send email.")
        return _send_with_sendgrid(recipients, subject, html_content, thumbnail_path)
    elif SMTP_HOST and SMTP_USER and SMTP_PASSWORD:
        logger.info("Using SMTP to send email.")
        return _send_with_smtp(recipients, subject, html_content, thumbnail_path)
    else:
        logger.error("No email sending method configured (SendGrid API Key or SMTP credentials required).")
        return False


def _send_with_smtp(recipients, subject, html_content, thumbnail_path):
    """
    Send email using SMTP server.

    Args:
        recipients: List of recipient email addresses
        subject: Email subject
        html_content: HTML content of the email
        thumbnail_path: Path to the thumbnail image file (optional)

    Returns:
        bool: True if the email was sent successfully, False otherwise
    """
    try:
        msg = MIMEMultipart('related')
        msg['Subject'] = subject
        msg['From'] = EMAIL_FROM
        msg['To'] = ", ".join(recipients) # Comma-separated string for header

        # Attach HTML content
        msg_alternative = MIMEMultipart('alternative')
        msg.attach(msg_alternative)
        msg_text = MIMEText("Please enable HTML to view this email.", 'plain') # Basic plain text fallback
        msg_alternative.attach(msg_text)
        msg_html = MIMEText(html_content, 'html')
        msg_alternative.attach(msg_html)

        # Attach thumbnail if available
        if thumbnail_path and os.path.exists(thumbnail_path):
            try:
                with open(thumbnail_path, 'rb') as fp:
                    img = MIMEImage(fp.read())
                img.add_header('Content-ID', '<thumbnail_image>') # Must match cid in template
                img.add_header('Content-Disposition', 'inline', filename=os.path.basename(thumbnail_path))
                msg.attach(img)
                logger.info("Attached thumbnail: %s", thumbnail_path) # Use % formatting
            except IOError as e:
                logger.warning("Could not read or attach thumbnail file %s: %s", thumbnail_path, e)
        elif thumbnail_path:
            # Corrected indentation
            logger.warning("Thumbnail path specified (%s) but file not found.", thumbnail_path)

        # Send the email
        logger.info("Connecting to SMTP server %s:%d...", SMTP_HOST, SMTP_PORT)
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo() # Identify ourselves to the SMTP server
            server.starttls() # Enable encryption
            server.ehlo() # Re-identify ourselves after starting TLS
            logger.info("Logging into SMTP server...")
            server.login(SMTP_USER, SMTP_PASSWORD)
            logger.info("Sending email to %s...", ", ".join(recipients))
            server.sendmail(EMAIL_FROM, recipients, msg.as_string())
            logger.info("Email sent successfully via SMTP.")
        return True

    except SMTPAuthenticationError as e:
        logger.error("SMTP authentication failed: %s", e)
        raise
    except SMTPConnectError as e:
        logger.error("SMTP connection error: %s", e)
        raise
    except IOError as e:
        logger.error("File I/O error during email attachment handling: %s", e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during email sending: %s", e)
        raise


def _send_with_sendgrid(recipients, subject, html_content, thumbnail_path):
    """
    Send email using SendGrid API.

    Args:
        recipients: List of recipient email addresses
        subject: Email subject
        html_content: HTML content of the email
        thumbnail_path: Path to the thumbnail image file (optional)

    Returns:
        bool: True if the email was sent successfully, False otherwise
    """
    if not SENDGRID_API_KEY:
        logger.error("SendGrid API Key not configured.")
        return False

    message = Mail(
        from_email=EMAIL_FROM,
        to_emails=recipients, # SendGrid accepts a list
        subject=subject,
        html_content=html_content
    )

    # Attach thumbnail if available
    if thumbnail_path and os.path.exists(thumbnail_path):
        try:
            # Ensure base64 is available (already checked by import)
            with open(thumbnail_path, "rb") as f:
                data = base64.b64encode(f.read()).decode()
            attachment = Attachment(
                FileContent(data),
                FileName(os.path.basename(thumbnail_path)),
                FileType(mimetypes.guess_type(thumbnail_path)[0] or 'application/octet-stream'), # Guess MIME type
                Disposition("inline"), # Display inline if possible
                ContentId("thumbnail_cid") # Content ID for embedding
            )
            message.attachment = attachment
        except (IOError, TypeError, ValueError) as e: # More specific exceptions
            logger.warning("Failed to prepare SendGrid attachment for %s: %s", thumbnail_path, e)
    elif thumbnail_path:
        # Corrected indentation
        logger.warning("Thumbnail path specified (%s) but file not found.", thumbnail_path)

    # Send the email
    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY) # Use configured API key
        response = sg.send(message)
        logger.info("Email sent via SendGrid. Status code: %s", response.status_code)
        # Check for success status codes (e.g., 2xx)
        if 200 <= response.status_code < 300:
            return True
        else:
            logger.error("SendGrid API returned non-success status %d: %s", response.status_code, response.body)
            return False
    except ImportError:
        # This case should ideally not be reached if the initial import worked,
        # but kept for robustness if the library becomes unavailable unexpectedly.
        logger.error("SendGrid library became unavailable. Cannot send email via SendGrid.")
        return False
    except Exception as e: # Catch potential API call errors (e.g., network issues), log traceback
        logger.exception("Failed to send email via SendGrid API call: %s", e)
        return False

def send_email_smtp(subject, body, recipients, sender, smtp_config):
    try:
        with smtplib.SMTP(smtp_config['host'], smtp_config['port']) as server:
            server.starttls()
            server.login(smtp_config['user'], smtp_config['password'])
            logger.info("Logged in to SMTP server successfully.")

            message = f"Subject: {subject}\n\n{body}"
            server.sendmail(sender, recipients, message)
            logger.info("Email sent successfully to %s", recipients)
    except SMTPAuthenticationError as e:
        logger.error("SMTP authentication failed: %s", e)
        raise
    except SMTPConnectError as e:
        logger.error("SMTP connection error: %s", e)
        raise
    except IOError as e:
        logger.error("File I/O error during email attachment handling: %s", e)
        raise
    except Exception as e:
        logger.exception("Unexpected error during email sending: %s", e)
        raise