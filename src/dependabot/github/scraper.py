"""GitHub repository scraping functionality."""

import requests
import json
import re
from typing import List, Tuple, Optional

from ..utils.console import print_error, print_info, print_warning

def scrape_dependencies_from_github(repo_url: str, file_path_override: Optional[str] = None) -> Optional[Tuple[List[Tuple[str, str]], str, str]]:
    """
    Fetches and parses dependency files (package.json or requirements.txt) from a GitHub repo.
    If file_path_override is given, it fetches that specific file.
    Otherwise, it looks for package.json then requirements.txt in the root on main/master branches.
    Returns a tuple: (list_of_packages, dependency_type, file_path_in_repo) or None.
    """
    if not (repo_url.startswith("https://github.com/") or repo_url.startswith("http://github.com/")):
        print_error("Invalid GitHub repository URL.")
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
            print_warning(f"Could not infer dependency type from --dfp '{file_path_override}'. Will attempt to parse based on content if successful.")
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
                    print_info(f"Successfully fetched '{file_path_in_repo}' from branch '{branch}'")
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
                            print_warning(f"Could not determine type for '{file_path_in_repo}', defaulting to pip parse attempt.")

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
                            print_error(f"File '{file_path_in_repo}' (expected npm) is not valid JSON.")
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
                        if packages:
                            return packages, "pip", file_path_in_repo
                        # If it's a requirements.txt and no packages found, it's still a success but no deps.
                        elif file_path_in_repo.endswith("requirements.txt") and not packages:
                            print_info(f"File '{file_path_in_repo}' (pip) parsed successfully but no dependencies found.")
                            return [], "pip", file_path_in_repo

                    # If we get here, it means we successfully fetched and parsed, but no packages were found (e.g. empty package.json)
                    # or type was ambiguous and parsing didn't yield results.
                    # If file_path_override was given, we assume it was the correct file, even if empty.
                    if file_path_override and not packages:
                        print_info(f"File '{file_path_in_repo}' (type: {actual_dep_type_to_use}) processed, no dependencies found or extracted.")
                        return [], actual_dep_type_to_use, file_path_in_repo
                    
                elif response.status_code == 404:
                    # If specific file path override given and not found on this branch, try next branch
                    continue 
                else:
                    continue # Try next branch
            except requests.RequestException as e:
                continue # Try next branch
            
            # If file_path_override was given and we tried all branches for it without success, break out early.
            if file_path_override: 
                break # Break from branches loop, as we only care about this specific file

        # If file_path_override was given and not found after trying branches, then report and exit
        if file_path_override:
            print_error(f"Specified dependency file '{file_path_override}' not found in the repository on main/master branches.")
            return None
    
    # If scanning default files and none were found or yielded packages
    if not file_path_override:
        print_error(f"Could not find a supported dependency file (package.json or requirements.txt) with extractable dependencies in the root of {repo_url} on main/master branches.")
    return None 