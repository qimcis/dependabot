"""Constants and configuration values for the dependabot package."""

# GitHub OAuth Configuration
GITHUB_OAUTH_CLIENT_ID = "Ov23lif56kE96lswYc6P"
GITHUB_OAUTH_SCOPES = "repo"
GITHUB_DEVICE_CODE_URL = "https://github.com/login/device/code"
GITHUB_ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"

# PR Configuration
PR_BRANCH_NAME_PREFIX = "dep-updates/"
PR_TITLE = "Update Dependencies"
PR_BODY_TEMPLATE = "Automated PR to update the following dependencies:\n\n{update_details}"

# Cache Configuration
CACHE_EXPIRY = 3600  # 1 hour in seconds 