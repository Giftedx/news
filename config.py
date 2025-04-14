#!/usr/bin/env python3
"""
Centralized configuration module for the newspaper emailer system.
Handles loading configuration from environment variables and YAML files,
and provides a unified interface for accessing configuration values.
"""

import logging
import yaml
from dotenv import load_dotenv

# Configure logging
logger = logging.getLogger(__name__)

class Configuration:
    """Manages configuration loading and access for the newspaper emailer system."""
    
    def __init__(self):
        """Initialize with default values. Call load() to populate from sources."""
        # Default configuration values
        self._config = {
            'general': {
                'date_format': '%Y-%m-%d',
                'retention_days': 7,
            },
            'newspaper': {
                'url': None,
                'username': None,
                'password': None,
                'selectors': {
                    'username': 'input[name="username"]',
                    'password': 'input[name="password"]',
                    'submit': 'button[type="submit"]',
                    'login_success': '#user-profile-link',
                    'login_success_url': None,
                    'download_link': None,
                }
            },
            'storage': {
                'bucket_name': None,
                'region': 'us-east-1',
                'endpoint_url': None,
                'url_expiration': 3600,
            },
            'email': {
                'sender': None,
                'recipients': [],
                'subject_template': "Daily Newspaper - {{ date }}",
                'smtp_host': None,
                'smtp_port': 587,
                'smtp_user': None,
                'smtp_password': None,
                'sendgrid_api_key': None,
            },
            'paths': {
                'template_dir': 'templates',
                'template_name': 'email_template.html',
                'download_dir': 'downloads',
            },
        }
        
        self._env_mapping = {
            # General configurations
            'DATE_FORMAT': ('general', 'date_format'),
            'RETENTION_DAYS': ('general', 'retention_days'),
            
            # Newspaper configurations
            'NEWSPAPER_URL': ('newspaper', 'url'),
            'WEBSITE_URL': ('newspaper', 'url'),
            'NEWSPAPER_USERNAME': ('newspaper', 'username'),
            'WEBSITE_USERNAME': ('newspaper', 'username'),
            'NEWSPAPER_PASSWORD': ('newspaper', 'password'),
            'WEBSITE_PASSWORD': ('newspaper', 'password'),
            'USERNAME_SELECTOR': ('newspaper', 'selectors', 'username'),
            'PASSWORD_SELECTOR': ('newspaper', 'selectors', 'password'),
            'SUBMIT_BUTTON_SELECTOR': ('newspaper', 'selectors', 'submit'),
            'LOGIN_SUCCESS_SELECTOR': ('newspaper', 'selectors', 'login_success'),
            'LOGIN_SUCCESS_URL_PATTERN': ('newspaper', 'selectors', 'login_success_url'),
            'DOWNLOAD_LINK_SELECTOR': ('newspaper', 'selectors', 'download_link'),
            
            # Storage configurations
            'S3_BUCKET_NAME': ('storage', 'bucket_name'),
            'AWS_REGION': ('storage', 'region'),
            'S3_ENDPOINT_URL': ('storage', 'endpoint_url'),
            'URL_EXPIRATION': ('storage', 'url_expiration'),
            'ARCHIVE_RETENTION_DAYS': ('general', 'retention_days'),
            
            # Email configurations
            'EMAIL_SENDER': ('email', 'sender'),
            'EMAIL_FROM': ('email', 'sender'),
            'EMAIL_TO': ('email', 'recipients'),
            'MAILING_LIST': ('email', 'recipients'),
            'EMAIL_SUBJECT_TEMPLATE': ('email', 'subject_template'),
            'SMTP_HOST': ('email', 'smtp_host'),
            'SMTP_PORT': ('email', 'smtp_port'),
            'SMTP_USER': ('email', 'smtp_user'),
            'SMTP_PASSWORD': ('email', 'smtp_password'),
            'SENDGRID_API_KEY': ('email', 'sendgrid_api_key'),
            
            # Path configurations
            'TEMPLATE_DIR': ('paths', 'template_dir'),
            'TEMPLATE_NAME': ('paths', 'template_name'),
            'DOWNLOAD_DIR': ('paths', 'download_dir'),
        }
        
    def load(self, env_file=None, config_path=None):
        """
        Load configuration from environment variables and/or YAML file.
        
        Args:
            env_file (str): Path to .env file to load
            config_path (str): Path to YAML config file to load
            
        Returns:
            bool: True if configuration was successfully loaded
        """
        # Try to load from .env file
        if env_file:
            try:
                load_dotenv(env_file)
                logger.info("Loaded environment variables from %s", env_file)
            except FileNotFoundError:
                logger.error("Environment file not found: %s", env_file)
            except PermissionError:
                logger.error("Permission denied when accessing environment file: %s", env_file)
            except OSError as e:
                logger.error("OS error while accessing environment file %s: %s", env_file, e)

        else:
            try:
                load_dotenv()
                logger.debug("Attempted to load default .env file")
            except FileNotFoundError:
                logger.debug("Default .env file not found")
            except PermissionError:
                logger.debug("Permission denied for default .env file")
            except OSError as e:
                logger.debug("OS error for default .env file: %s", e)

        # Load from YAML if specified
        if config_path:
            try:
                with open(config_path, 'r', encoding='utf-8') as file:
                    yaml_config = yaml.safe_load(file)
                    if not yaml_config:
                        logger.warning("Empty or invalid YAML config file: %s", config_path)
                        return

                    self._merge_config(self._config, yaml_config)
                    logger.info("Loaded configuration from %s", config_path)

            except FileNotFoundError:
                logger.error("Configuration file not found: %s", config_path)
            except yaml.YAMLError as e:
                logger.error("Error parsing YAML configuration file %s: %s", config_path, e)
            except PermissionError:
                logger.error("Permission denied when accessing configuration file: %s", config_path)
            except OSError as e:
                logger.error("OS error while accessing configuration file %s: %s", config_path, e)
    
    def _merge_config(self, target, source):
        """Recursively merge source dict into target dict."""
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                # Recursively merge nested dictionaries
                self._merge_config(target[key], value)
            else:
                # Set or override the value
                target[key] = value
    
    def _set_nested_value(self, config_dict, path_tuple, value):
        """Set a value in a nested dictionary using a tuple of path segments."""
        if len(path_tuple) == 1:
            config_dict[path_tuple[0]] = value
            return
            
        key = path_tuple[0]
        if key not in config_dict:
            config_dict[key] = {}
        
        self._set_nested_value(config_dict[key], path_tuple[1:], value)
    
    def _validate_config(self):
        """Validate that essential configuration values are set."""
        required_values = [
            (('newspaper', 'url'), "Newspaper website URL is not configured"),
            (('newspaper', 'username'), "Newspaper website username is not configured"),
            (('newspaper', 'password'), "Newspaper website password is not configured"),
            (('email', 'sender'), "Email sender address is not configured"),
        ]

        valid = True
        for path, message in required_values:
            if not self.get(path):
                logger.error("Required configuration missing: %s", message)
                valid = False

        # Check for recipients if email sender is configured
        if self.get(('email', 'sender')) and not self.get(('email', 'recipients')):
            logger.warning("Email sender is configured but no recipients are specified")

        return valid
    
    def get(self, path, default=None):
        """
        Get a configuration value by path.
        
        Args:
            path (tuple or list): Path to the configuration value
            default: Value to return if path doesn't exist
            
        Returns:
            The configuration value or default if not found
        """
        try:
            value = self._config
            for segment in path:
                value = value[segment]
            return value
        except (KeyError, TypeError):
            return default

# Create a global instance for importing
config = Configuration()

def load_config(env_file=None, config_path=None):
    """Load configuration from sources and return the Configuration instance."""
    config.load(env_file, config_path)
    return config

# Automatically try to load configuration when module is imported
if __name__ != "__main__":
    config.load()
