# Architecture Decisions

## Decision 1

### CLI + Orchestrator (MCP deferred)

Chosen:

```text
Developer / AI Agent
    ↓
SKILL.md + copado-genie CLI
    ↓
Orchestrator
    ↓
Copado APIs
```

Rejected for hackathon MVP:

```text
AI Agent → MCP → Orchestrator
```

Reason:

* Faster to ship a working end-to-end demo
* Terminal is native to Cursor—agents run shell commands without custom MCP
* Track A + Track B (`SKILL.md`) do not require MCP
* Same orchestrator can be wrapped by MCP later if time permits

---

## Decision 2

### Primary interface: `workflow run` + subcommands

Chosen:

```bash
copado-genie workflow run --story US-1234 --to UAT
copado-genie story set --id US-1234
copado-genie commit
copado-genie promote --env UAT
copado-genie status --watch
```

Reason:

* Matches hackathon `copado-genie` spec and [`deployment-ui-flow.md`](deployment-ui-flow.md)
* One command for demos; granular commands for debugging
* Agents invoke predictable, documented strings (not free-form API calls)

Future: optional MCP tool that calls the same `workflow run` implementation.

---

## Decision 3

### Backend controls workflow

Chosen:

```text
Orchestrator controls execution
```

Rejected:

```text
AI controls execution sequence
```

Reason:

* Safer
* Deterministic
* Easier approval handling
* Better enterprise design

The agent may suggest commands; the orchestrator enforces order when `workflow run` is used.

---

## Decision 4

### Approval before PROD

Chosen:

Mandatory approval gate in the orchestrator (interactive prompt or explicit `--approve-prod` flag after human confirmation).

Reason:

* Prevent accidental deployments
* Demonstrate governance
* Enterprise best practice
* Aligns with hackathon guardrails

---

## Decision 5

### Single implementation path for CLI and future MCP

Chosen:

```text
CLI / future MCP
    ↓
Orchestrator
    ↓
Functions
    ↓
Copado API layer
```

Reason:

Avoid duplicating business logic. MCP would be a thin adapter, not a second workflow engine.

---

## Decision 6

### AI is not source of truth

Chosen:

Orchestrator + API layer validation required.

Reason:

LLMs are probabilistic. Deployment actions require deterministic validation.

Agents must not call Copado HTTP APIs directly or fabricate job/story IDs.

---

## Decision 7

### Language and stack

Chosen: **Python 3.11+**

| Layer | Tool |
|-------|------|
| Language | Python 3.11+ |
| CLI | **Typer** |
| HTTP | **httpx** (async) |
| Credential storage | **keyring** (PAK) |
| Async runtime | `asyncio` |

Reason: faster iteration, readable async code, Typer auto-generates help text, httpx has a clean async API matching Copado's async job model.

---

## Decision 8

### Hackathon priorities

Priority order:

1. Working demo (dev1 → UAT → PROD path)
2. Headless experience (no Copado UI during demo)
3. `workflow run` orchestrator + job polling
4. CLI UX (`auth`, `story`, `commit`, `promote`, `status`)
5. `SKILL.md` agent playbooks (Track B)
6. CRT tests + Release agent on failure
7. MCP server (optional — only if time permits)
8. Advanced architecture (split packages, extension UI)

Reason:

Judges evaluate usability and innovation more than integration plumbing.

---

## Final Architecture

```text
Developer
    ↓
Cursor / Copilot / Terminal
    ↓
SKILL.md  →  copado-genie CLI
    ↓
Orchestrator
    ↓
Workflow Functions
    ↓
Copado APIs
```

This architecture maximizes:

* Demo quality
* Development speed
* Reliability
* Hackathon scoring potential (Track A + B; Track C via IDE-native terminal)
