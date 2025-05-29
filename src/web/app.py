from flask import Flask, render_template, request, jsonify
import threading
import time
from typing import Dict, Any, Optional, List, Tuple
import requests
import sys
import os
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ..main import (
    check_updates_parallel,
    create_github_pr,
    GITHUB_OAUTH_CLIENT_ID,
    GITHUB_OAUTH_SCOPES,
    GITHUB_DEVICE_CODE_URL,
    GITHUB_ACCESS_TOKEN_URL,
    PR_TITLE,
    PR_BODY_TEMPLATE,
)

app = Flask(__name__)

# In-memory stores
# Tracks ongoing OAuth device flows keyed by the GitHub device_code returned
oauth_flows: Dict[str, Dict[str, Any]] = {}

# Helper utilities

def fetch_original_file_content(repo_url: str, dep_file_path: str) -> Optional[str]:
    """Fetch the raw contents of the given dependency file from the repo."""
    repo_path_cleaned = (
        repo_url.replace("https://github.com/", "").replace("http://github.com/", "")
    )
    if repo_path_cleaned.endswith("/"):
        repo_path_cleaned = repo_path_cleaned[:-1]
    owner_repo = "/".join(repo_path_cleaned.split("/")[:2])

    for branch in ["main", "master"]:
        raw_url = f"https://raw.githubusercontent.com/{owner_repo}/{branch}/{dep_file_path}"
        try:
            resp = requests.get(raw_url, timeout=10)
            if resp.status_code == 200:
                return resp.text
        except requests.RequestException:
            continue
    return None 


# Routes

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/check", methods=["POST"])
def check_dependencies():
    """Return the list of outdated dependencies for the provided repository."""
    data = request.get_json() or {}
    repo_url = data.get("repo_url")
    dependency_file_path = data.get("dependency_file_path")

    if not repo_url:
        return jsonify({"error": "Repository URL is required."}), 400

    updates, dep_type, dep_file_path = check_updates_parallel(
        repo_url, dependency_file_path
    )

    # --- Add dev property for npm dependencies ---
    response_updates = []
    if dep_type == "npm":
        # Fetch package.json to distinguish devDependencies
        repo_path_cleaned = repo_url.replace("https://github.com/", "").replace("http://github.com/", "")
        if repo_path_cleaned.endswith("/"):
            repo_path_cleaned = repo_path_cleaned[:-1]
        owner_repo = "/".join(repo_path_cleaned.split("/")[:2])
        package_json_url = None
        for branch in ["main", "master"]:
            url = f"https://raw.githubusercontent.com/{owner_repo}/{branch}/{dep_file_path or 'package.json'}"
            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    package_json_url = url
                    pkg_data = json.loads(resp.text)
                    break
            except Exception:
                continue
        dev_pkgs = set(pkg_data.get("devDependencies", {}).keys()) if package_json_url else set()
        for p, c, l in updates:
            response_updates.append({
                "package": p,
                "current": c,
                "latest": l,
                "dev": p in dev_pkgs
            })
    else:
        response_updates = [
            {"package": p, "current": c, "latest": l} for p, c, l in updates
        ]

    return jsonify(
        {
            "updates": response_updates,
            "dependency_type": dep_type,
            "dependency_file": dep_file_path,
        }
    )


# PR creation flow helpers

def poll_and_create_pr(device_code: str):
    """Background task: poll GitHub OAuth endpoint, then store access token and set status."""
    flow = oauth_flows[device_code]
    interval = flow.get("interval", 5)
    expires_at = flow.get("expires_at", time.time() + 900)

    while time.time() < expires_at:
        time.sleep(interval)

        # Poll for access token
        try:
            token_resp = requests.post(
                GITHUB_ACCESS_TOKEN_URL,
                data={
                    "client_id": GITHUB_OAUTH_CLIENT_ID,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
                headers={"Accept": "application/json"},
                timeout=10,
            )
            token_data = token_resp.json()
        except Exception as exc:
            flow.update({"status": "error", "message": f"Error polling token: {exc}"})
            return

        if "error" in token_data:
            err = token_data["error"]
            if err == "authorization_pending":
                continue  # user hasn't authorized yet
            if err == "slow_down":
                interval += 5
                continue
            flow.update({"status": "error", "message": f"OAuth error: {err}"})
            return

        # Success
        access_token = token_data.get("access_token")
        if not access_token:
            flow.update({"status": "error", "message": "No access token returned."})
            return

        # Store the access token and set status to authorized, but do NOT create the PR here
        flow["access_token"] = access_token
        flow.update({"status": "authorized", "message": "Authorized. Ready to create PR."})
        return  # finished

    # Timed out
    flow.update({"status": "error", "message": "Authorization timed out."})


@app.route("/start_pr", methods=["POST"])
def start_pr():
    data = request.get_json() or {}
    repo_url = data.get("repo_url")
    dependency_file_path = data.get("dependency_file_path")

    if not repo_url:
        return jsonify({"error": "Repository URL is required."}), 400

    # First check there are updates worth creating a PR for
    updates, dep_type, dep_file_path = check_updates_parallel(
        repo_url, dependency_file_path
    )
    if not updates:
        return jsonify({"error": "No updates found."}), 400

    # Prepare PR preview info
    update_details_md = "\n".join([
        f"| `{p}` | `{c}` | `{l}` |" for p, c, l in updates
    ])
    default_pr_title = PR_TITLE
    default_pr_body = PR_BODY_TEMPLATE.format(update_details=update_details_md)
    diff_preview = [
        {"package": p, "current": c, "latest": l} for p, c, l in updates
    ]

    # Start GitHub device flow
    try:
        resp = requests.post(
            GITHUB_DEVICE_CODE_URL,
            data={"client_id": GITHUB_OAUTH_CLIENT_ID, "scope": GITHUB_OAUTH_SCOPES},
            headers={"Accept": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()
        device_data = resp.json()
    except Exception as exc:
        return jsonify({"error": f"Failed to start OAuth flow: {exc}"}), 500

    device_code = device_data.get("device_code")
    user_code = device_data.get("user_code")
    verification_uri = device_data.get("verification_uri")
    expires_in = device_data.get("expires_in", 900)
    interval = device_data.get("interval", 5)

    if not all([device_code, user_code, verification_uri]):
        return jsonify({"error": "Incomplete response from GitHub."}), 500

    # Store context
    oauth_flows[device_code] = {
        "repo_url": repo_url,
        "dependency_file_path": dependency_file_path,
        "updates": updates,
        "dep_type": dep_type,
        "dep_file_path": dep_file_path,
        "status": "waiting_for_user",
        "message": "Waiting for user authorization…",
        "interval": interval,
        "expires_at": time.time() + expires_in,
        "default_pr_title": default_pr_title,
        "default_pr_body": default_pr_body,
        "diff_preview": diff_preview,
    }

    # Spawn background thread
    t = threading.Thread(target=poll_and_create_pr, args=(device_code,), daemon=True)
    t.start()

    return jsonify(
        {
            "device_code": device_code,
            "user_code": user_code,
            "verification_uri": verification_uri,
            "expires_in": expires_in,
            "default_pr_title": default_pr_title,
            "default_pr_body": default_pr_body,
            "diff_preview": diff_preview,
        }
    )


@app.route("/pr_status/<device_code>")
def pr_status(device_code: str):
    flow = oauth_flows.get(device_code)
    if not flow:
        return jsonify({"error": "Unknown device code."}), 404
    return jsonify(flow)


@app.route("/submit_pr", methods=["POST"])
def submit_pr():
    data = request.get_json() or {}
    device_code = data.get("device_code")
    pr_title = data.get("pr_title")
    pr_body = data.get("pr_body")
    if not device_code or not pr_title or not pr_body:
        return jsonify({"error": "Missing required fields."}), 400
    flow = oauth_flows.get(device_code)
    if not flow:
        return jsonify({"error": "Unknown device code."}), 400
    
    # Store the custom PR title and body in the flow data
    flow["pr_title"] = pr_title
    flow["pr_body"] = pr_body
    
    # If already authorized, create PR immediately
    if flow.get("status") == "authorized":
        access_token = flow.get("access_token")
        if not access_token:
            return jsonify({"error": "Not authorized yet."}), 400
        # Use the latest updates and info from the flow
        updates = flow["updates"]
        dep_type = flow["dep_type"]
        dep_file_path = flow["dep_file_path"]
        repo_url = flow["repo_url"]
        # Fetch original file content
        original_content = fetch_original_file_content(repo_url, dep_file_path)
        if original_content is None:
            return jsonify({"error": "Could not fetch dependency file."}), 400
        pr_url = create_github_pr(
            repo_url,
            dep_file_path,
            dep_type,
            original_content,
            updates,
            access_token,
            pr_title,
            pr_body,
        )
        if pr_url:
            return jsonify({"pr_url": pr_url})
        else:
            return jsonify({"error": "Failed to create pull request."}), 500
    
    return jsonify({"status": "pending", "message": "PR creation pending authorization."})


if __name__ == "__main__":
    app.run(debug=True) 