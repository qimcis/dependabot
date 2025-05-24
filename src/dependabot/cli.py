"""Command-line interface for the dependabot package."""

import time
import click
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Optional

from .utils.console import console, print_error, print_info, print_success, print_warning
from .dependencies.version_checker import check_package_version
from .dependencies.local import get_installed_packages, check_installed_package, update_package
from .github.scraper import scrape_dependencies_from_github
from .github.oauth import get_github_oauth_token
from .github.pr import create_github_pr

def display_updates(updates: List[Tuple[str, str, str]]):
    """Display available updates in a nice table format."""
    if not updates:
        print_success("All packages are up to date!")
        return

    table = Table(title="Available Updates")
    table.add_column("Package", style="cyan")
    table.add_column("Current Version", style="yellow")
    table.add_column("Latest Version", style="green")

    for package, current, latest in updates:
        table.add_row(package, current, latest)
    
    console.print(table)

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
        print_info(f"Checking dependencies from GitHub repository: {source}")
        scraped_info = scrape_dependencies_from_github(source, dependency_file_path_override)
        
        if not scraped_info:
            return [], None, None
        
        repo_packages, dependency_type, dependency_file_path = scraped_info
        
        if not repo_packages:
            return [], dependency_type, dependency_file_path

        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_package = {}
            
            for package_name, version_spec_from_req in repo_packages:
                future = executor.submit(check_package_version, package_name, version_spec_from_req, dependency_type)
                future_to_package[future] = (package_name, version_spec_from_req)
            
            for future in as_completed(future_to_package):
                package_name, version_spec_from_req = future_to_package[future]
                try:
                    result = future.result()
                    if result:
                        updates.append(result)
                except Exception as e:
                    print_error(f"Error checking {package_name}: {str(e)}")
    else:
        print_info("Checking installed packages...")
        installed_packages = get_installed_packages()
        dependency_type = "pip" # Assuming local check is for pip environment
        if not installed_packages:
            print_warning("No packages found in the current environment.")
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
                    print_error(f"Error checking {package}: {str(e)}")
    
    return updates, dependency_type, dependency_file_path

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
        print_info(f"Dependency type: {dependency_type.upper()}")
    if dependency_file_path:
        print_info(f"Dependency file: {dependency_file_path}")

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
        print_success("All packages are up to date!")
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
        print_info(f"Dependency type: {dependency_type.upper()}")
    if dependency_file_path:
        print_info(f"Dependency file: {dependency_file_path}")

    print_info(f"Check completed in {end_time - start_time:.2f} seconds")
    
    if update and updates:
        if source and (source.startswith("https://github.com/") or source.startswith("http://github.com/")):
            print_warning("The '--update' flag for GitHub repos currently only updates local packages if they match. It does not create a PR.")
            print_warning("Use the 'propose-updates' command to create a PR for a GitHub repository.")

        print_info("Updating packages...")
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(update_package, package) for package, _, _ in updates]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print_error(f"Error during update: {str(e)}")
        print_success("All updates completed!")

@cli.command(name='propose-updates')
@click.argument('repo_url', type=str)
@click.option('--dfp', 'dependency_file_path_override', type=str, default=None, help='Optional path to the specific dependency file (e.g., backend/requirements.txt) relative to the repo root.')
def propose_updates_command(repo_url: str, dependency_file_path_override: Optional[str]):
    """
    Checks a GitHub repository for outdated dependencies and proposes a PR with updates
    using GitHub OAuth Device Flow for authorization.
    Use --dfp if the dependency file is not in the repository root.
    """
    try:
        from github import Github
    except ImportError:
        print_error("PyGithub library is not installed. Cannot create PR. Please run: pip install PyGithub")
        return

    print_info(f"Starting update proposal for repository: {repo_url}")
    
    oauth_token = get_github_oauth_token() 
    if not oauth_token:
        print_error("Failed to obtain GitHub OAuth token. Aborting.")
        return

    updates, dep_type, dep_file_path = check_updates_parallel(repo_url, dependency_file_path_override)

    if not updates:
        print_success("No updates found. Repository is up to date or no supported dependency file was found.")
        return

    display_updates(updates)
    print_info(f"Dependency type: {dep_type.upper() if dep_type else 'N/A'}")
    print_info(f"Dependency file: {dep_file_path if dep_file_path else 'N/A'}")

    if not dep_type or not dep_file_path:
        print_error("Could not determine dependency type or file path. Cannot create PR.")
        return

    if not click.confirm(f"\nFound {len(updates)} updates. Do you want to create a Pull Request in {repo_url}?"):
        print_info("PR creation aborted by user.")
        return
    
    # Fetch original file content
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
                print_warning(f"Dependency file '{dep_file_path}' not found on branch '{branch_to_try}'.")
                continue
            else:
                print_error(f"Failed to fetch original {dep_file_path} from {branch_to_try} branch (HTTP {response.status_code}).")
        except requests.RequestException as e:
            print_error(f"Error fetching original {dep_file_path} from {branch_to_try} branch: {e}.")
    
    if original_file_content is None:
        print_error(f"Could not fetch original dependency file '{dep_file_path}'. Cannot create PR.")
        return

    pr_url = create_github_pr(repo_url, dep_file_path, dep_type, original_file_content, updates, oauth_token)

    if pr_url:
        print_success(f"Successfully initiated PR creation. URL: {pr_url}")
    else:
        print_error("PR creation failed or was skipped.")

def main():
    cli()

if __name__ == "__main__":
    main() 