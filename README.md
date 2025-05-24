# Dependabot

A Python-based dependency management tool that checks for outdated packages in Python projects and GitHub repositories.

## Features

- Check for outdated packages in your local Python environment
- Check dependencies from any GitHub repository's `requirements.txt`
- Support for various version specifiers (==, >=, <=, ~=, !=)
- Beautiful console output using `rich`
- Detailed version comparison and update suggestions
- Fast parallel processing for checking multiple packages
- Version caching to reduce API calls
- One-command check and update functionality

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

### Fast Check and Update

The fastest way to check and optionally update dependencies:

```bash
# Just check for updates
python src/main.py check-and-update

# Check and automatically update all outdated packages
python src/main.py check-and-update --update

# Check a specific GitHub repository
python src/main.py check-and-update https://github.com/username/repo

# Check and update a specific GitHub repository
python src/main.py check-and-update https://github.com/username/repo --update
```

This command uses parallel processing and caching to make dependency checking much faster than the traditional commands.

### Traditional Commands

For backward compatibility, the following commands are still available:

```bash
# Check local environment
python src/main.py check

# Check GitHub repository
python src/main.py check https://github.com/username/repo

# Update specific package
python src/main.py update package_name

# Update all packages
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