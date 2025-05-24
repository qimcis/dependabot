# Dependabot

A Python-based dependency management tool that checks for outdated packages in Python projects and GitHub repositories.

## Features

- Check for outdated packages in your local Python environment
- Check dependencies from any GitHub repository's `requirements.txt`
- Support for various version specifiers (==, >=, <=, ~=, !=)
- Beautiful console output using `rich`
- Detailed version comparison and update suggestions

## Installation

1. Clone this repository:
```bash
git clone https://github.com/yourusername/dependabot.git
cd dependabot
```

2. Create and activate a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Check Local Environment

To check for outdated packages in your current Python environment:

```bash
python src/main.py check
```

### Check GitHub Repository

To check dependencies from a GitHub repository's requirements.txt:

```bash
python src/main.py check https://github.com/username/repo
```

The script will:
1. Fetch the requirements.txt from the repository
2. Parse all package names and version specifiers
3. Check each package against PyPI for newer versions
4. Display a table of available updates

### Update Packages

To update a specific package:

```bash
python src/main.py update package_name
```

To update all outdated packages:

```bash
python src/main.py update-all
```

## Version Specifier Support

The script understands various version specifiers in requirements.txt:
- `==1.2.3` (exact version)
- `>=1.2.0` (minimum version)
- `<=2.0.0` (maximum version)
- `~=1.2.0` (compatible release)
- `!=1.2.3` (excluded version)
- No specifier (any version)

## Output Example

```
                    Available Updates                    
┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┓
┃ Package            ┃ Current Version ┃ Latest Version ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
│ requests           │ 2.31.0          │ 2.32.3         │
│ rich               │ 13.7.0          │ 14.0.0         │
└────────────────────┴─────────────────┴────────────────┘
```

## Requirements

- Python 3.7+
- pip
- Internet connection (for checking PyPI)

## Dependencies

- click: Command line interface creation
- rich: Terminal formatting and styling
- requests: HTTP requests
- packaging: Version parsing and comparison

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.