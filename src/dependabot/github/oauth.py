"""GitHub OAuth functionality."""

import time
import requests
import json
import webbrowser
from typing import Optional

from ..utils.console import console, print_error, print_success, print_warning
from ..utils.constants import (
    GITHUB_OAUTH_CLIENT_ID,
    GITHUB_OAUTH_SCOPES,
    GITHUB_DEVICE_CODE_URL,
    GITHUB_ACCESS_TOKEN_URL
)

def get_github_oauth_token() -> Optional[str]:
    """Manages the GitHub OAuth Device Flow to get an access token."""
    # Step 1: Request a device code and user code
    try:
        response = requests.post(
            GITHUB_DEVICE_CODE_URL,
            data={"client_id": GITHUB_OAUTH_CLIENT_ID, "scope": GITHUB_OAUTH_SCOPES},
            headers={"Accept": "application/json"},
            timeout=10
        )
        response.raise_for_status()
        device_code_data = response.json()
    except requests.RequestException as e:
        print_error(f"Error requesting device code from GitHub: {e}")
        return None
    except json.JSONDecodeError:
        print_error(f"Error decoding GitHub response for device code. Response: {response.text}")
        return None

    device_code = device_code_data.get("device_code")
    user_code = device_code_data.get("user_code")
    verification_uri = device_code_data.get("verification_uri")
    expires_in = device_code_data.get("expires_in", 300)  # 5 minutes expiry
    interval = device_code_data.get("interval", 5)      # 5 seconds polling interval

    if not all([device_code, user_code, verification_uri]):
        print_error(f"Incomplete device code response from GitHub: {device_code_data}")
        return None

    console.print(f"[bold yellow]Please authorize this application via your browser.[/bold yellow]")
    console.print(f"Go to: [link={verification_uri}]{verification_uri}[/link]")
    console.print(f"And enter the code: [bold cyan]{user_code}[/bold cyan]")
    
    # Try to open the verification URI in the default web browser
    try:
        if not webbrowser.open(verification_uri):
            print_warning("Could not automatically open the browser. Please navigate to the URL manually.")
    except Exception as e:
        print_warning(f"Error trying to open browser: {e}. Please navigate to the URL manually.")

    # Step 2: Poll for the access token
    start_time = time.time()
    while True:
        if time.time() - start_time > expires_in:
            print_error("Device code expired. Please try again.")
            return None

        time.sleep(interval)

        try:
            token_response = requests.post(
                GITHUB_ACCESS_TOKEN_URL,
                data={
                    "client_id": GITHUB_OAUTH_CLIENT_ID,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code"
                },
                headers={"Accept": "application/json"},
                timeout=10
            )
            token_data = token_response.json()
        except requests.RequestException as e:
            print_error(f"Error polling for access token: {e}")
            continue 
        except json.JSONDecodeError:
            print_error(f"Error decoding GitHub response for access token. Response: {token_response.text}")
            continue

        error = token_data.get("error")
        if error:
            if error == "authorization_pending":
                pass
            elif error == "slow_down":
                interval += 5  
            elif error == "expired_token":
                print_error("Device code expired while polling. Please try again.")
                return None
            elif error == "access_denied":
                print_error("Authorization denied by the user. Aborting.")
                return None
            else:
                print_error(f"GitHub OAuth Error: {error} - {token_data.get('error_description', 'No description')}")
                return None
        elif "access_token" in token_data:
            print_success("Successfully authorized and obtained access token!")
            return token_data["access_token"] 