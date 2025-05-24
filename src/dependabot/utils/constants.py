"""Constants and configuration values for the dependabot package."""

# GitHub OAuth Configuration
GITHUB_OAUTH_CLIENT_ID = "Ov23lif56kE96lswYc6P"
GITHUB_OAUTH_SCOPES = "repo"
GITHUB_DEVICE_CODE_URL = "https://github.com/login/device/code"
GITHUB_ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"

# PR Configuration
PR_BRANCH_NAME_PREFIX = "dep-updates/"
PR_TITLE = "Dependabot: Update Dependencies"
PR_BODY_TEMPLATE = """
## Summary
This PR updates the following dependencies to their latest versions.

### Dependency Updates
| Package | From | To |
|---------|------|----|
{update_details}

### Instructions
- Please review the changes and run your test suite to ensure everything works as expected.
- These updates are automated by Dependabot.
- If you encounter any issues, please let us know or adjust update preferences in your repository settings.
"""

# Cache Configuration
CACHE_EXPIRY = 3600  # 1 hour in seconds 