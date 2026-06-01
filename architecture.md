# Architecture

## High-Level Design

```text
Developer
    ↓
Cursor / Copilot / Terminal
    ↓
SKILL.md  →  agent runs copado-genie commands  (or developer runs CLI directly)
    ↓
copado-genie CLI
    ↓
Workflow Orchestrator  (embedded in CLI)
    ↓
Workflow Functions
    ↓
Copado API Layer
    ↓
Copado APIs
```

**Optional (if time permits):** an MCP server can wrap the same orchestrator later without changing workflow logic.

---

## Component Responsibilities

### AI Agent (Cursor / Copilot)

Responsibilities:

* Understand user intent
* Read `SKILL.md` for commands, playbooks, and guardrails
* Run `copado-genie` in the integrated terminal (or ask the developer to confirm)
* Present results and human-readable summaries

The AI agent is **not** trusted to call Copado APIs directly or invent deployment order.

---

### SKILL.md

Responsibilities:

* Teach agents which CLI commands to run and in what order
* Encode guardrails (e.g. never deploy to PROD without explicit human approval)
* Map natural language (“deploy to UAT”) to concrete `copado-genie` invocations

See [`skill.md`](skill.md).

---

### copado-genie CLI

Responsibilities:

* Single entry point for developers and agents (`auth`, `story`, `commit`, `promote`, `workflow`, `status`, `test`, `ai`)
* Parse flags and validate inputs
* Invoke the orchestrator for multi-step flows (e.g. `workflow run`)
* Print structured, parseable output for agents

The CLI does not decide ad-hoc workflow order for full deliveries—that belongs to the orchestrator.

---

### Workflow Orchestrator

Responsibilities:

* Deterministic execution of the Copado UI-equivalent path (see [`deployment-ui-flow.md`](deployment-ui-flow.md))
* Approval checkpoints before PROD
* Retry and job polling (`status --watch`)
* State management across async Copado jobs

Example:

```python
def workflow_run(story_id: str, target: str):
    story_set(story_id)
    commit()
    ready_to_promote()
    promote_uat()
    wait_until_complete()
  # optional: run_tests()
    if target == "PROD":
        require_human_approval()
        deploy_prod()
        wait_until_complete()
```

---

### Workflow Functions

Examples:

```python
story_set()
commit()
ready_to_promote()
promote_uat()
run_tests()
deploy_prod()
poll_job_status()
```

These functions perform actual operations via the API layer.

---

### Copado API Layer

Responsibilities:

* Authenticate (Personal Access Key)
* CI/CD Actions: commit, promote, validate, deploy
* User stories, environments, job executions
* Agentia testing (CRT) and AI dialogues (Release agent on failure)

This layer contains all external HTTP communication.

---

## Execution Flow

### Path A — Developer uses CLI

```bash
copado-genie auth login
copado-genie workflow run --story US-1234 --to UAT
copado-genie status --watch
```

### Path B — Agent uses SKILL + terminal

**User prompt:**

```text
Deploy my feature to UAT
```

**Agent (reads SKILL.md):**

```bash
copado-genie auth status
copado-genie story set --id US-1234
copado-genie workflow run --story US-1234 --to UAT
copado-genie status --watch
```

**Orchestrator** runs the same steps as Path A internally.

### Full delivery (UAT → tests → PROD)

```python
# Inside orchestrator — not chosen by the LLM
story_set()
commit()
ready_to_promote()
promote_uat()
wait_until_complete()
run_tests()           # optional, pipeline-dependent
require_human_approval()
deploy_prod()
wait_until_complete()
```

---

## Safety Model

| Layer | Trusted for deployment logic? |
|-------|-------------------------------|
| LLM / agent | No — intent and narration only |
| SKILL.md | No — instructions only |
| CLI + orchestrator | Yes — deterministic source of truth |
| Copado APIs | Yes — system of record |

Approval checkpoints are mandatory before production deployments.

---

## UI Parity

The orchestrator implements the linear checklist in [`deployment-ui-flow.md`](deployment-ui-flow.md):

1. User story context  
2. Commit (with metadata completeness warnings)  
3. Ready to Promote  
4. Promote / deploy to UAT + poll  
5. Optional tests  
6. Human approval gate  
7. Deploy to PROD + poll  

---

## Future: Optional MCP Layer

If time permits, add an MCP server that forwards to the **same** orchestrator:

```text
MCP tool (e.g. run_workflow)
    ↓
Orchestrator  (unchanged)
    ↓
Workflow Functions
```

Additional MCP tools (future): `deploy_story`, `run_tests`, `generate_release_notes`, `rollback_deployment`.

No business logic should live only in MCP—the CLI and orchestrator remain canonical.

---

## Repository Layout (planned)

```text
packages/cli/           # copado-genie commands
packages/orchestrator/  # workflow run(), gates, polling
packages/copado-api/    # HTTP client + auth
SKILL.md                # agent playbooks (repo root)
deployment-ui-flow.md   # UI → headless spec
```

Packages may be merged into one module for hackathon velocity.
