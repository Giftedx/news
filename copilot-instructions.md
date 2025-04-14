
START SPECIFICATION:
---
description: Apply this overview documentation for projects with automated newspaper delivery systems that handle downloading, storing, and emailing digital newspapers to subscribers
globs: *.py,*.yaml
alwaysApply: false
---


# main-overview

## Development Guidelines

- Only modify code directly relevant to the specific request. Avoid changing unrelated functionality.
- Never replace code with placeholders like `# ... rest of the processing ...`. Always include complete code.
- Break problems into smaller steps. Think through each step separately before implementing.
- Always provide a complete PLAN with REASONING based on evidence from code and logs before making changes.
- Explain your OBSERVATIONS clearly, then provide REASONING to identify the exact issue. Add console logs when needed to gather more information.


## Core Business Workflow

### Newspaper Processing Pipeline
- Downloads daily newspapers through website authentication and automated navigation
- Generates visual thumbnails for email preview
- Manages cloud storage for current and archived newspapers
- Sends formatted emails with links to current and past editions
- Maintains 7-day retention policy for newspaper archives

### Download Engine (Importance: 95)
Located in `website.py`:
- Multi-method download strategy with requests-based and Playwright-based approaches
- Date-specific newspaper targeting with support for various date formats
- Automatic format detection between PDF and HTML newspapers
- Session-based authentication handling

### Distribution System (Importance: 90)
Located in `email_sender.py` and `main.py`:
- Custom email composition with current and archive newspaper links
- Thumbnail generation for visual previews
- Multiple delivery methods (SMTP/SendGrid) support
- Template-based email formatting with Jinja2

### Storage Management (Importance: 85)
Located in `storage.py`:
- Cloud-based newspaper storage and archival
- Automated cleanup of outdated editions
- Archive listing for past paper access
- URL generation for email distribution

### Execution Control (Importance: 75)
Located in `run_newspaper.py`:
- Orchestrates the complete newspaper processing pipeline
- Supports simulation mode for testing
- Manages configuration and environment settings
- Controls archive retention policies

$END$
END SPECIFICATION