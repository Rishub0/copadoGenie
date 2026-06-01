# Copado Genie — Agentic DevOps CLI

## Overview

Copado Genie is an agentic DevOps CLI (`copado-genie`) that lets Salesforce developers run end-to-end Copado workflows from the IDE terminal—without opening the Copado UI. AI agents in Cursor/Copilot can drive the same commands via [`SKILL.md`](skill.md).

The orchestrator encodes the full UI path documented in [`deployment-ui-flow.md`](deployment-ui-flow.md): user story → commit → ready to promote → UAT → optional tests → approval → PROD.

**Hackathon track:** Track B (Agentic Orchestrator) via `SKILL.md` + CLI. Optional MCP wrapper later if time permits—see [`architecture.md`](architecture.md).

---

## Problem

Copado releases today require many browser steps (user story, commit grid, pipeline manager, promotion jobs, deliver tab for PROD). That breaks flow for developers working in the IDE and is unsafe if an LLM improvises API calls.

Copado Genie:

* Reduces UI dependency
* Improves developer productivity
* Enables agent-driven workflows through documented CLI commands
* Keeps governance (orchestrator + PROD approval gate)

---

## Quick start (planned)

```bash
copado-genie auth login
copado-genie story set --id US-1234
copado-genie workflow run --story US-1234 --to UAT
copado-genie status --watch
```

Granular commands for debugging:

```bash
copado-genie commit
copado-genie promote --env UAT
copado-genie test run --suite <suite-id>
copado-genie deploy --env PROD    # only after approval gate in workflow
copado-genie ai ask --agent release "analyze last failure"
```

---

## Key features

### CLI workflow

```bash
copado-genie workflow run --story US-1234 --to UAT
copado-genie workflow run --story US-1234 --to PROD   # stops for approval
```

### AI agent experience (no MCP required)

Agent reads `SKILL.md` and runs the same commands in the integrated terminal:

```text
Deploy story US-1234 to UAT and run smoke tests.
```

### Approval gates

```text
UAT deployment complete. Smoke tests passed.

Ready to deploy to PROD.

Approve deployment? (y/n)
```

### Release summaries

```text
Deployment Summary

✓ UAT promote/deploy completed
✓ Smoke tests passed
✓ Code coverage: 91%

Awaiting PROD approval / PROD deployment successful.
```

---

## Architecture

```text
Developer / AI Agent
    ↓
SKILL.md  →  copado-genie CLI
    ↓
Workflow Orchestrator
    ↓
Workflow Functions
    ↓
Copado API Layer
```

Details: [`architecture.md`](architecture.md)  
Build flow: [`copado-genie-flow.md`](copado-genie-flow.md)  
Decisions: [`decisions.md`](decisions.md)  
UI → headless mapping: [`deployment-ui-flow.md`](deployment-ui-flow.md)

---

## Demo flow

1. Developer or agent sets story context: `copado-genie story set --id US-1234`
2. Orchestrated run: `copado-genie workflow run --story US-1234 --to UAT`
3. CLI polls Copado jobs: `copado-genie status --watch`
4. Optional: `copado-genie test run ...`
5. Orchestrator prompts for PROD approval
6. After approval: deploy to PROD and poll until complete
7. Agent or CLI prints deployment summary

No Copado browser UI required during the demo (UI only for initial setup per hackathon rules).

---

## Success criteria

* No browser required for commit → UAT → PROD demo path
* Deterministic orchestrator (not LLM-driven step order)
* Agent-assisted workflows via `SKILL.md` + terminal
* Mandatory approval before PROD
* Human-readable job output and summaries

---

## Future enhancements

* MCP server (thin wrapper over orchestrator)
* VS Code extension (Track C)
* Back-promotion and pre/post deployment steps
* Rollback workflows
* Slack / Teams notifications
* Release note generation (`ai ask --agent operate`)
* Production-grade RBAC
