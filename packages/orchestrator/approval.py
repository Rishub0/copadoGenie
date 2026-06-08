"""
Approval gate before PROD.
Blocks on stdin until a human explicitly types 'yes'.
Agents must not auto-answer — enforced by SKILL.md guardrails.
"""

from rich.console import Console
from rich.panel import Panel

console = Console()


def require_approval(prompt: str, auto_approve: bool = False) -> bool:
    """
    Prompts the developer in the terminal with a prominent warning.

    For production deployments, requires typing 'yes' (not just 'y')
    to prevent accidental approvals.

    If auto_approve is True (only via --auto-approve CLI flag), skips
    the prompt entirely. Default is False — always blocks.
    """
    if auto_approve:
        console.print("[yellow]Auto-approved (--auto-approve flag set).[/yellow]")
        return True

    console.print()
    console.print(Panel(
        f"[bold yellow]{prompt}[/bold yellow]\n\n"
        "Type [bold green]yes[/bold green] to proceed, anything else to cancel.",
        title="[bold red]APPROVAL REQUIRED[/bold red]",
        border_style="red",
        expand=False,
    ))

    try:
        answer = input("  > ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        console.print("\n[yellow]Cancelled.[/yellow]")
        return False

    if answer == "yes":
        console.print("[green]Approved. Proceeding...[/green]")
        return True
    else:
        console.print("[yellow]Cancelled by user.[/yellow]")
        return False
