"""
Workflow step functions.
Each function does exactly one Copado action — the orchestrator chains them in order.
"""

import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from rich.console import Console
from rich.table import Table

from copado_api.client import CopadoClient, JobStatus, UserStory
from orchestrator.poll import poll_until_complete

console = Console()


# ── State passed between steps ────────────────────────────────────

@dataclass
class WorkflowState:
    story_id: str
    target: Literal["UAT", "PROD"]
    story: Optional[UserStory] = None
    build_guidance: Optional[str] = None
    commit_job_id: Optional[str] = None
    promote_job_id: Optional[str] = None
    deploy_job_id: Optional[str] = None
    test_result: Optional[JobStatus] = None
    uat_result: Optional[JobStatus] = None
    prod_result: Optional[JobStatus] = None
    release_notes: Optional[str] = None
    errors: list[str] = field(default_factory=list)


# ── Step helpers ──────────────────────────────────────────────────

def _progress(label: str):
    """Returns a callback that prints job progress in-place."""
    def _cb(s: JobStatus):
        print(f"\r  {label}: {s.progress}%  {s.status}   ", end="", flush=True)
    return _cb


def _done():
    print()  # newline after in-place progress


# ── Steps ─────────────────────────────────────────────────────────

async def ask_build_agent(
    client: CopadoClient, state: WorkflowState, metadata: list[dict]
) -> None:
    """Ask the Build agent for metadata guidance before committing."""
    types = ", ".join(sorted({m["type"] for m in metadata}))
    names = ", ".join(m.get("fullName", "?") for m in metadata)
    prompt = (
        f"I'm about to commit metadata for user story {state.story_id}. "
        f"Components: {names}. Types: {types}. "
        f"Are there any missing dependencies or related metadata I should include?"
    )
    console.print("[bold][2][/bold] Asking Build agent for metadata guidance...")
    try:
        reply = await client.ask_agent("build", prompt)
        state.build_guidance = reply
        console.print(f"    [cyan]Build agent:[/cyan] {reply[:200]}{'...' if len(reply) > 200 else ''}")
    except Exception as exc:
        # Non-fatal — continue with commit even if agent is unavailable
        console.print(f"    [yellow]Build agent unavailable: {exc}[/yellow]")
        state.build_guidance = None


async def bind_story(client: CopadoClient, state: WorkflowState) -> None:
    console.print(f"[bold][1][/bold] Binding user story {state.story_id}...")
    state.story = await client.get_user_story(state.story_id)
    console.print(f"    Title   : [bold]{state.story.title}[/bold]")
    console.print(f"    Project : {state.story.project}")
    console.print(f"    Env     : {state.story.environment}")


async def commit_metadata(
    client: CopadoClient,
    state: WorkflowState,
    metadata: list[dict],
) -> None:
    # Guardrail from deployment-ui-flow.md §3.2:
    # committing an object without its custom fields leaves them out of UAT.
    types = {m["type"] for m in metadata}
    if "CustomObject" in types and "CustomField" not in types:
        print(
            "\n  ⚠  Warning: committing a CustomObject without CustomField.\n"
            "     UAT will get the object but none of its custom fields.\n"
            "     Add CustomField entries to metadata list.\n"
        )

    sf_id = state.story.id if state.story else state.story_id
    console.print(f"[bold][2][/bold] Committing {len(metadata)} metadata component(s)...")
    job_id = await client.commit(sf_id, metadata)
    state.commit_job_id = job_id
    console.print(f"    Job: {job_id}")

    result = await poll_until_complete(client, job_id, _progress("Commit"))
    _done()
    _print_result(result)

    if result.status == "Failed":
        raise RuntimeError(f"Commit failed: {result.error_message}")


async def ready_to_promote(client: CopadoClient, state: WorkflowState) -> None:
    """
    Mirrors: User story → Deliver → Ready to Promote → Save.
    Updates the pipeline count (e.g. dev1 [0] → dev1 [1]).
    """
    console.print("[bold][4][/bold] Marking story as Ready to Promote...")
    sf_id = state.story.id if state.story else state.story_id
    await client.update_story_status(sf_id, {"copado__Promote_Change__c": True})
    console.print("    Done — story now appears in Pipeline Manager count.")


async def promote_to_uat(client: CopadoClient, state: WorkflowState) -> None:
    """
    Mirrors: Pipeline Manager → click dev1 [n] → select story → Promote and Deploy.
    Copado creates a promotion branch from uat-branch, merges feature/US-xxxx, deploys.
    """
    sf_id = state.story.id if state.story else state.story_id
    console.print("[bold][5][/bold] Promoting and deploying to UAT...")
    job_id = await client.promote(sf_id, "UAT")
    state.promote_job_id = job_id
    console.print(f"    Job: {job_id}")

    result = await poll_until_complete(client, job_id, _progress("UAT"))
    _done()
    _print_result(result)

    state.uat_result = result
    if result.status == "Failed":
        raise RuntimeError(f"UAT promotion failed: {result.error_message}")


async def run_tests(
    client: CopadoClient,
    state: WorkflowState,
    project_id: str,
    suite_id: str,
) -> None:
    console.print("[bold][6][/bold] Running CRT tests...")
    job_id = await client.run_tests(project_id, suite_id)
    console.print(f"    Job: {job_id}")

    result = await poll_until_complete(client, job_id, _progress("Tests"))
    _done()
    _print_result(result)

    state.test_result = result
    if result.status == "Failed":
        raise RuntimeError("Tests failed — cannot proceed to PROD.")


async def deploy_to_prod(client: CopadoClient, state: WorkflowState) -> None:
    """
    Mirrors: User story → Deliver → Promote and Deploy (PROD checkbox) → Save.
    """
    sf_id = state.story.id if state.story else state.story_id
    console.print("[bold][7][/bold] Deploying to Production...")
    job_id = await client.deploy(sf_id, "Production")
    state.deploy_job_id = job_id
    console.print(f"    Job: {job_id}")

    result = await poll_until_complete(client, job_id, _progress("PROD"))
    _done()
    _print_result(result)

    state.prod_result = result
    if result.status == "Failed":
        raise RuntimeError(f"PROD deploy failed: {result.error_message}")


async def generate_release_notes(client: CopadoClient, state: WorkflowState) -> None:
    """Ask the Operate agent to generate release notes after a successful deployment.

    The notes are printed to the console, stored in state, and saved to a markdown file.
    """
    story_info = f"{state.story_id}"
    if state.story:
        story_info = f"{state.story.name} — {state.story.title}"
    prompt = (
        f"Generate concise release notes for user story {story_info}. "
        f"Target environment: {state.target}. "
        f"UAT status: {state.uat_result.status if state.uat_result else 'N/A'}. "
        f"PROD status: {state.prod_result.status if state.prod_result else 'N/A'}. "
        f"Format as markdown."
    )
    console.print("[bold][8][/bold] Generating release notes...")
    try:
        reply = await client.ask_agent("operate", prompt)
        state.release_notes = reply
        console.print(f"    [cyan]Release notes:[/cyan]\n{reply}")

        # Save to file
        out_dir = Path("release-notes")
        out_dir.mkdir(exist_ok=True)
        date_str = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_id = state.story_id.replace("/", "-")
        out_path = out_dir / f"{safe_id}-{date_str}.md"
        out_path.write_text(
            f"# Release Notes — {story_info}\n\n"
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Target: {state.target}\n\n"
            f"{reply}\n"
        )
        console.print(f"    [green]Saved to:[/green] {out_path}")
    except Exception as exc:
        console.print(f"    [yellow]Could not generate release notes: {exc}[/yellow]")
        state.release_notes = None


def _print_result(result: JobStatus) -> None:
    """Print job result with color based on status."""
    color = "green" if result.status == "Completed" else "yellow" if "Error" in result.status else "red"
    console.print(f"    Result: [{color}]{result.status}[/{color}]")


def print_summary(state: WorkflowState) -> None:
    console.print("\n[bold][9] Deployment Summary[/bold]")
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Label", style="dim", width=12)
    table.add_column("Value")

    table.add_row("Story", f"{state.story_id} — {state.story.title if state.story else '?'}")

    if state.build_guidance:
        table.add_row("Build Agent", "[green]consulted[/green]")

    table.add_row("Commit", state.commit_job_id or "—")

    uat_status = state.uat_result.status if state.uat_result else "—"
    uat_color = "green" if uat_status == "Completed" else "red" if uat_status == "Failed" else "yellow"
    table.add_row("UAT", f"{state.promote_job_id or '—'} → [{uat_color}]{uat_status}[/{uat_color}]")

    if state.test_result:
        test_color = "green" if state.test_result.status == "Completed" else "red"
        table.add_row("Tests", f"[{test_color}]{state.test_result.status}[/{test_color}]")

    if state.target == "PROD":
        prod_status = state.prod_result.status if state.prod_result else "—"
        prod_color = "green" if prod_status == "Completed" else "red" if prod_status == "Failed" else "yellow"
        table.add_row("PROD", f"{state.deploy_job_id or '—'} → [{prod_color}]{prod_status}[/{prod_color}]")
    else:
        table.add_row("PROD", "[dim]awaiting approval[/dim]")

    if state.release_notes:
        table.add_row("Release Notes", "[green]generated[/green]")

    console.print(table)

    if state.errors:
        console.print("\n[red]Errors:[/red]")
        for e in state.errors:
            console.print(f"  - {e}")
