"""
Copado Genie CLI — Agentic DevOps for Salesforce (Track B).

Thin Typer shell over the orchestrator.
Agents read SKILL.md and run these commands; orchestrator owns all logic.

Usage:
  copado-genie auth login --token <pak> --org <org-id>
  copado-genie auth status
  copado-genie story set --id US-1234
  copado-genie workflow run --story US-1234 --to UAT
  copado-genie workflow run --story US-1234 --to PROD
  copado-genie status --job <job-id>
  copado-genie ai ask --agent release "Analyze last failure"
  copado-genie workspace list
"""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import keyring
import typer
from rich.console import Console
from rich.table import Table
from typing_extensions import Annotated

from copado_api.client import COPADO_AI_BASE_URLS, CopadoClient, CopadoConfig
from orchestrator.workflow import WorkflowOptions, run_workflow

console = Console()

app = typer.Typer(
    name="copado-genie",
    help="Copado Genie — Agentic DevOps CLI for Salesforce",
)

auth_app = typer.Typer(help="Authentication")
story_app = typer.Typer(help="User story management")
workflow_app = typer.Typer(help="Orchestrated deployment workflows")
test_app = typer.Typer(help="CRT test execution")
workspace_app = typer.Typer(help="Copado AI workspace management")

app.add_typer(auth_app, name="auth")
app.add_typer(story_app, name="story")
app.add_typer(workflow_app, name="workflow")
app.add_typer(test_app, name="test")
app.add_typer(workspace_app, name="workspace")

SERVICE = "copado-genie"


# ── Helpers ───────────────────────────────────────────────────────

def _get_pak() -> str:
    return os.environ.get("COPADO_PAK", "") or keyring.get_password(SERVICE, "pak") or ""


def _get_org_id() -> int:
    raw = os.environ.get("COPADO_ORG_ID", "") or keyring.get_password(SERVICE, "org_id") or ""
    if not raw:
        return 0
    return int(raw)


def _get_workspace_id() -> str:
    return (
        os.environ.get("COPADO_WORKSPACE_ID", "")
        or keyring.get_password(SERVICE, "workspace_id")
        or ""
    )


def _config() -> CopadoConfig:
    pak = _get_pak()
    org_id = _get_org_id()
    if not pak or not org_id:
        console.print(
            "[red]Not authenticated.[/red] Run: copado-genie auth login --token <pak> --org <org-id>"
        )
        raise typer.Exit(code=1)
    region = os.environ.get("COPADO_REGION", "US")
    return CopadoConfig(
        api_key=pak,
        org_id=org_id,
        ai_base_url=COPADO_AI_BASE_URLS.get(region, COPADO_AI_BASE_URLS["US"]),
        cicd_base_url=os.environ.get("COPADO_CICD_URL", "") or keyring.get_password(SERVICE, "cicd_url") or "",
        sf_token=os.environ.get("COPADO_SF_TOKEN", "") or keyring.get_password(SERVICE, "sf_token") or "",
        workspace_id=_get_workspace_id(),
        region=region,
    )


# ── auth ─────────────────────────────────────────────────────────

@auth_app.command("login")
def auth_login(
    token: Annotated[str, typer.Option("--token", help="Personal Access Key (PAK)")],
    org: Annotated[int, typer.Option("--org", help="Organization ID (integer)")],
    region: Annotated[str, typer.Option("--region", help="Region: US|EU|AU|SG")] = "US",
    workspace: Annotated[Optional[str], typer.Option("--workspace", help="Workspace ID")] = None,
    cicd_url: Annotated[Optional[str], typer.Option("--cicd-url", help="Salesforce instance URL for CI/CD API")] = None,
    sf_token: Annotated[Optional[str], typer.Option("--sf-token", help="Salesforce session token for CI/CD REST")] = None,
):
    """Store Copado credentials securely via keyring."""
    keyring.set_password(SERVICE, "pak", token)
    keyring.set_password(SERVICE, "org_id", str(org))
    keyring.set_password(SERVICE, "region", region)
    if workspace:
        keyring.set_password(SERVICE, "workspace_id", workspace)
    if cicd_url:
        keyring.set_password(SERVICE, "cicd_url", cicd_url.rstrip("/"))
    if sf_token:
        keyring.set_password(SERVICE, "sf_token", sf_token)
    os.environ["COPADO_PAK"] = token
    os.environ["COPADO_ORG_ID"] = str(org)
    os.environ["COPADO_REGION"] = region
    console.print(f"[green]Authenticated.[/green] Org: {org} | Region: {region}")
    if cicd_url:
        console.print(f"  CI/CD URL : {cicd_url}")
    if sf_token:
        console.print(f"  SF Token  : {'*' * 8}...{sf_token[-4:]}")


@auth_app.command("status")
def auth_status():
    """Check authentication status."""
    pak = _get_pak()
    org_id = _get_org_id()
    ws_id = _get_workspace_id()
    if pak and org_id:
        console.print(f"[green]Authenticated.[/green]")
        cicd_url = keyring.get_password(SERVICE, "cicd_url") or "(not set)"
        sf_tok = keyring.get_password(SERVICE, "sf_token") or ""
        console.print(f"  Org ID    : {org_id}")
        console.print(f"  Workspace : {ws_id or '(not set)'}")
        console.print(f"  CI/CD URL : {cicd_url}")
        console.print(f"  SF Token  : {'*' * 8}...{sf_tok[-4:]}" if sf_tok else "  SF Token  : (not set)")
        console.print(f"  PAK       : {'*' * 8}...{pak[-4:]}")
    else:
        console.print("[red]Not authenticated.[/red] Run: copado-genie auth login --token <pak> --org <org-id>")
        raise typer.Exit(code=1)


@auth_app.command("logout")
def auth_logout():
    """Remove stored credentials."""
    for key in ("pak", "org_id", "region", "workspace_id", "cicd_url", "sf_token"):
        try:
            keyring.delete_password(SERVICE, key)
        except keyring.errors.PasswordDeleteError:
            pass
    for env in ("COPADO_PAK", "COPADO_ORG_ID", "COPADO_REGION", "COPADO_WORKSPACE_ID"):
        os.environ.pop(env, None)
    console.print("[yellow]Logged out.[/yellow]")


# ── story ─────────────────────────────────────────────────────────

@story_app.command("set")
def story_set(
    id: Annotated[str, typer.Option("--id", help="User story ID, e.g. US-1234")]
):
    """Bind the active user story for the current session."""
    os.environ["COPADO_STORY"] = id
    console.print(f"Active story: [bold]{id}[/bold]")


@story_app.command("show")
def story_show(
    id: Annotated[Optional[str], typer.Option("--id", help="Story Name or Id")] = None,
):
    """Show a user story's details from Copado."""
    story_id = id or os.environ.get("COPADO_STORY")
    if not story_id:
        console.print("No story set. Run: copado-genie story set --id US-xxxx")
        raise typer.Exit(code=1)

    async def _run():
        async with CopadoClient(_config()) as client:
            s = await client.get_user_story(story_id)
            console.print(f"[bold]{story_id}[/bold] — {s.title}")
            console.print(f"  ID          : {s.id}")
            console.print(f"  Project     : {s.project}")
            console.print(f"  Environment : {s.environment}")
            console.print(f"  Promote     : {'Yes' if s.ready_to_promote else 'No'}")

    asyncio.run(_run())


@story_app.command("create")
def story_create(
    title: Annotated[str, typer.Option("--title", help="User story title")],
    project: Annotated[Optional[str], typer.Option("--project", help="Copado project ID")] = None,
):
    """Create a new user story in Copado."""
    async def _run():
        async with CopadoClient(_config()) as client:
            s = await client.create_user_story(title, project)
            console.print(f"[green]Created story:[/green] {s.name}")
            console.print(f"  ID          : {s.id}")
            console.print(f"  Title       : {s.title}")
            console.print(f"  Project     : {s.project}")

    asyncio.run(_run())


@story_app.command("list")
def story_list(
    limit: Annotated[int, typer.Option("--limit", help="Max stories to show")] = 10,
):
    """List user stories from Copado."""

    async def _run():
        async with CopadoClient(_config()) as client:
            stories = await client.list_user_stories(limit=limit)
            if not stories:
                console.print("[yellow]No user stories found.[/yellow]")
                return
            table = Table(title="User Stories")
            table.add_column("Name", style="bold")
            table.add_column("Title")
            table.add_column("Environment")
            table.add_column("Promote?")
            for s in stories:
                table.add_row(
                    s.name,
                    s.title,
                    s.environment or "—",
                    "Yes" if s.ready_to_promote else "No",
                )
            console.print(table)

    asyncio.run(_run())


# ── workflow ──────────────────────────────────────────────────────

@workflow_app.command("run")
def workflow_run(
    story: Annotated[str, typer.Option("--story", help="User story ID")],
    to: Annotated[str, typer.Option("--to", help="Target env: UAT or PROD")],
    metadata: Annotated[Optional[str], typer.Option("--metadata", help="JSON list of metadata")] = None,
    test_suite: Annotated[Optional[str], typer.Option("--test-suite", help="CRT test suite ID")] = None,
    project: Annotated[Optional[str], typer.Option("--project", help="Copado project ID")] = None,
):
    """
    Run the full DevOps pipeline: dev1 → UAT → (approval) → PROD.

    Examples:
      copado-genie workflow run --story US-1234 --to UAT
      copado-genie workflow run --story US-1234 --to PROD
    """
    target = to.upper()
    if target not in ("UAT", "PROD"):
        console.print("[red]--to must be UAT or PROD[/red]")
        raise typer.Exit(code=1)

    opts = WorkflowOptions(
        story_id=story,
        target=target,          # type: ignore[arg-type]
        metadata=json.loads(metadata) if metadata else None,
        test_suite_id=test_suite,
        project_id=project,
    )

    asyncio.run(run_workflow(_config(), opts))


# ── promote (standalone) ─────────────────────────────────────────

@app.command("promote")
def promote(
    env: Annotated[str, typer.Option("--env", help="Target environment: UAT")],
    story: Annotated[Optional[str], typer.Option("--story", help="Story ID")] = None,
    validate: Annotated[bool, typer.Option("--validate", help="Validate only (dry run)")] = False,
):
    """Promote a story to an environment (standalone)."""
    story_id = story or os.environ.get("COPADO_STORY")
    if not story_id:
        console.print("[red]Provide --story or run: copado-genie story set --id US-xxxx[/red]")
        raise typer.Exit(code=1)

    action = "Validating" if validate else "Promoting"
    console.print(f"{action} {story_id} to {env}...")

    async def _run():
        async with CopadoClient(_config()) as client:
            if validate:
                job_id = await client.validate(story_id, env)
            else:
                job_id = await client.promote(story_id, env)
            console.print(f"  Job: {job_id}")
            from orchestrator.poll import poll_until_complete
            result = await poll_until_complete(client, job_id)
            console.print(f"  Result: {result.status}")

    asyncio.run(_run())


# ── deploy (standalone) ──────────────────────────────────────────

@app.command("deploy")
def deploy_cmd(
    env: Annotated[str, typer.Option("--env", help="Target environment: PROD")],
    story: Annotated[Optional[str], typer.Option("--story", help="Story ID")] = None,
):
    """Deploy a story to an environment (standalone)."""
    story_id = story or os.environ.get("COPADO_STORY")
    if not story_id:
        console.print("[red]Provide --story or run: copado-genie story set --id US-xxxx[/red]")
        raise typer.Exit(code=1)

    if env.upper() == "PROD":
        from orchestrator.approval import require_approval
        if not require_approval("Deploy to Production?"):
            console.print("[yellow]Deployment cancelled.[/yellow]")
            raise typer.Exit(code=0)

    console.print(f"Deploying {story_id} to {env}...")

    async def _run():
        async with CopadoClient(_config()) as client:
            job_id = await client.deploy(story_id, env)
            console.print(f"  Job: {job_id}")
            from orchestrator.poll import poll_until_complete
            result = await poll_until_complete(client, job_id)
            console.print(f"  Result: {result.status}")

    asyncio.run(_run())


# ── status (standalone) ───────────────────────────────────────────

@app.command("status")
def status(
    job: Annotated[Optional[str], typer.Option("--job", help="Job execution ID")] = None,
    watch: Annotated[bool, typer.Option("--watch", help="Poll until complete")] = False,
):
    """Check or watch a Copado job status.

    If --job is omitted, uses the latest job for the active story.
    """
    async def _resolve_job(client):
        """Return the job ID — explicit or looked up from the active story."""
        if job:
            return job
        story_id = os.environ.get("COPADO_STORY")
        if not story_id:
            console.print("[red]Provide --job <job-id> or set a story first: copado-genie story set --id US-xxxx[/red]")
            raise typer.Exit(code=1)
        found = await client.get_latest_job_for_story(story_id)
        if not found:
            console.print(f"[red]No job executions found for story {story_id}.[/red]")
            raise typer.Exit(code=1)
        console.print(f"[dim]Using latest job for {story_id}:[/dim] {found}")
        return found

    async def _check():
        async with CopadoClient(_config()) as client:
            job_id = await _resolve_job(client)
            if watch:
                from orchestrator.poll import poll_until_complete
                def _cb(s):
                    print(f"\r  {s.progress}%  {s.status}   ", end="", flush=True)
                result = await poll_until_complete(client, job_id, _cb)
                print()
                console.print(f"Final: [bold]{result.status}[/bold]")
            else:
                s = await client.get_job_status(job_id)
                console.print(f"Job {s.id}: {s.status} ({s.progress}%)")
                if s.error_message:
                    console.print(f"[red]Error: {s.error_message}[/red]")

    asyncio.run(_check())


# ── commit (standalone) ───────────────────────────────────────────

@app.command("commit")
def commit(
    metadata: Annotated[Optional[str], typer.Option("--metadata", help="JSON list")] = None,
    story: Annotated[Optional[str], typer.Option("--story", help="Story ID")] = None,
):
    """Commit metadata for a story (standalone — use 'workflow run' for full pipeline)."""
    story_id = story or os.environ.get("COPADO_STORY")
    if not story_id:
        console.print("[red]Provide --story or run: copado-genie story set --id US-xxxx[/red]")
        raise typer.Exit(code=1)

    console.print(f"Committing for {story_id}...")

    async def _run():
        async with CopadoClient(_config()) as client:
            meta = json.loads(metadata) if metadata else [
                {"type": "CustomObject", "fullName": "Copado_Demo__c"},
                {"type": "CustomField", "fullName": "Copado_Demo__c.Description__c"},
            ]
            job_id = await client.commit(story_id, meta)
            console.print(f"  Job: {job_id}")
            from orchestrator.poll import poll_until_complete
            result = await poll_until_complete(client, job_id)
            console.print(f"  Result: {result.status}")

    asyncio.run(_run())


# ── test commands ─────────────────────────────────────────────────

@test_app.command("run")
def test_run(
    suite: Annotated[str, typer.Option("--suite", help="CRT test suite ID")],
    project: Annotated[Optional[str], typer.Option("--project", help="Project ID")] = None,
):
    """Run a CRT test suite."""
    proj = project or os.environ.get("COPADO_PROJECT_ID", "")
    if not proj:
        console.print("[red]Provide --project or set COPADO_PROJECT_ID[/red]")
        raise typer.Exit(code=1)

    console.print(f"Running test suite {suite}...")

    async def _run():
        async with CopadoClient(_config()) as client:
            job_id = await client.run_tests(proj, suite)
            console.print(f"  Build: {job_id}")

    asyncio.run(_run())


@test_app.command("list")
def test_list(
    project: Annotated[Optional[str], typer.Option("--project", help="Project ID")] = None,
):
    """List available CRT test suites."""
    proj = project or os.environ.get("COPADO_PROJECT_ID", "")
    if not proj:
        console.print("[red]Provide --project or set COPADO_PROJECT_ID[/red]")
        raise typer.Exit(code=1)

    async def _run():
        async with CopadoClient(_config()) as client:
            suites = await client.list_test_suites(proj)
            if not suites:
                console.print("[yellow]No test suites found.[/yellow]")
                return
            table = Table(title="CRT Test Suites")
            table.add_column("ID", style="cyan")
            table.add_column("Name", style="bold")
            table.add_column("Status")
            for s in suites:
                table.add_row(
                    s.get("id", s.get("Id", "?")),
                    s.get("name", s.get("Name", "?")),
                    s.get("status", s.get("Status", "?")),
                )
            console.print(table)

    asyncio.run(_run())


@test_app.command("status")
def test_status(
    execution: Annotated[str, typer.Option("--execution", help="Execution/build ID")],
    project: Annotated[Optional[str], typer.Option("--project", help="Project ID")] = None,
):
    """Check test execution status."""
    async def _run():
        async with CopadoClient(_config()) as client:
            s = await client.get_job_status(execution)
            console.print(f"Test {s.id}: {s.status} ({s.progress}%)")

    asyncio.run(_run())


@test_app.command("results")
def test_results(
    execution: Annotated[str, typer.Option("--execution", help="Execution/build ID")],
    project: Annotated[Optional[str], typer.Option("--project", help="Project ID")] = None,
):
    """Retrieve test results for a completed test run."""
    proj = project or os.environ.get("COPADO_PROJECT_ID", "")
    if not proj:
        console.print("[red]Provide --project or set COPADO_PROJECT_ID[/red]")
        raise typer.Exit(code=1)

    async def _run():
        async with CopadoClient(_config()) as client:
            results = await client.get_test_results(proj, execution)
            table = Table(title=f"Test Results — {execution}")
            table.add_column("Test", style="bold")
            table.add_column("Status")
            table.add_column("Duration")
            if isinstance(results, list):
                for r in results:
                    name = r.get("name", r.get("testName", "?"))
                    passed = r.get("passed", r.get("status", "?"))
                    dur = r.get("duration", r.get("executionTime", "?"))
                    status_str = "[green]PASS[/green]" if passed is True else "[red]FAIL[/red]" if passed is False else str(passed)
                    table.add_row(name, status_str, str(dur))
            else:
                table.add_row("Raw output", str(results), "")
            console.print(table)

    asyncio.run(_run())


# ── workspace commands ────────────────────────────────────────────

@workspace_app.command("list")
def workspace_list():
    """List Copado AI workspaces."""
    async def _run():
        async with CopadoClient(_config()) as client:
            workspaces = await client.list_workspaces()
            if not workspaces:
                console.print("No workspaces found.")
                return
            table = Table(title="Workspaces")
            table.add_column("ID", style="cyan")
            table.add_column("Name", style="bold")
            table.add_column("Description")
            for ws in workspaces:
                table.add_row(ws.id, ws.name, ws.description)
            console.print(table)

    asyncio.run(_run())


@workspace_app.command("create")
def workspace_create(
    name: Annotated[str, typer.Option("--name", help="Workspace name")],
    description: Annotated[str, typer.Option("--desc", help="Description")] = "",
):
    """Create a new Copado AI workspace."""
    async def _run():
        async with CopadoClient(_config()) as client:
            ws = await client.create_workspace(name, description)
            console.print(f"[green]Created workspace:[/green] {ws.name} ({ws.id})")
            console.print(f"Set it active: copado-genie auth login --workspace {ws.id} ...")

    asyncio.run(_run())


@workspace_app.command("set")
def workspace_set(
    id: Annotated[str, typer.Option("--id", help="Workspace ID to activate")],
):
    """Set the active workspace."""
    keyring.set_password(SERVICE, "workspace_id", id)
    os.environ["COPADO_WORKSPACE_ID"] = id
    console.print(f"Active workspace: [bold]{id}[/bold]")


# ── release-notes ────────────────────────────────────────────────

@app.command("release-notes")
def release_notes(
    story: Annotated[Optional[str], typer.Option("--story", help="Story ID")] = None,
    output: Annotated[Optional[str], typer.Option("--output", help="Save to file path")] = None,
):
    """Generate release notes for a deployed story using the Operate agent.

    If --output is specified, saves to that file.
    Otherwise prints to terminal and saves to release-notes/<story>-<date>.md.
    """
    story_id = story or os.environ.get("COPADO_STORY")
    if not story_id:
        console.print("[red]Provide --story or run: copado-genie story set --id US-xxxx[/red]")
        raise typer.Exit(code=1)

    async def _run():
        async with CopadoClient(_config()) as client:
            story_info = story_id
            try:
                s = await client.get_user_story(story_id)
                story_info = f"{s.name} — {s.title}"
            except Exception:
                pass

            prompt = (
                f"Generate concise release notes for user story {story_info}. "
                f"Include: summary of changes, environments touched, any risks, "
                f"and recommended verification steps. Format as markdown."
            )
            console.print(f"[dim]Generating release notes for {story_id}...[/dim]")
            reply = await client.ask_agent("operate", prompt)

            console.print(f"\n[bold cyan]Release Notes[/bold cyan]\n{reply}")

            # Determine output path
            if output:
                out_path = Path(output)
            else:
                out_dir = Path("release-notes")
                out_dir.mkdir(exist_ok=True)
                date_str = datetime.now().strftime("%Y%m%d-%H%M%S")
                safe_id = story_id.replace("/", "-")
                out_path = out_dir / f"{safe_id}-{date_str}.md"

            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                f"# Release Notes — {story_id}\n\n"
                f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"{reply}\n"
            )
            console.print(f"\n[green]Saved to:[/green] {out_path}")

    asyncio.run(_run())


# ── ai ask ────────────────────────────────────────────────────────

@app.command("ai")
def ai_ask(
    agent: Annotated[str, typer.Option("--agent", help="Agent: plan|build|test|release|operate")],
    question: Annotated[str, typer.Argument(help="Your question or prompt")],
):
    """Ask a Copado AI agent a question."""
    valid = {"plan", "build", "test", "release", "operate", "knowledge"}
    if agent not in valid:
        console.print(f"[red]--agent must be one of: {', '.join(sorted(valid))}[/red]")
        raise typer.Exit(code=1)

    async def _ask():
        async with CopadoClient(_config()) as client:
            console.print(f"[dim]Asking {agent} agent...[/dim]")
            reply = await client.ask_agent(agent, question)
            console.print(f"\n[bold cyan][{agent} agent][/bold cyan]\n{reply}")

    asyncio.run(_ask())


# ── Entry point ───────────────────────────────────────────────────

if __name__ == "__main__":
    app()
