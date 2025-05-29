# Dependency Management Bot (Dependabot CLI Clone)

This script is a command-line tool to help manage and update your Python and Node.js package dependencies. It can check for outdated packages in your local environment or in a remote GitHub repository, and can propose updates via a Pull Request to a GitHub repository.

## Features

-   **Local Environment Check:**
    -   Scans your currently installed Python (`pip`) packages.
    -   Identifies packages with newer versions available on PyPI.
-   **GitHub Repository Check:**
    -   Scans a public GitHub repository for `requirements.txt` (pip) or `package.json` (npm).
    -   Supports specifying a path to the dependency file if it's not in the repository root (using `--dfp`).
    -   Compares declared dependencies against their latest versions on PyPI or npm.
-   **Display Updates:**
    -   Shows available updates in a clean table format using `rich`.
-   **Update Packages Locally:**
    -   `update <package_name>`: Updates a specific locally installed pip package.
    -   `update-all`: Updates all outdated locally installed pip packages.
    -   `check-and-update`: Checks and then updates all local pip packages.
-   **Propose Updates to GitHub Repositories (via Pull Request):**
    -   The `propose-updates` command checks a GitHub repository.
    -   If updates are found, it prompts the user for confirmation.
    -   Uses **GitHub OAuth Device Flow** for secure authentication (user authorizes in browser).
    -   Creates a new branch in the target repository.
    -   Commits the updated dependency file (`requirements.txt` or `package.json`).
    -   Opens a Pull Request with the proposed changes.
-   **Web Interface:**
    -   Modern, user-friendly web interface for checking and updating dependencies.
    -   Real-time status updates and progress tracking.
    -   Beautiful table display of available updates.
    -   Direct links to created Pull Requests.
-   **Caching:** Caches version information from PyPI/npm for a short period to speed up repeated checks.
-   **Parallel Processing:** Uses thread pools for faster checking of multiple packages.

## Prerequisites

-   Python 3.7+
-   `pip` (for installing Python dependencies)

## Installation

1.  **Clone the repository (or download the script):**
    ```bash
    git clone https://github.com/qimcis/dependabot 
    cd dependabot 
    ```

2.  **Install required Python libraries:**
    ```bash
    pip install click rich packaging requests PyGithub importlib-metadata flask
    ```
    (`importlib-metadata` is generally included with Python 3.8+ but good to list for older versions or specific environments).

## Development Setup: Using a Virtual Environment

It is recommended to use a Python virtual environment to isolate dependencies and avoid conflicts with system packages.

### 1. Create a virtual environment
```sh
python3 -m venv venv
```

### 2. Activate the virtual environment
```sh
source venv/bin/activate
```

### 3. (Optional) Upgrade pip
```sh
pip install --upgrade pip
```

### 4. Install dependencies
If you have a `requirements.txt` or want to install the package in editable mode:
```sh
pip install -e .
# or
pip install -r requirements.txt
```

### 5. Run the tool
```sh
# CLI mode
python src/main.py ...
# or
python -m src.main ...

# Web interface mode
python src/web/app.py
```

When finished, you can deactivate the environment with:
```sh
deactivate
```

## How to Use

### Web Interface

1. Start the web server:
   ```bash
   python src/web/app.py
   ```

2. Open your browser and navigate to `http://localhost:5000`

3. Enter a GitHub repository URL and optionally specify a dependency file path

4. Click "Check Dependencies" and wait for the results

5. If updates are found, a Pull Request will be created automatically

The web interface provides:
- Real-time status updates
- A clean table view of available updates
- Direct links to created Pull Requests
- Error handling and user feedback

### Command Line Interface

The script is run from the command line using `python src/main.py` followed by a command.

**Available Commands:**

### `check`
Checks for available updates.
-   **Check local environment (pip packages):**
    ```bash
    python src/main.py check
    ```
-   **Check a GitHub repository (pip or npm, dependency file in root):**
    ```bash
    python src/main.py check https://github.com/user/repo
    ```
-   **Check a specific dependency file in a GitHub repository:**
    ```bash
    python src/main.py check https://github.com/user/repo --dfp path/to/your/requirements.txt
    python src/main.py check https://github.com/user/repo --dfp client/package.json
    ```
    (`--dfp` stands for "dependency file path")

### `update <package_name>`
Updates a specific locally installed pip package to its latest version.
```bash
python src/main.py update requests
```

### `update-all`
Updates all outdated locally installed pip packages.
```bash
python src/main.py update-all
```

### `check-and-update`
Checks for updates and optionally updates them. For local pip environment or specified GitHub dependency file.
-   **Check and update local environment:**
    ```bash
    python src/main.py check-and-update --update
    ```
-   **Check GitHub repo and then decide (update action is local if used):**
    ```bash
    python src/main.py check-and-update https://github.com/user/repo --dfp path/to/requirements.txt 
    # If you add --update here, it currently attempts local package updates based on the check.
    ```
*(Note: The `--update` flag with a GitHub repo URL in `check-and-update` will warn that it updates local packages, not the remote repo directly. Use `propose-updates` for remote repos.)*

### `propose-updates <repo_url>`
Checks a GitHub repository for outdated pip or npm dependencies and, if updates are found, proposes a Pull Request.

-   **Propose updates for a repository (dependency file in root):**
    ```bash
    python src/main.py propose-updates https://github.com/owner/repository-name
    ```
-   **Propose updates for a specific dependency file in a repository:**
    ```bash
    python src/main.py propose-updates https://github.com/owner/repo --dfp backend/requirements.txt
    ```

**Authorization for `propose-updates`:**
When you run `propose-updates` for the first time (or if your previous authorization is no longer valid), the script will initiate the GitHub OAuth Device Flow:
1.  It will display a URL (e.g., `https://github.com/login/device`) and a user code.
2.  It will attempt to open this URL in your default web browser.
3.  You need to navigate to this URL (if it didn't open automatically), enter the user code, and authorize the OAuth App you registered (e.g., "My Dependency Updater CLI") to access your repositories with the `repo` scope. This scope is necessary to create branches and pull requests.
4.  Once you authorize in the browser, the script will detect this and proceed.

The script will then:
-   Identify outdated dependencies.
-   Display them and ask for confirmation before creating a PR.
-   Create a new branch (e.g., `dep-updates/pip-timestamp`).
-   Commit the updated `requirements.txt` or `package.json`.
-   Create a Pull Request against the repository's default branch.

## Script Overview (`src/main.py`)

-   **OAuth Handling:**
    -   `get_github_oauth_token()`: Manages the OAuth Device Flow.
-   **Package Information:**
    -   `get_installed_packages()`: Gets locally installed pip packages.
    -   `get_latest_version()`: Fetches latest pip package version from PyPI (with caching).
    -   `get_latest_npm_version()`: Fetches latest npm package version from npm registry (with caching).
-   **GitHub Scraping & Checking:**
    -   `scrape_dependencies_from_github()`: Fetches and parses `requirements.txt` or `package.json` from a GitHub repo. Supports `--dfp`.
    -   `check_updates_parallel()`: Orchestrates checking for updates (local or GitHub) using threading.
    -   `check_package_version()`: Logic for comparing a single package's version.
-   **PR Creation:**
    -   `generate_new_dependency_file_content()`: Creates the string content for the updated dependency file.
    -   `create_github_pr()`: Handles creating the branch, committing the file, and opening the PR using `PyGithub`.
-   **CLI Commands:** Defined using `click`, mapping to the functionalities above.

## Contributing

Feel free to fork this repository, make improvements, and submit pull requests!

## License

MIT License 