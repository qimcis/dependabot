"""Console utilities for consistent output formatting."""

from rich.console import Console

# Create a global console instance
console = Console()

def print_error(message: str) -> None:
    """Print an error message in red."""
    console.print(f"[red]{message}[/red]")

def print_success(message: str) -> None:
    """Print a success message in green."""
    console.print(f"[green]{message}[/green]")

def print_info(message: str) -> None:
    """Print an info message in cyan."""
    console.print(f"[cyan]{message}[/cyan]")

def print_warning(message: str) -> None:
    """Print a warning message in yellow."""
    console.print(f"[yellow]{message}[/yellow]")

def print_bold(message: str) -> None:
    """Print a bold message."""
    console.print(f"[bold]{message}[/bold]") 