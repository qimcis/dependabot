import subprocess
import sys
import click
from rich.console import Console
from rich.table import Table
from packaging import version
import importlib.metadata
import requests
from typing import Dict, List, Tuple, Optional
import re
import json
import os
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

console = Console()

# Cache for version checks (expires after 1 hour)
VERSION_CACHE = {}
CACHE_EXPIRY = 3600  # 1 hour in seconds

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

def get_packages_from_github_requirements(repo_url: str) -> List[Tuple[str, str]]:
    """
    Fetches requirements.txt from a GitHub repo and parses package names and versions.
    Returns a list of (package_name, version_spec_string).
    Example version_spec_string: "==1.2.3", ">=1.2", or "" if no version specified.
    """
    if not (repo_url.startswith("https://github.com/") or repo_url.startswith("http://github.com/")):
        console.print("[red]Invalid GitHub repository URL.[/red]")
        return []

    repo_path = repo_url.replace("https://github.com/", "").replace("http://github.com/", "")
    if repo_path.endswith("/"):
        repo_path = repo_path[:-1]
    
    # Try to get package.json first
    package_json_urls = [
        f"https://raw.githubusercontent.com/{repo_path}/main/package.json",
        f"https://raw.githubusercontent.com/{repo_path}/master/package.json"
    ]
    
    for pkg_url in package_json_urls:
        try:
            response = requests.get(pkg_url, timeout=10)
            if response.status_code == 200:
                console.print(f"[info]Successfully fetched package.json from {pkg_url}[/info]")
                try:
                    pkg_data = response.json()
                    packages = []
                    # Check dependencies
                    if "dependencies" in pkg_data:
                        for pkg_name, version_spec in pkg_data["dependencies"].items():
                            packages.append((pkg_name, version_spec))
                    # Check devDependencies
                    if "devDependencies" in pkg_data:
                        for pkg_name, version_spec in pkg_data["devDependencies"].items():
                            packages.append((pkg_name, version_spec))
                    return packages
                except json.JSONDecodeError:
                    console.print(f"[red]Invalid JSON in package.json[/red]")
                    break
        except requests.RequestException:
            continue

    # If no package.json found, try requirements.txt
    requirements_urls = [
        f"https://raw.githubusercontent.com/{repo_path}/main/requirements.txt",
        f"https://raw.githubusercontent.com/{repo_path}/master/requirements.txt"
    ]
    
    content = None
    fetched_url = None
    for req_url in requirements_urls:
        try:
            response = requests.get(req_url, timeout=10)
            if response.status_code == 200:
                content = response.text
                fetched_url = req_url
                break
            elif response.status_code == 404:
                continue 
            else:
                continue
        except requests.RequestException:
            continue

    if not content:
        console.print(f"[red]Could not find or access requirements.txt or package.json in {repo_url} (tried /main/ and /master/ branches).[/red]")
        return []
    
    console.print(f"[info]Successfully fetched requirements.txt from {fetched_url}[/info]")
    packages = []
    for line_number, line_content in enumerate(content.splitlines(), 1):
        line = line_content.strip()
        if not line or line.startswith("#"):
            continue
        
        match = re.match(r"^\s*([a-zA-Z0-9._-]+(?:\[[a-zA-Z0-9_,.-]+\])?)\s*([<>=!~]=?.*)?", line)
        if match:
            package_name = match.group(1)
            version_spec = match.group(2) if match.group(2) else ""
            version_spec = version_spec.strip()
            packages.append((package_name, version_spec))
        else:
            console.print(f"[yellow]Could not parse line {line_number} in requirements.txt: '{line_content}'[/yellow]")
            
    return packages

def check_updates_parallel(source: Optional[str] = None) -> List[Tuple[str, str, str]]:
    """
    Check for available updates using parallel processing.
    """
    updates: List[Tuple[str, str, str]] = []
    
    if source and (source.startswith("https://github.com/") or source.startswith("http://github.com/")):
        console.print(f"[cyan]Checking dependencies from GitHub repository: {source}[/cyan]")
        repo_packages = get_packages_from_github_requirements(source)
        
        if not repo_packages:
            return []

        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_package = {}
            
            for package_name, version_spec_from_req in repo_packages:
                future = executor.submit(check_package_version, package_name, version_spec_from_req)
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
        if not installed_packages:
            console.print("[yellow]No packages found in the current environment.[/yellow]")
            return []

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
    
    return updates

def check_package_version(package_name: str, version_spec_from_req: str) -> Optional[Tuple[str, str, str]]:
    """Check a single package version and return update info if available."""
    latest_version = get_latest_npm_version(package_name)
    if latest_version:
        current_version_for_table = version_spec_from_req if version_spec_from_req else "ANY"
        add_to_table = False

        if version_spec_from_req.startswith("^") or version_spec_from_req.startswith("~"):
            try:
                clean_version = version_spec_from_req[1:]
                if version.parse(latest_version) > version.parse(clean_version):
                    add_to_table = True
            except version.InvalidVersion:
                add_to_table = True
        else:
            add_to_table = True

        if add_to_table:
            return (package_name, current_version_for_table, latest_version)
    
    latest_pypi_version_str = get_latest_version(package_name)
    if not latest_pypi_version_str:
        return None

    current_version_for_table = version_spec_from_req if version_spec_from_req else "ANY"
    add_to_table = False

    if "==" in version_spec_from_req:
        try:
            pinned_version_str = version_spec_from_req.split("==")[1].strip()
            parsed_pinned_version = version.parse(pinned_version_str)
            parsed_latest_pypi_version = version.parse(latest_pypi_version_str)
            
            current_version_for_table = str(parsed_pinned_version) 
            if parsed_latest_pypi_version > parsed_pinned_version:
                add_to_table = True
        except (version.InvalidVersion, IndexError):
            if latest_pypi_version_str != version_spec_from_req:
                add_to_table = True
    else:
        add_to_table = True 
    
    if add_to_table:
        return (package_name, current_version_for_table, latest_pypi_version_str)
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

@click.group()
def cli():
    """Dependency Management Bot - Automatically manage and update your Python dependencies."""
    pass

@cli.command(name='check')
@click.argument('source', required=False, default=None, type=str)
def check(source: Optional[str]):
    """
    Check for available updates.
    Checks installed packages by default.
    Or, provide a GitHub repository URL (e.g., https://github.com/user/repo)
    to check dependencies from its requirements.txt or package.json against PyPI/npm.
    """
    updates = check_updates_parallel(source)
    display_updates(updates)

@cli.command(name='update')
@click.argument('package_name')
def update(package_name):
    """Update a specific package to its latest version."""
    update_package(package_name)

@cli.command(name='update-all')
def update_all():
    """Update all outdated packages."""
    updates = check_updates_parallel()
    if not updates:
        console.print("[green]All packages are up to date![/green]")
        return

    for package, _, _ in updates:
        update_package(package)

@cli.command(name='check-and-update')
@click.argument('source', required=False, default=None, type=str)
@click.option('--update/--no-update', default=False, help='Automatically update packages after checking')
def check_and_update(source: Optional[str], update: bool):
    """
    Check for available updates and optionally update them.
    This is a faster version that uses parallel processing and caching.
    """
    start_time = time.time()
    updates = check_updates_parallel(source)
    end_time = time.time()
    
    display_updates(updates)
    console.print(f"[cyan]Check completed in {end_time - start_time:.2f} seconds[/cyan]")
    
    if update and updates:
        console.print("[yellow]Updating packages...[/yellow]")
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(update_package, package) for package, _, _ in updates]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    console.print(f"[red]Error during update: {str(e)}[/red]")
        console.print("[green]All updates completed![/green]")

def main():
    cli()

if __name__ == "__main__":
    main() 