import subprocess
import sys
import click
from rich.console import Console
from rich.table import Table
from packaging import version
import pkg_resources
import requests
from typing import Dict, List, Tuple

console = Console()

def get_installed_packages() -> Dict[str, str]:
    """Get all installed packages and their versions."""
    return {pkg.key: pkg.version for pkg in pkg_resources.working_set}

def get_latest_version(package_name: str) -> str:
    """Get the latest version of a package from PyPI."""
    try:
        response = requests.get(f"https://pypi.org/pypi/{package_name}/json")
        if response.status_code == 200:
            return response.json()["info"]["version"]
        return None
    except Exception as e:
        console.print(f"[red]Error fetching version for {package_name}: {str(e)}[/red]")
        return None

def check_updates() -> List[Tuple[str, str, str]]:
    """Check for available updates in installed packages."""
    updates = []
    installed = get_installed_packages()
    
    for package, current_version in installed.items():
        latest_version = get_latest_version(package)
        if latest_version and version.parse(latest_version) > version.parse(current_version):
            updates.append((package, current_version, latest_version))
    
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
def check():
    """Check for available updates in installed packages."""
    updates = check_updates()
    display_updates(updates)

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