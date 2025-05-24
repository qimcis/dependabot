"""Local package management functionality."""

import subprocess
import sys
from typing import Dict, Optional, Tuple
import importlib.metadata
from packaging import version

from ..utils.console import print_error, print_success, print_info
from .version_checker import get_latest_version

def get_installed_packages() -> Dict[str, str]:
    """Get all installed packages and their versions."""
    return {dist.metadata['Name']: dist.version for dist in importlib.metadata.distributions()}

def check_installed_package(package: str, current_version: str) -> Optional[Tuple[str, str, str]]:
    """Check a single installed package and return update info if available."""
    latest_version = get_latest_version(package)
    if latest_version and version.parse(latest_version) > version.parse(current_version):
        return (package, current_version, latest_version)
    return None

def update_package(package_name: str) -> bool:
    """Update a specific package to its latest version."""
    try:
        print_info(f"Updating {package_name}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", package_name])
        print_success(f"Successfully updated {package_name}")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to update {package_name}: {str(e)}")
        return False 