"""Version checking functionality for packages."""

import time
from typing import Dict, Tuple, Optional
import requests
from functools import lru_cache
from packaging import version
import re

from ..utils.console import console, print_error
from ..utils.constants import CACHE_EXPIRY

# Cache for version checks
VERSION_CACHE: Dict[str, Tuple[str, float]] = {}

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
        print_error(f"Error fetching version for {package_name}: {str(e)}")
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
        print_error(f"Error fetching version for {package_name}: {str(e)}")
        return None

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