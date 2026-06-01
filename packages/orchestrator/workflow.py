"""
Copado Genie — Main orchestrator.

Deterministic deployment pipeline called by the CLI.
Not an LLM — fixed async step sequence.

Pipeline: dev1 → UAT → (approval) → PROD
Reference: deployment-ui-flow.md — Full Flow Checklist
"""

from dataclasses import dataclass
from typing import Literal, Optional

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


# ── Options ───────────────────────────────────────────────────────

@dataclass
class WorkflowOptions:
    story_id: str
    target: Literal["UAT", "PROD"]
    # Metadata to commit — defaults to the demo object + field
    metadata: Optional[list[dict]] = None
    # CRT tests (optional)
    test_suite_id: Optional[str] = None
    project_id: Optional[str] = None


# ── Default metadata from deployment-ui-flow.md demo ─────────────

DEFAULT_METADATA = [
    {"type": "CustomObject",  "fullName": "Copado_Demo__c"},
    {"type": "CustomField",   "fullName": "Copado_Demo__c.Description__c"},
]


# ── Main pipeline ─────────────────────────────────────────────────

async def run_workflow(config: CopadoConfig, opts: WorkflowOptions) -> WorkflowState:
    """
    Runs the full Copado deployment pipeline deterministically.

    Step map → Copado UI:
      bind_story        → New User Story (set story context)
      commit_metadata   → Copado Changes → Commit Changes
      ready_to_promote  → Deliver → Ready to Promote
      promote_to_uat    → Pipeline Manager → Promote and Deploy (UAT)
      poll              → View deployment status (async job)
      run_tests         → CRT test run (optional)
      require_approval  → (our gate — mandatory before PROD)
      deploy_to_prod    → Deliver → Promote and Deploy (PROD)
      poll              → Monitor PROD job
      print_summary     → Pipeline green, path complete
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

            # ── 5: promote + deploy → UAT ────────────────────
            await promote_to_uat(client, state)

            # ── 6 (optional): run CRT tests ──────────────────
            if opts.test_suite_id and opts.project_id:
                await run_tests(client, state, opts.project_id, opts.test_suite_id)

            # ── 7: approval gate + deploy → PROD ─────────────
            if opts.target == "PROD":
                approved = require_approval(
                    "UAT deployment complete.\nDeploy to Production?"
                )
                if not approved:
                    state.errors.append("PROD deployment cancelled by user.")
                    print_summary(state)
                    return state

                await deploy_to_prod(client, state)

                # ── 8: generate release notes ────────────────
                await generate_release_notes(client, state)

            # ── 9: summary ───────────────────────────────────
            print_summary(state)
            return state

        except Exception as exc:
            state.errors.append(str(exc))
            print_summary(state)
            raise
