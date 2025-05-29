import subprocess
import sys
import click
from rich.console import Console
from rich.table import Table
from packaging import version
import importlib.metadata
import requests
from typing import Dict, List, Tuple, Optional, Any
import re
import json
import os
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import webbrowser

try:
    from github import Github, GithubException, UnknownObjectException
    PYGITHUB_AVAILABLE = True
except ImportError:
    PYGITHUB_AVAILABLE = False

GITHUB_OAUTH_CLIENT_ID = "Ov23lif56kE96lswYc6P" 

GITHUB_OAUTH_SCOPES = "repo" 

GITHUB_DEVICE_CODE_URL = "https://github.com/login/device/code"
GITHUB_ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"

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
        response.raise_for_status() # Raise an exception for bad status codes
        device_code_data = response.json()
    except requests.RequestException as e:
        console.print(f"[red]Error requesting device code from GitHub: {e}[/red]")
        return None
    except json.JSONDecodeError:
        console.print(f"[red]Error decoding GitHub response for device code. Response: {response.text}[/red]")
        return None

    device_code = device_code_data.get("device_code")
    user_code = device_code_data.get("user_code")
    verification_uri = device_code_data.get("verification_uri")
    expires_in = device_code_data.get("expires_in", 300)  # 5 minutes expiry
    interval = device_code_data.get("interval", 5)      # 5 seconds polling interval

    if not all([device_code, user_code, verification_uri]):
        console.print(f"[red]Incomplete device code response from GitHub: {device_code_data}[/red]")
        return None

    console.print(f"[bold yellow]Please authorize this application via your browser.[/bold yellow]")
    console.print(f"Go to: [link={verification_uri}]{verification_uri}[/link]")
    console.print(f"And enter the code: [bold cyan]{user_code}[/bold cyan]")
    
    # Try to open the verification URI in the default web browser
    try:
        if not webbrowser.open(verification_uri):
            console.print(f"[yellow]Could not automatically open the browser. Please navigate to the URL manually.[/yellow]")
    except Exception as e:
        console.print(f"[yellow]Error trying to open browser: {e}. Please navigate to the URL manually.[/yellow]")

    # Step 2: Poll for the access token
    start_time = time.time()
    while True:
        if time.time() - start_time > expires_in:
            console.print("[red]Device code expired. Please try again.[/red]")
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
            console.print(f"[red]Error polling for access token: {e}[/red]")
            continue 
        except json.JSONDecodeError:
            console.print(f"[red]Error decoding GitHub response for access token. Response: {token_response.text}[/red]")
            continue

        error = token_data.get("error")
        if error:
            if error == "authorization_pending":
                pass
            elif error == "slow_down":
                interval += 5  
            elif error == "expired_token":
                console.print("[red]Device code expired while polling. Please try again.[/red]")
                return None
            elif error == "access_denied":
                console.print("[red]Authorization denied by the user. Aborting.[/red]")
                return None
            else:
                console.print(f"[red]GitHub OAuth Error: {error} - {token_data.get('error_description', 'No description')}[/red]")
                return None
        elif "access_token" in token_data:
            console.print("[green]Successfully authorized and obtained access token![/green]")
            return token_data["access_token"]

console = Console()

# Cache for version checks (expires after 1 hour)
VERSION_CACHE: Dict[str, Tuple[str, float]] = {}
CACHE_EXPIRY = 3600  # 1 hour in seconds

# Configuration for PRs 
PR_BRANCH_NAME_PREFIX = "dep-updates/"
PR_TITLE = "Update Dependencies"
PR_BODY_TEMPLATE = "Automated PR to update the following dependencies:\n\n{update_details}"

def get_installed_packages() -> Dict[str, str]:
    """Get all installed packages and their versions."""
    return {dist.metadata['Name']: dist.version for dist in importlib.metadata.distributions()}

@lru_cache(maxsize=1000)
def get_latest_version(package_name: str) -> Optional[str]:
    """Get the latest version of a package from PyPI with caching."""
    current_time = time.time()
    if package_name in VERSION_CACHE:
        cached_version, timestamp = VERSION_CACHE[package_name]
        if current_time - timestamp < CACHE_EXPIRY:
            return cached_version

    try:
        response = requests.get(f"https://pypi.org/pypi/{package_name}/json")
        if response.status_code == 200:
            latest_version = response.json()["info"]["version"]
            VERSION_CACHE[package_name] = (latest_version, current_time)
            return latest_version
        return None
    except Exception as e:
        console.print(f"[red]Error fetching version for {package_name}: {str(e)}[/red]")
        return None

@lru_cache(maxsize=1000)
def get_latest_npm_version(package_name: str) -> Optional[str]:
    """Get the latest version of a package from npm with caching."""
    current_time = time.time()
    if package_name in VERSION_CACHE:
        cached_version, timestamp = VERSION_CACHE[package_name]
        if current_time - timestamp < CACHE_EXPIRY:
            return cached_version

    try:
        response = requests.get(f"https://registry.npmjs.org/{package_name}/latest")
        if response.status_code == 200:
            latest_version = response.json()["version"]
            VERSION_CACHE[package_name] = (latest_version, current_time)
            return latest_version
        return None
    except Exception as e:
        console.print(f"[red]Error fetching version for {package_name}: {str(e)}[/red]")
        return None

def scrape_dependencies_from_github(repo_url: str, file_path_override: Optional[str] = None) -> Optional[Tuple[List[Tuple[str, str]], str, str]]:
    """
    Fetches and parses dependency files (package.json or requirements.txt) from a GitHub repo.
    If file_path_override is given, it fetches that specific file.
    Otherwise, it looks for package.json then requirements.txt in the root on main/master branches.
    Returns a tuple: (list_of_packages, dependency_type, file_path_in_repo) or None.
    """
    if not (repo_url.startswith("https://github.com/") or repo_url.startswith("http://github.com/")):
        console.print("[red]Invalid GitHub repository URL.[/red]")
        return None

    repo_path_cleaned = repo_url.replace("https://github.com/", "").replace("http://github.com/", "")
    if repo_path_cleaned.endswith("/"):
        repo_path_cleaned = repo_path_cleaned[:-1]
    owner_repo = "/".join(repo_path_cleaned.split("/")[:2])

    branches_to_try = ["main", "master"]
    
    potential_files_to_scan = [
        ("package.json", "npm"),
        ("requirements.txt", "pip")
    ]

    files_to_process: List[Tuple[str, Optional[str]]] = [] # (file_path_in_repo, explicit_dep_type_if_known)

    if file_path_override:
        # Determine dep_type from override path
        inferred_dep_type: Optional[str] = None
        if file_path_override.endswith("package.json"):
            inferred_dep_type = "npm"
        elif file_path_override.endswith("requirements.txt"):
            inferred_dep_type = "pip"
        else:
            console.print(f"[yellow]Warning: Could not infer dependency type from --dfp '{file_path_override}'. Will attempt to parse based on content if successful.[/yellow]")
        files_to_process.append((file_path_override, inferred_dep_type))
    else:
        for fname, ftype in potential_files_to_scan:
            files_to_process.append((fname, ftype))

    for file_path_in_repo, explicit_dep_type in files_to_process:
        actual_dep_type_to_use = explicit_dep_type # Will be used for parsing logic

        for branch in branches_to_try:
            file_url = f"https://raw.githubusercontent.com/{owner_repo}/{branch}/{file_path_in_repo}"
            try:
                response = requests.get(file_url, timeout=10)
                if response.status_code == 200:
                    content = response.text
                    console.print(f"[info]Successfully fetched '{file_path_in_repo}' from branch '{branch}'[/info]")
                    packages = []
                    
                    # If explicit_dep_type wasn't known (e.g. from a generic --dfp), try to infer from content or filename again
                    if not actual_dep_type_to_use:
                        if file_path_in_repo.endswith("package.json") or (not file_path_in_repo.endswith("requirements.txt") and '"dependencies":' in content) :
                            actual_dep_type_to_use = "npm"
                        elif file_path_in_repo.endswith("requirements.txt"):
                            actual_dep_type_to_use = "pip"
                        else:
                             # Default to trying pip style parsing if type is ambiguous and not clearly npm json
                            actual_dep_type_to_use = "pip" 
                            console.print(f"[yellow]Could not determine type for '{file_path_in_repo}', defaulting to pip parse attempt.[/yellow]")

                    if actual_dep_type_to_use == "npm":
                        try:
                            pkg_data = json.loads(content)
                            for section_key in ["dependencies", "devDependencies"]:
                                if section_key in pkg_data and isinstance(pkg_data[section_key], dict):
                                    for pkg_name, version_spec in pkg_data[section_key].items():
                                        packages.append((pkg_name, str(version_spec)))
                            if packages:
                                return packages, "npm", file_path_in_repo
                        except json.JSONDecodeError:
                            console.print(f"[red]File '{file_path_in_repo}' (expected npm) is not valid JSON.[/red]")
                            # If an override path was given and it failed as npm, don't try other types for this path.
                            if file_path_override: break # break from branches loop for this file
                            else: continue # continue to next file type if it was a scan
                            
                    elif actual_dep_type_to_use == "pip":
                        for line_number, line_content in enumerate(content.splitlines(), 1):
                            line = line_content.strip()
                            if not line or line.startswith("#"):
                                continue
                            match = re.match(r"^\s*([a-zA-Z0-9._-]+(?:\[[a-zA-Z0-9_,.-]+\])?)\s*([<>=!~]=?.*)?", line)
                            if match:
                                package_name = match.group(1)
                                version_spec = match.group(2) if match.group(2) else ""
                                packages.append((package_name, version_spec.strip()))
                            # else: # Be less verbose about non-matching lines in requirements.txt
                                # console.print(f"[yellow]Could not parse line {line_number} in {file_path_in_repo}: '{line_content}'[/yellow]")
                        if packages:
                            return packages, "pip", file_path_in_repo
                        # If it's a requirements.txt and no packages found, it's still a success but no deps.
                        elif file_path_in_repo.endswith("requirements.txt") and not packages:
                            console.print(f"[info]File '{file_path_in_repo}' (pip) parsed successfully but no dependencies found.[/info]")
                            return [], "pip", file_path_in_repo

                    # If we get here, it means we successfully fetched and parsed, but no packages were found (e.g. empty package.json)
                    # or type was ambiguous and parsing didn't yield results.
                    # If file_path_override was given, we assume it was the correct file, even if empty.
                    if file_path_override and not packages:
                        console.print(f"[info]File '{file_path_in_repo}' (type: {actual_dep_type_to_use}) processed, no dependencies found or extracted.[/info]")
                        return [], actual_dep_type_to_use, file_path_in_repo
                    
                elif response.status_code == 404:
                    # If specific file path override given and not found on this branch, try next branch
                    continue 
                else:
                    # console.print(f"[yellow]Failed to fetch {file_url}: HTTP {response.status_code}[/yellow]")
                    continue # Try next branch
            except requests.RequestException as e:
                # console.print(f"[red]Error fetching {file_url}: {e}[/red]")
                continue # Try next branch
            
            # If file_path_override was given and we tried all branches for it without success, break out early.
            if file_path_override: 
                break # Break from branches loop, as we only care about this specific file

        # If file_path_override was given and not found after trying branches, then report and exit
        if file_path_override:
            console.print(f"[red]Specified dependency file '{file_path_override}' not found in the repository on main/master branches.[/red]")
            return None
    
    # If scanning default files and none were found or yielded packages
    if not file_path_override:
        console.print(f"[red]Could not find a supported dependency file (package.json or requirements.txt) with extractable dependencies in the root of {repo_url} on main/master branches.[/red]")
    return None

def check_updates_parallel(source: Optional[str] = None, dependency_file_path_override: Optional[str] = None) -> Tuple[List[Tuple[str, str, str]], Optional[str], Optional[str]]:
    """
    Check for available updates using parallel processing.
    Returns: (updates_list, dependency_type, dependency_file_path)
    updates_list: [(package_name, current_version_spec, latest_version_str)]
    dependency_type: "npm", "pip", or None
    dependency_file_path: path like "requirements.txt", or None
    """
    updates: List[Tuple[str, str, str]] = []
    dependency_type: Optional[str] = None
    dependency_file_path: Optional[str] = None
    
    if source and (source.startswith("https://github.com/") or source.startswith("http://github.com/")):
        console.print(f"[cyan]Checking dependencies from GitHub repository: {source}[/cyan]")
        scraped_info = scrape_dependencies_from_github(source, dependency_file_path_override)
        
        if not scraped_info:
            return [], None, None
        
        repo_packages, dependency_type, dependency_file_path = scraped_info
        
        if not repo_packages:
            return [], dependency_type, dependency_file_path

        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_package = {}
            
            for package_name, version_spec_from_req in repo_packages:
                # Pass dependency_type to check_package_version
                future = executor.submit(check_package_version, package_name, version_spec_from_req, dependency_type)
                future_to_package[future] = (package_name, version_spec_from_req)
            
            for future in as_completed(future_to_package):
                package_name, version_spec_from_req = future_to_package[future]
                try:
                    result = future.result()
                    if result:
                        updates.append(result)
                except Exception as e:
                    console.print(f"[red]Error checking {package_name}: {str(e)}[/red]")
    else:
        console.print("[cyan]Checking installed packages...[/cyan]")
        installed_packages = get_installed_packages()
        dependency_type = "pip" # Assuming local check is for pip environment
        if not installed_packages:
            console.print("[yellow]No packages found in the current environment.[/yellow]")
            return [], dependency_type, None

        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_package = {}
            
            for package, current_version in installed_packages.items():
                future = executor.submit(check_installed_package, package, current_version)
                future_to_package[future] = package
            
            for future in as_completed(future_to_package):
                package = future_to_package[future]
                try:
                    result = future.result()
                    if result:
                        updates.append(result)
                except Exception as e:
                    console.print(f"[red]Error checking {package}: {str(e)}[/red]")
    
    return updates, dependency_type, dependency_file_path

def check_package_version(package_name: str, version_spec_from_req: str, dep_type: Optional[str]) -> Optional[Tuple[str, str, str]]:
    """Check a single package version and return update info if available."""
    latest_version_str: Optional[str] = None
    
    if dep_type == "npm":
        latest_version_str = get_latest_npm_version(package_name)
    elif dep_type == "pip":
        latest_version_str = get_latest_version(package_name)
    else: # Fallback or unknown type, try both or default to pip
        latest_version_str = get_latest_version(package_name)
        if not latest_version_str: # If not found on PyPI, try npm as a guess
            latest_version_str = get_latest_npm_version(package_name)
            if latest_version_str:
                dep_type = "npm" # Correct the inferred type

    if not latest_version_str:
        return None

    current_version_for_table = version_spec_from_req if version_spec_from_req else "ANY"
    add_to_table = False
    
    parsed_spec_version_str: Optional[str] = None
    is_pinned_exact = False

    if dep_type == "npm":
        match = re.match(r"[\^~]?([0-9]+\.[0-9]+\.[0-9]+.*)", version_spec_from_req)
        if match:
            parsed_spec_version_str = match.group(1)
        elif version_spec_from_req and not any(c in version_spec_from_req for c in ('>', '<', '*', 'x', 'X', '||')):
             # if it's just a number like "1.2.3" without range specifiers, treat as pinned
            parsed_spec_version_str = version_spec_from_req
            is_pinned_exact = True


    elif dep_type == "pip":
        if "==" in version_spec_from_req:
            try:
                parsed_spec_version_str = version_spec_from_req.split("==")[1].strip()
                is_pinned_exact = True
            except IndexError:
                pass # Malformed '=='
    
    if parsed_spec_version_str:
        try:
            parsed_spec = version.parse(parsed_spec_version_str)
            parsed_latest = version.parse(latest_version_str)
            if parsed_latest > parsed_spec:
                add_to_table = True
            current_version_for_table = parsed_spec_version_str 
        except version.InvalidVersion:
            if latest_version_str != version_spec_from_req:
                add_to_table = True
    else: # Not a clearly pinned version (e.g., "ANY", ">=1.0", or complex pip ranges)
        if latest_version_str != version_spec_from_req and version_spec_from_req != "ANY":
             add_to_table = True
        elif version_spec_from_req == "ANY": # Always show for "ANY" to inform user of latest
            add_to_table = True
            
    if add_to_table:
        if latest_version_str != current_version_for_table:
             return (package_name, current_version_for_table, latest_version_str)
    return None

def check_installed_package(package: str, current_version: str) -> Optional[Tuple[str, str, str]]:
    """Check a single installed package and return update info if available."""
    latest_version = get_latest_version(package)
    if latest_version and version.parse(latest_version) > version.parse(current_version):
        return (package, current_version, latest_version)
    return None

def display_updates(updates: List[Tuple[str, str, str]]):
    """Display available updates in a nice table format."""
    if not updates:
        console.print("[green]All packages are up to date![/green]")
        return

    table = Table(title="Available Updates")
    table.add_column("Package", style="cyan")
    table.add_column("Current Version", style="yellow")
    table.add_column("Latest Version", style="green")

    for package, current, latest in updates:
        table.add_row(package, current, latest)
    
    console.print(table)

def update_package(package_name: str) -> bool:
    """Update a specific package to its latest version."""
    try:
        console.print(f"[yellow]Updating {package_name}...[/yellow]")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", package_name])
        console.print(f"[green]Successfully updated {package_name}[/green]")
        return True
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Failed to update {package_name}: {str(e)}[/red]")
        return False

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
                    # Construct the new line with the updated version, preserving original formatting as much as possible
                    # This is a simple replacement, might need refinement for complex version specifiers
                    # or lines with comments at the end.
                    new_lines.append(f"{package_name}=={updates_map[package_name]}")
                    console.print(f"[info]Updating {package_name} to {updates_map[package_name]} in pip file content[/info]")
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
                            # For NPM, we need to consider the original version specifier type (e.g., ^, ~)
                            # This simple update just puts the latest version. More advanced logic could try to preserve prefix.
                            # For now, we'll use a common practice like ^version.
                            data[section][pkg_name] = f"^{latest_version}"
                            console.print(f"[info]Updating {pkg_name} to ^{latest_version} in npm file content[/info]")
            new_content = json.dumps(data, indent=2) # Common indent for package.json
        except json.JSONDecodeError:
            console.print("[red]Could not parse package.json to update versions. Original content kept.[/red]")
            return original_content
            
    return new_content

def create_github_pr(repo_url: str, dependency_file_path: str, dep_type: str, original_file_content: str, updates_to_apply: List[Tuple[str, str, str]], oauth_token: str, pr_title: Optional[str] = None, pr_body: Optional[str] = None) -> Optional[str]:
    """Creates a GitHub PR with the updated dependency file using an OAuth token."""
    if not PYGITHUB_AVAILABLE:
        console.print("[red]PyGithub library is not installed. Cannot create PR. Please run: pip install PyGithub[/red]")
        return None
    if not updates_to_apply:
        console.print("[info]No updates to apply for PR.[/info]")
        return None 

    try:
        repo_path_cleaned = repo_url.replace("https://github.com/", "").replace("http://github.com/", "")
        if repo_path_cleaned.endswith("/"):
            repo_path_cleaned = repo_path_cleaned[:-1]
        owner_repo_name = "/".join(repo_path_cleaned.split("/")[:2])

        g = Github(oauth_token) # Use OAuth token here
        repo = g.get_repo(owner_repo_name)

        source_branch_name = repo.default_branch 
        source_branch = repo.get_branch(source_branch_name)

        new_branch_name = f"{PR_BRANCH_NAME_PREFIX}{dep_type}-{int(time.time())}"
        
        console.print(f"[info]Creating new branch: {new_branch_name} from {source_branch_name}[/info]")
        try:
            repo.create_git_ref(ref=f"refs/heads/{new_branch_name}", sha=source_branch.commit.sha)
        except GithubException as e:
            if e.status == 422 and "Reference already exists" in str(e.data.get("message", "")):
                console.print(f"[yellow]Branch {new_branch_name} already exists. Attempting to use it.[/yellow]")
            else:
                raise 

        new_file_content = generate_new_dependency_file_content(original_file_content, dep_type, updates_to_apply)
        
        if new_file_content == original_file_content:
            console.print("[info]File content unchanged after update generation. No PR needed.[/info]")
            return None

        update_details_for_pr_body = "\n".join([f"- `{pkg}` to `{new_ver}` (was `{curr_ver}`)" for pkg, curr_ver, new_ver in updates_to_apply])
        commit_message = f"Update {dep_type.upper()} dependencies"
        
        # Use provided PR body or generate default
        if pr_body is None:
            pr_body = PR_BODY_TEMPLATE.format(update_details=update_details_for_pr_body)

        try:
            file_contents_obj = repo.get_contents(dependency_file_path, ref=new_branch_name)
            current_sha = file_contents_obj.sha
            console.print(f"[info]Updating existing file '{dependency_file_path}' in branch '{new_branch_name}'[/info]")
            update_result = repo.update_file(
                path=dependency_file_path,
                message=commit_message,
                content=new_file_content,
                sha=current_sha,
                branch=new_branch_name
            )
        except UnknownObjectException: 
            console.print(f"[info]Creating new file '{dependency_file_path}' in branch '{new_branch_name}' as it was not found.[/info]")
            update_result = repo.create_file(
                path=dependency_file_path,
                message=commit_message,
                content=new_file_content,
                branch=new_branch_name
            )

        console.print(f"[info]Commit successful: {update_result['commit'].sha}[/info]")

        # Use provided PR title or default
        final_pr_title = pr_title if pr_title is not None else PR_TITLE
        console.print(f"[info]Creating PR: {final_pr_title}[/info]")
        pull_request = repo.create_pull(
            title=final_pr_title,
            body=pr_body,
            head=new_branch_name,
            base=source_branch_name
        )
        console.print(f"[green]Successfully created Pull Request: {pull_request.html_url}[/green]")
        return pull_request.html_url

    except GithubException as e:
        console.print(f"[red]GitHub API Error: {str(e)} - {e.data if hasattr(e, 'data') and e.data else 'No details'}[/red]")
        return None
    except Exception as e:
        console.print(f"[red]An unexpected error occurred during PR creation: {str(e)}[/red]")
        return None

@click.group()
def cli():
    """Dependency Management Bot - Automatically manage and update your Python dependencies."""
    pass

@cli.command(name='check')
@click.argument('source', required=False, default=None, type=str)
@click.option('--dfp', 'dependency_file_path_override', type=str, default=None, help='Optional path to the specific dependency file (e.g., backend/requirements.txt) relative to the repo root.')
def check(source: Optional[str], dependency_file_path_override: Optional[str]):
    """
    Check for available updates.
    Checks installed packages by default.
    Or, provide a GitHub repository URL (e.g., https://github.com/user/repo)
    to check dependencies from its requirements.txt or package.json against PyPI/npm.
    Use --dfp to specify a path to a dependency file if not in root.
    """
    updates, dependency_type, dependency_file_path = check_updates_parallel(source, dependency_file_path_override)
    display_updates(updates)
    if dependency_type:
        console.print(f"[cyan]Dependency type: {dependency_type.upper()}[/cyan]")
    if dependency_file_path:
        console.print(f"[cyan]Dependency file: {dependency_file_path}[/cyan]")

@cli.command(name='update')
@click.argument('package_name')
def update(package_name):
    """Update a specific package to its latest version."""
    update_package(package_name)

@cli.command(name='update-all')
def update_all():
    """Update all outdated packages."""
    updates, dependency_type, dependency_file_path = check_updates_parallel()
    if not updates:
        console.print("[green]All packages are up to date![/green]")
        return

    for package, _, _ in updates:
        update_package(package)

@cli.command(name='check-and-update')
@click.argument('source', required=False, default=None, type=str)
@click.option('--update/--no-update', default=False, help='Automatically update packages after checking')
@click.option('--dfp', 'dependency_file_path_override', type=str, default=None, help='Optional path to the specific dependency file for GitHub repos.')
def check_and_update(source: Optional[str], update: bool, dependency_file_path_override: Optional[str]):
    """
    Check for available updates and optionally update them.
    This is a faster version that uses parallel processing and caching.
    Use --dfp for GitHub repos if the dependency file is not in the root.
    """
    start_time = time.time()
    updates, dependency_type, dependency_file_path = check_updates_parallel(source, dependency_file_path_override)
    end_time = time.time()
    
    display_updates(updates)
    if dependency_type:
        console.print(f"[cyan]Dependency type: {dependency_type.upper()}[/cyan]")
    if dependency_file_path:
        console.print(f"[cyan]Dependency file: {dependency_file_path}[/cyan]")

    console.print(f"[cyan]Check completed in {end_time - start_time:.2f} seconds[/cyan]")
    
    if update and updates:
        if source and (source.startswith("https://github.com/") or source.startswith("http://github.com/")):
            console.print("[yellow]Warning: The '--update' flag for GitHub repos currently only updates local packages if they match. It does not create a PR.[/yellow]")
            console.print("[yellow]Use the 'propose-updates' command to create a PR for a GitHub repository.[/yellow]")
            # Fall-through to local update logic for now, or could be prevented.

        console.print("[yellow]Updating packages...[/yellow]")
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(update_package, package) for package, _, _ in updates]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    console.print(f"[red]Error during update: {str(e)}[/red]")
        console.print("[green]All updates completed![/green]")

@cli.command(name='propose-updates')
@click.argument('repo_url', type=str)
@click.option('--dfp', 'dependency_file_path_override', type=str, default=None, help='Optional path to the specific dependency file (e.g., backend/requirements.txt) relative to the repo root.')
def propose_updates_command(repo_url: str, dependency_file_path_override: Optional[str]):
    """
    Checks a GitHub repository for outdated dependencies and proposes a PR with updates
    using GitHub OAuth Device Flow for authorization.
    Use --dfp if the dependency file is not in the repository root.
    """
    if not PYGITHUB_AVAILABLE:
        console.print("[red]PyGithub library is not installed. Cannot create PR. Please run: pip install PyGithub[/red]")
        return
    
    if GITHUB_OAUTH_CLIENT_ID == "YOUR_GITHUB_OAUTH_CLIENT_ID":
        console.print("[bold red]OAuth Client ID is not configured in the script.[/bold red]")
        console.print("Please register an OAuth App on GitHub and set the GITHUB_OAUTH_CLIENT_ID in the script.")
        return

    console.print(f"[cyan]Starting update proposal for repository: {repo_url}[/cyan]")
    
    oauth_token = get_github_oauth_token() 
    if not oauth_token:
        console.print("[red]Failed to obtain GitHub OAuth token. Aborting.[/red]")
        return

    updates, dep_type, dep_file_path = check_updates_parallel(repo_url, dependency_file_path_override)

    if not updates:
        console.print("[green]No updates found. Repository is up to date or no supported dependency file was found.[/green]")
        return

    display_updates(updates)
    console.print(f"[info]Dependency type: {dep_type.upper() if dep_type else 'N/A'}[/info]")
    console.print(f"[info]Dependency file: {dep_file_path if dep_file_path else 'N/A'}[/info]")

    if not dep_type or not dep_file_path:
        console.print("[red]Could not determine dependency type or file path. Cannot create PR.[/red]")
        return

    if not click.confirm(f"\nFound {len(updates)} updates. Do you want to create a Pull Request in {repo_url}?"):
        console.print("[info]PR creation aborted by user.[/info]")
        return
    
    # Fetch original file content (simplified, as before)
    repo_path_cleaned = repo_url.replace("https://github.com/", "").replace("http://github.com/", "")
    if repo_path_cleaned.endswith("/"):
        repo_path_cleaned = repo_path_cleaned[:-1]
    owner_repo = "/".join(repo_path_cleaned.split("/")[:2])
    
    original_file_content = None
    for branch_to_try in ["main", "master"]:
        original_content_url = f"https://raw.githubusercontent.com/{owner_repo}/{branch_to_try}/{dep_file_path}"
        try:
            response = requests.get(original_content_url, timeout=10)
            if response.status_code == 200:
                original_file_content = response.text
                break
            elif response.status_code == 404:
                console.print(f"[yellow]Dependency file '{dep_file_path}' not found on branch '{branch_to_try}'.[/yellow]")
                continue
            else:
                console.print(f"[red]Failed to fetch original {dep_file_path} from {branch_to_try} branch (HTTP {response.status_code}).[/red]")
        except requests.RequestException as e:
            console.print(f"[red]Error fetching original {dep_file_path} from {branch_to_try} branch: {e}.[/red]")
    
    if original_file_content is None:
        console.print(f"[red]Could not fetch original dependency file '{dep_file_path}'. Cannot create PR.[/red]")
        return

    pr_url = create_github_pr(repo_url, dep_file_path, dep_type, original_file_content, updates, oauth_token)

    if pr_url:
        console.print(f"[green]Successfully initiated PR creation. URL: {pr_url}[/green]")
    else:
        console.print("[red]PR creation failed or was skipped.[/red]")

def main():
    cli()

if __name__ == "__main__":
    main() 