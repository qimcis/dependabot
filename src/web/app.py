from flask import Flask, render_template, request, jsonify
import threading
from typing import Optional, Dict, Any
import time
import sys
import os

# Add the parent directory to sys.path to import from src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from main import check_updates_parallel, create_github_pr, get_github_oauth_token

app = Flask(__name__)

# Store OAuth tokens and job status
oauth_tokens: Dict[str, str] = {}
job_status: Dict[str, Dict[str, Any]] = {}

def generate_job_id() -> str:
    """Generate a unique job ID."""
    return f"job_{int(time.time())}_{threading.get_ident()}"

def process_repository(job_id: str, repo_url: str, dependency_file_path: Optional[str] = None):
    """Process a repository in a background thread."""
    try:
        # Update job status
        job_status[job_id].update({
            "status": "processing",
            "message": "Checking repository for updates..."
        })

        # Get OAuth token
        oauth_token = get_github_oauth_token()
        if not oauth_token:
            job_status[job_id].update({
                "status": "error",
                "message": "Failed to obtain GitHub OAuth token"
            })
            return

        # Check for updates
        updates, dep_type, dep_file_path = check_updates_parallel(repo_url, dependency_file_path)
        
        if not updates:
            job_status[job_id].update({
                "status": "completed",
                "message": "No updates found",
                "updates": []
            })
            return

        # Create PR
        pr_url = create_github_pr(repo_url, dep_file_path, dep_type, "", updates, oauth_token)
        
        if pr_url:
            job_status[job_id].update({
                "status": "completed",
                "message": "Successfully created PR",
                "pr_url": pr_url,
                "updates": [
                    {
                        "package": pkg,
                        "current": curr,
                        "latest": latest
                    } for pkg, curr, latest in updates
                ]
            })
        else:
            job_status[job_id].update({
                "status": "error",
                "message": "Failed to create PR",
                "updates": [
                    {
                        "package": pkg,
                        "current": curr,
                        "latest": latest
                    } for pkg, curr, latest in updates
                ]
            })

    except Exception as e:
        job_status[job_id].update({
            "status": "error",
            "message": f"Error processing repository: {str(e)}"
        })

@app.route('/')
def index():
    """Render the main page."""
    return render_template('index.html')

@app.route('/check', methods=['POST'])
def check_repository():
    """Handle repository check requests."""
    data = request.get_json()
    repo_url = data.get('repo_url')
    dependency_file_path = data.get('dependency_file_path')

    if not repo_url:
        return jsonify({"error": "Repository URL is required"}), 400

    # Generate job ID and initialize status
    job_id = generate_job_id()
    job_status[job_id] = {
        "status": "queued",
        "message": "Job queued for processing"
    }

    # Start processing in background thread
    thread = threading.Thread(
        target=process_repository,
        args=(job_id, repo_url, dependency_file_path)
    )
    thread.daemon = True
    thread.start()

    return jsonify({
        "job_id": job_id,
        "status": "queued",
        "message": "Processing started"
    })

@app.route('/status/<job_id>')
def get_status(job_id: str):
    """Get the status of a job."""
    if job_id not in job_status:
        return jsonify({"error": "Job not found"}), 404
    
    return jsonify(job_status[job_id])

if __name__ == '__main__':
    app.run(debug=True) 