"""GitHub Pull Request functionality."""

import time
from typing import List, Tuple, Optional
import json
import re

from github import Github, GithubException, UnknownObjectException

from ..utils.console import print_error, print_info, print_success
from ..utils.constants import (
    PR_BRANCH_NAME_PREFIX,
    PR_TITLE,
    PR_BODY_TEMPLATE
)

def generate_new_dependency_file_content(original_content: str, dep_type: str, updates_to_apply: List[Tuple[str, str, str]]) -> str:
    """Generates new content for a dependency file with updated versions."""
    if not updates_to_apply:
        return original_content

    new_content = original_content
    updates_map = {pkg_name: latest_version for pkg_name, _, latest_version in updates_to_apply}

    if dep_type == "pip":
        lines = original_content.splitlines()
        new_lines = []
        for line in lines:
            stripped_line = line.strip()
            if not stripped_line or stripped_line.startswith("#"):
                new_lines.append(line)
                continue
            
            match = re.match(r"^\s*([a-zA-Z0-9._-]+(?:\[[a-zA-Z0-9_,.-]+\])?)\s*([<>=!~]=?.*)?", stripped_line)
            if match:
                package_name = match.group(1)
                if package_name in updates_map:
                    new_lines.append(f"{package_name}=={updates_map[package_name]}")
                    print_info(f"Updating {package_name} to {updates_map[package_name]} in pip file content")
                    continue
            new_lines.append(line)
        new_content = "\n".join(new_lines)

    elif dep_type == "npm":
        try:
            data = json.loads(original_content)
            for section in ["dependencies", "devDependencies"]:
                if section in data and isinstance(data[section], dict):
                    for pkg_name, latest_version in updates_map.items():
                        if pkg_name in data[section]:
                            data[section][pkg_name] = f"^{latest_version}"
                            print_info(f"Updating {pkg_name} to ^{latest_version} in npm file content")
            new_content = json.dumps(data, indent=2)
        except json.JSONDecodeError:
            print_error("Could not parse package.json to update versions. Original content kept.")
            return original_content
            
    return new_content

def create_github_pr(repo_url: str, dependency_file_path: str, dep_type: str, original_file_content: str, updates_to_apply: List[Tuple[str, str, str]], oauth_token: str, pr_title: Optional[str] = None, pr_body: Optional[str] = None) -> Optional[str]:
    """Creates a GitHub PR with the updated dependency file using an OAuth token."""
    if not updates_to_apply:
        print_info("No updates to apply for PR.")
        return None 

    try:
        repo_path_cleaned = repo_url.replace("https://github.com/", "").replace("http://github.com/", "")
        if repo_path_cleaned.endswith("/"):
            repo_path_cleaned = repo_path_cleaned[:-1]
        owner_repo_name = "/".join(repo_path_cleaned.split("/")[:2])

        g = Github(oauth_token)
        repo = g.get_repo(owner_repo_name)

        source_branch_name = repo.default_branch 
        source_branch = repo.get_branch(source_branch_name)

        new_branch_name = f"{PR_BRANCH_NAME_PREFIX}{dep_type}-{int(time.time())}"
        
        print_info(f"Creating new branch: {new_branch_name} from {source_branch_name}")
        try:
            repo.create_git_ref(ref=f"refs/heads/{new_branch_name}", sha=source_branch.commit.sha)
        except GithubException as e:
            if e.status == 422 and "Reference already exists" in str(e.data.get("message", "")):
                print_info(f"Branch {new_branch_name} already exists. Attempting to use it.")
            else:
                raise 

        new_file_content = generate_new_dependency_file_content(original_file_content, dep_type, updates_to_apply)
        
        if new_file_content == original_file_content:
            print_info("File content unchanged after update generation. No PR needed.")
            return None

        # Generate update_details as Markdown table rows
        update_details_for_pr_body = "\n".join([
            f"| `{pkg}` | `{curr_ver}` | `{new_ver}` |" for pkg, curr_ver, new_ver in updates_to_apply
        ])
        commit_message = f"Update {dep_type.upper()} dependencies"
        
        # Use provided PR body or generate default
        if pr_body is None:
            pr_body = PR_BODY_TEMPLATE.format(update_details=update_details_for_pr_body)

        try:
            file_contents_obj = repo.get_contents(dependency_file_path, ref=new_branch_name)
            current_sha = file_contents_obj.sha
            print_info(f"Updating existing file '{dependency_file_path}' in branch '{new_branch_name}'")
            update_result = repo.update_file(
                path=dependency_file_path,
                message=commit_message,
                content=new_file_content,
                sha=current_sha,
                branch=new_branch_name
            )
        except UnknownObjectException: 
            print_info(f"Creating new file '{dependency_file_path}' in branch '{new_branch_name}' as it was not found.")
            update_result = repo.create_file(
                path=dependency_file_path,
                message=commit_message,
                content=new_file_content,
                branch=new_branch_name
            )

        print_info(f"Commit successful: {update_result['commit'].sha}")

        # Use provided PR title or default
        final_pr_title = pr_title if pr_title is not None else PR_TITLE
        print_info(f"Creating PR: {final_pr_title}")
        pull_request = repo.create_pull(
            title=final_pr_title,
            body=pr_body,
            head=new_branch_name,
            base=source_branch_name
        )
        print_success(f"Successfully created Pull Request: {pull_request.html_url}")
        return pull_request.html_url

    except GithubException as e:
        print_error(f"GitHub API Error: {str(e)} - {e.data if hasattr(e, 'data') and e.data else 'No details'}")
        return None
    except Exception as e:
        print_error(f"An unexpected error occurred during PR creation: {str(e)}")
        return None 