import subprocess
import sys
import click
from rich.console import Console
from rich.table import Table
from packaging import version
import pkg_resources
import requests
from typing import Dict, List, Tuple, Optional
import re

console = Console()

def get_installed_packages() -> Dict[str, str]:
    """Get all installed packages and their versions."""
    return {pkg.key: pkg.version for pkg in pkg_resources.working_set}

def get_latest_version(package_name: str) -> Optional[str]:
    """Get the latest version of a package from PyPI."""
    try:
        response = requests.get(f"https://pypi.org/pypi/{package_name}/json")
        if response.status_code == 200:
            return response.json()["info"]["version"]
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
                # console.print(f"[yellow]Failed to fetch {req_url}: HTTP {response.status_code}[/yellow]")
                continue
        except requests.RequestException as e:
            # console.print(f"[red]Error fetching {req_url}: {e}[/red]")
            continue

    if not content:
        console.print(f"[red]Could not find or access requirements.txt in {repo_url} (tried /main/ and /master/ branches).[/red]")
        return []
    
    console.print(f"[info]Successfully fetched requirements.txt from {fetched_url}[/info]")
    packages = []
    for line_number, line_content in enumerate(content.splitlines(), 1):
        line = line_content.strip()
        if not line or line.startswith("#"):
            continue
        
        # Regex to capture package name and the rest of the specifier
        # Handles names like 'package', 'package-name', 'package_name', 'package.name1.name2'
        # And specifiers like ==1.2.3, >=1.2, <2.0, ~=1.1, !=1.0
        # Also handles lines with extras like: package[extra1,extra2]==1.0.0
        match = re.match(r"^\s*([a-zA-Z0-9._-]+(?:\[[a-zA-Z0-9_,.-]+\])?)\s*([<>=!~]=?.*)?", line)
        if match:
            package_name = match.group(1)
            version_spec = match.group(2) if match.group(2) else ""
            version_spec = version_spec.strip()
            packages.append((package_name, version_spec))
        else:
            console.print(f"[yellow]Could not parse line {line_number} in requirements.txt: '{line_content}'[/yellow]")
            
    return packages

def check_updates(source: Optional[str] = None) -> List[Tuple[str, str, str]]:
    """
    Check for available updates.
    If source is a GitHub URL, checks dependencies from its requirements.txt against PyPI.
    Otherwise, checks installed packages.
    """
    updates: List[Tuple[str, str, str]] = []
    if source and (source.startswith("https://github.com/") or source.startswith("http://github.com/")):
        console.print(f"[cyan]Checking dependencies from GitHub repository: {source}[/cyan]")
        repo_packages = get_packages_from_github_requirements(source)
        
        if not repo_packages:
            return []

        for package_name, version_spec_from_req in repo_packages:
            latest_pypi_version_str = get_latest_version(package_name)
            if not latest_pypi_version_str:
                # console.print(f"[yellow]Could not find {package_name} on PyPI.[/yellow]")
                continue

            current_version_for_table = version_spec_from_req if version_spec_from_req else "ANY"
            add_to_table = False

            if "==" in version_spec_from_req:
                try:
                    # Extract version part after ==
                    pinned_version_str = version_spec_from_req.split("==")[1].strip()
                    parsed_pinned_version = version.parse(pinned_version_str)
                    parsed_latest_pypi_version = version.parse(latest_pypi_version_str)
                    
                    current_version_for_table = str(parsed_pinned_version) 
                    if parsed_latest_pypi_version > parsed_pinned_version:
                        add_to_table = True
                except (version.InvalidVersion, IndexError) as e:
                    # console.print(f"[yellow]Could not parse pinned version '{version_spec_from_req}' for {package_name}: {e}[/yellow]")
                    # If parsing fails, treat as non-pinned for decision logic, but display original spec.
                    # Add if latest PyPI version string is different from the spec string.
                    if latest_pypi_version_str != version_spec_from_req:
                         add_to_table = True
            else:
                # For non-pinned versions (ANY, >=, <=, ~=, !=) or unparseable '=='
                # Add to table to inform user of the latest available against their specification.
                add_to_table = True 
            
            if add_to_table:
                updates.append((package_name, current_version_for_table, latest_pypi_version_str))
    else:
        console.print("[cyan]Checking installed packages...[/cyan]")
        installed_packages = get_installed_packages()
        if not installed_packages:
            console.print("[yellow]No packages found in the current environment.[/yellow]")
            return []
        for package, current_installed_version in installed_packages.items():
            latest_pkg_version = get_latest_version(package)
            if latest_pkg_version and version.parse(latest_pkg_version) > version.parse(current_installed_version):
                updates.append((package, current_installed_version, latest_pkg_version))
    
    return updates

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

@cli.command()
@click.argument('source', required=False, default=None, type=str)
def check(source: Optional[str]):
    """
    Check for available updates.
    Checks installed packages by default.
    Or, provide a GitHub repository URL (e.g., https://github.com/user/repo)
    to check dependencies from its requirements.txt against PyPI.
    """
    updates_found = check_updates(source)
    display_updates(updates_found)

@cli.command()
@click.argument('package_name')
def update(package_name):
    """Update a specific package to its latest version."""
    update_package(package_name)

@cli.command()
def update_all():
    """Update all outdated packages."""
    updates = check_updates()
    if not updates:
        console.print("[green]All packages are up to date![/green]")
        return

    for package, _, _ in updates:
        update_package(package)

def main():
    cli()

if __name__ == "__main__":
    main() 