"""
Copado Genie — Main orchestrator.

Deterministic deployment pipeline called by the CLI.
Not an LLM — fixed async step sequence.

Pipeline: Dev -> INT -> UAT -> (approval) -> Production
Reference: deployment-ui-flow.md — Full Flow Checklist
"""

from dataclasses import dataclass
from typing import Literal, Optional

from rich.console import Console

from copado_api.client import CopadoClient, CopadoConfig
from orchestrator.steps import (
    WorkflowState,
    ask_build_agent,
    bind_story,
    commit_metadata,
    ready_to_promote,
    promote_to_uat,
    run_tests,
    deploy_to_prod,
    generate_release_notes,
    print_summary,
)
from orchestrator.approval import require_approval

console = Console()


# ── Options ───────────────────────────────────────────────────────

@dataclass
class WorkflowOptions:
    story_id: str
    target: Literal["UAT", "PROD"]
    metadata: Optional[list[dict]] = None
    test_suite_id: Optional[str] = None
    project_id: Optional[str] = None
    auto_approve: bool = False


# ── Default metadata from deployment-ui-flow.md demo ─────────────

DEFAULT_METADATA = [
    {"type": "CustomObject",  "fullName": "Copado_Demo__c"},
    {"type": "CustomField",   "fullName": "Copado_Demo__c.Description__c"},
]

# Pipeline stages in order (Copado promotes sequentially)
PIPELINE_STAGES = ["INT", "UAT", "PROD"]


def _next_stage(current_env: str) -> Optional[str]:
    """Given a current environment name, return the next pipeline stage."""
    current_upper = current_env.upper()
    for i, stage in enumerate(PIPELINE_STAGES):
        if stage in current_upper:
            if i + 1 < len(PIPELINE_STAGES):
                return PIPELINE_STAGES[i + 1]
            return None  # Already at PROD
    # If not in pipeline (e.g. on dev), next stage is the first one
    return PIPELINE_STAGES[0]


# ── Main pipeline ─────────────────────────────────────────────────

async def run_workflow(config: CopadoConfig, opts: WorkflowOptions) -> WorkflowState:
    """
    Runs the full Copado deployment pipeline deterministically.

    Detects the story's current pipeline stage and promotes through
    each remaining stage until reaching the target.
    """
    state = WorkflowState(story_id=opts.story_id, target=opts.target)
    metadata = opts.metadata or DEFAULT_METADATA

    async with CopadoClient(config) as client:
        try:
            # ── 1: bind user story ───────────────────────────
            await bind_story(client, state)

            # ── 2: ask Build agent for metadata guidance ─────
            await ask_build_agent(client, state, metadata)

            # ── 3: commit metadata to Git ────────────────────
            await commit_metadata(client, state, metadata)

            # ── 4: mark ready to promote ─────────────────────
            await ready_to_promote(client, state)

            # ── 5: promote through pipeline stages ───────────
            # Determine current position and promote stage by stage
            sf_id = state.story.id if state.story else state.story_id
            _, current_env = await client.get_story_environment(sf_id)
            console.print(f"    Current environment: [cyan]{current_env}[/cyan]")

            target_upper = opts.target.upper()
            step_num = 5

            while True:
                next_stage = _next_stage(current_env)
                if next_stage is None:
                    console.print(f"    [green]Already at final stage ({current_env})[/green]")
                    break
                if next_stage == "PROD" and opts.target != "PROD":
                    console.print(f"    [dim]Target is UAT — stopping at {current_env}[/dim]")
                    break

                # For PROD, require approval
                if next_stage == "PROD":
                    approved = require_approval(
                        f"Story is on {current_env}.\nDeploy to Production?",
                        auto_approve=opts.auto_approve,
                    )
                    if not approved:
                        state.errors.append("PROD deployment cancelled by user.")
                        print_summary(state)
                        return state

                console.print(f"[bold][{step_num}][/bold] Promoting {current_env} -> {next_stage}...")
                job_id = await client.promote(sf_id, next_stage)

                if next_stage == "UAT":
                    state.promote_job_id = job_id
                elif next_stage == "PROD":
                    state.deploy_job_id = job_id

                console.print(f"    Promotion: {job_id}")

                # Wait for promotion to complete
                from orchestrator.poll import poll_until_complete
                from orchestrator.steps import _progress, _done, _print_result

                result = await poll_until_complete(client, job_id, _progress(next_stage))
                _done()
                _print_result(result)

                if next_stage == "UAT":
                    state.uat_result = result
                elif next_stage == "PROD":
                    state.prod_result = result

                if result.status == "Failed":
                    raise RuntimeError(f"{next_stage} promotion failed: {result.error_message}")

                # Re-check environment after promotion
                _, current_env = await client.get_story_environment(sf_id)
                console.print(f"    Now on: [cyan]{current_env}[/cyan]")
                step_num += 1

            # ── 6: generate release notes ────────────────────
            if opts.target == "PROD" and state.prod_result:
                await generate_release_notes(client, state)

            # ── 7: summary ───────────────────────────────────
            print_summary(state)
            return state

        except Exception as exc:
            state.errors.append(str(exc))
            print_summary(state)
            raise
