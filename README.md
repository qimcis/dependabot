# Python Dependency Management Bot

A command-line tool that helps you manage and automatically update your Python package dependencies. Similar to GitHub's Dependabot, but with interactive control over updates.

## Features

- Check for outdated packages in your environment
- Update individual packages to their latest versions
- Update all outdated packages at once
- Beautiful terminal interface with color-coded output
- Safe dependency updates with error handling

## Installation

1. Clone this repository
2. Install the required dependencies:
```bash
pip install -r requirements.txt
```

## Usage

The tool provides several commands:

### Check for Updates
```bash
python src/main.py check
```
This will show a table of all packages that have updates available.

### Update a Specific Package
```bash
python src/main.py update <package_name>
```
This will update the specified package to its latest version.

### Update All Packages
```bash
python src/main.py update-all
```
This will update all outdated packages to their latest versions.

## Example Output

When checking for updates, you'll see a nicely formatted table showing:
- Package name
- Current version
- Latest available version

## Requirements

- Python 3.6+
- pip
- Internet connection (for checking PyPI)

## Contributing

Feel free to submit issues and enhancement requests! 