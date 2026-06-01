# Copado Genie — Build Flow

Concise spec for what we build, how steps connect, and what we need. UI reference: [`deployment-ui-flow.md`](deployment-ui-flow.md).

---

## What we are building

**Copado Genie** = `copado-genie` CLI + embedded **orchestrator** + **Copado API client** + **`SKILL.md`** for Cursor agents.

One command runs the full dev1 → UAT → PROD path:

```bash
copado-genie workflow run --story US-1234 --to PROD
```

Agents run the same commands from the IDE terminal (no MCP in MVP).

```text
Developer / Agent
    → SKILL.md + copado-genie CLI
    → Orchestrator
    → Workflow functions
    → Copado APIs
```

---

## End-to-end flow (what happens)

| # | Copado UI (reference) | Copado Genie | Build as |
|---|------------------------|-----------|----------|
| 0 | — | Authenticate | `auth login`, `auth status` + PAK storage |
| 1 | New User Story | Bind story context | `story set --id US-xxxx` → GET user stories |
| 2 | Open Org, build metadata | *(out of scope)* | Document in SKILL: metadata must exist in dev sandbox |
| 3 | Copado Changes → Commit | Commit to Git | `commit` → retrieve refresh + POST `/actions/commit` |
| 4 | Deliver → Ready to Promote | Flag story ready | `ready` or step inside `workflow run` → story status API |
| 5 | Pipeline Manager → Promote UAT | Promote + deploy UAT | `promote --env UAT` → POST `/actions/promote` |
| 6 | Monitor jobs | Poll until done | `status --watch` → GET `/job-executions/{id}` |
| 7 | Verify UAT | Summary + optional org check | CLI prints job result; story path / pipeline status |
| 8 | *(optional)* CRT tests | Run smoke tests | `test run` → Agentia testing API |
| 9 | — | **Approval gate** | Orchestrator prompts: deploy to PROD? (y/n) |
| 10 | Deliver → Promote and Deploy | Deploy PROD | `deploy --env PROD` → POST `/actions/deploy` |
| 11 | Monitor + confirm | Poll + summary | `status --watch` → deployment summary |

**Git model (orchestrator must respect):** one `feature/US-xxxx` branch per story on commit; new promotion branch on each promote/deploy run.

**Guardrail:** warn if commit selection looks incomplete (object without custom fields — see flow doc §3.2).

---

## Orchestrator sequence

Deterministic — not chosen by the LLM:

```text
auth check
  → story set
  → commit              (metadata completeness warning)
  → ready_to_promote
  → promote --env UAT
  → status --watch
  → test run            (optional)
  → APPROVAL GATE
  → deploy --env PROD
  → status --watch
  → print summary
```

Exposed as `copado-genie workflow run`. Individual subcommands stay available for debugging.

---

## Components & integration

| Component | Role | Integrates with |
|-----------|------|-----------------|
| **CLI** (`packages/cli`) | Parse args, print output, call orchestrator | Orchestrator, terminal, agents via SKILL |
| **Orchestrator** | Step order, gates, polling, state | Workflow functions only |
| **Workflow functions** | One function per action (`commit`, `promote_uat`, …) | API client |
| **Copado API client** | HTTP, auth headers, error mapping | Copado REST APIs |
| **SKILL.md** | Agent playbooks + guardrails | Documents CLI commands; no code |

**Integration rule:** orchestrator and API client are shared. Future MCP (if added) calls the same orchestrator — no duplicate logic.

---

## Tools & stack

| Need | Choice |
|------|--------|
| Language | **Python 3.11+** |
| CLI framework | **Typer** |
| HTTP | **httpx** (async) |
| Auth storage | **keyring** (never commit PAK) |
| Copado auth | Personal Access Key |
| Copado APIs | CI/CD Actions, user stories, job executions, environments |
| Optional | CRT testing API, Agentia AI (`ai ask --agent release`) |
| IDE | Cursor + integrated terminal |
| Agent docs | `SKILL.md` at repo root |
| Spec | `deployment-ui-flow.md` |

**Hackathon credentials:** use provided Copado org/API access; confirm exact endpoints for ready-to-promote and retrieve-before-commit.

---

## Repo layout (planned)

```text
packages/cli/           # copado-genie commands
packages/orchestrator/  # workflow run(), approval, polling
packages/copado-api/    # client + types
SKILL.md
deployment-ui-flow.md   # UI parity spec
copado-genie-flow.md       # this file
```

May start as a single package; split when useful.

---

## Runtime flow — from developer prompt to deployment

Step-by-step: what runs, who decides what, and which tools are involved.

### Phase 0 — Before first use (one-time setup)

| Who | What | Tool |
|-----|------|------|
| Developer | `copado-genie auth login` | CLI + **keytar/keyring** stores **Personal Access Key** |
| Developer | Metadata exists in **dev1** sandbox | Salesforce (not Copado Genie) |

---

### Phase 1 — Developer prompts in Cursor

**Developer says:**

```text
Deploy US-1234 to UAT
```

| Step | Who | What happens | Tool / artifact |
|------|-----|--------------|-----------------|
| 1 | **Cursor agent** | Reads intent: deploy, story `US-1234`, target UAT | LLM (Cursor) |
| 2 | **Cursor agent** | Loads **`SKILL.md`** — finds playbook “Full story delivery”, guardrails (no direct API calls, use CLI only) | `skill.md` |
| 3 | **Cursor agent** | Runs in integrated terminal (does **not** call Copado HTTP itself) | Cursor terminal |

**Agent runs:**

```bash
copado-genie auth status
copado-genie workflow run --story US-1234 --to UAT
```

*(If not authenticated, agent asks developer to `auth login` first.)*

**Alternative:** developer types the same command manually — orchestrator path is identical; agent is skipped.

---

### Phase 2 — CLI receives the command

| Step | Who | What happens | Built with |
|------|-----|--------------|------------|
| 4 | **CLI** | Parses `--story US-1234 --to UAT` | **Oclif / Commander** (or Typer) |
| 5 | **CLI** | Loads stored PAK, validates args | CLI + **keytar** |
| 6 | **CLI** | Calls `orchestrator.run({ storyId, target: 'UAT' })` | Our code — entry point |

The CLI is a thin shell: parse args → call orchestrator → print JSON/text output for human and agent.

---

### Phase 3 — Orchestrator runs (the brain)

**How we build it:** a single module, e.g. `packages/orchestrator/workflow.ts`, with one function:

```text
runWorkflow(storyId, target)  →  runs steps in fixed order, tracks job IDs, stops on error
```

Not an LLM. A **deterministic async pipeline** — each step awaits the previous (especially job polling).

| Step | Orchestrator calls | Maps to Copado UI | On failure |
|------|-------------------|-------------------|------------|
| 7 | `ensureAuthenticated()` | — | Exit: “run auth login” |
| 8 | `storySet(storyId)` | New User Story / bind story | Exit: invalid story |
| 9 | `commit(storyId)` | Copado Changes → Commit | Exit + optional Release agent |
| 10 | `readyToPromote(storyId)` | Deliver → Ready to Promote | Exit |
| 11 | `promoteUAT(storyId)` | Pipeline Manager → Promote and Deploy | Exit |
| 12 | `pollUntilComplete(jobId)` | View deployment status → 100% | Exit or retry |
| 13 | *(if `--to PROD`)* `requireApproval()` | — (our gate; not in UI video) | Block until user types `y` |
| 14 | `deployProd(storyId)` | Deliver → Promote and Deploy | Exit |
| 15 | `pollUntilComplete(jobId)` | Monitor PROD job | Exit |
| 16 | `printSummary(state)` | Pipeline green, path complete | Return to CLI |

**Orchestrator state object** (in memory for one run):

```text
{ storyId, jobIds[], currentStep, uatComplete, prodApproved, errors[] }
```

**Polling:** loop `GET /job-executions/{id}` every N seconds until `Completed` or `Failed` — same as UI async jobs.

**Approval gate:** orchestrator reads stdin (`Approve PROD? y/n`) or requires `--approve-prod` flag only after interactive confirm — agent must not auto-approve per SKILL.

---

### Phase 4 — Workflow functions → API client → Copado

Each orchestrator step delegates to a **workflow function** in `packages/copado-api` or `packages/orchestrator/steps/`:

```text
orchestrator.run()
    → commit()           → api.post('/actions/commit', body)
    → promoteUAT()       → api.post('/actions/promote', body)
    → pollJob()          → api.get('/job-executions/{id}')
    → readyToPromote()   → api.patch user story / status (confirm with hackathon creds)
    → deployProd()       → api.post('/actions/deploy', body)
```

| Workflow function | HTTP / API | Libraries |
|-------------------|------------|-----------|
| `storySet` | GET `/user-stories` | **axios / httpx** |
| `commit` | POST `/actions/commit` (+ retrieve refresh if needed) | axios + our payload builder |
| `readyToPromote` | Story status update | axios |
| `promoteUAT` | POST `/actions/promote` | axios |
| `deployProd` | POST `/actions/deploy` | axios |
| `pollJob` | GET `/job-executions/{id}` | axios + sleep loop |
| `runTests` *(optional)* | Agentia CRT API | axios |
| `askReleaseAgent` *(on failure)* | POST `/dialogues` (Release agent) | axios |

**API client** handles: base URL, PAK header, errors → friendly CLI messages.

---

### Phase 5 — Output back to developer / agent

| Step | Who | What |
|------|-----|------|
| 17 | **CLI** | Prints step progress + final summary (job IDs, UAT ✅, waiting on PROD approval, etc.) |
| 18 | **Agent** | Reads terminal output, parses status table from SKILL §6, explains in plain English |
| 19 | **Developer** | Confirms PROD when prompted; verifies object + field in UAT/PROD org |

If deploy fails at step 11–12, agent may run:

```bash
copado-genie ai ask --agent release "Analyze failed deployment for US-1234"
```

---

### Full picture (one diagram)

```text
Developer: "Deploy US-1234 to UAT"
        │
        ▼
┌───────────────────┐
│  Cursor Agent     │  reads SKILL.md, runs terminal commands only
└─────────┬─────────┘
          │  copado-genie workflow run --story US-1234 --to UAT
          ▼
┌───────────────────┐
│  copado-genie CLI    │  Oclif/Commander — parse args, print output
└─────────┬─────────┘
          │  orchestrator.run()
          ▼
┌───────────────────┐
│  Orchestrator     │  fixed step order, state, poll, approval gate
└─────────┬─────────┘
          │  commit(), promoteUAT(), pollJob(), ...
          ▼
┌───────────────────┐
│  Workflow fns     │  one function per Copado action
└─────────┬─────────┘
          │  axios/httpx
          ▼
┌───────────────────┐
│  Copado APIs      │  commit, promote, deploy, jobs, stories
└───────────────────┘
          │
          ▼
   dev1 → UAT → PROD  (Salesforce orgs via Copado pipeline)
```

---

### What the agent does vs what the orchestrator does

| | Agent (LLM) | Orchestrator (our code) |
|---|-------------|-------------------------|
| Understands “deploy my feature” | ✅ | ❌ |
| Chooses step order | ❌ | ✅ |
| Calls Copado APIs | ❌ | ✅ (via workflow fns) |
| Polls jobs | ❌ | ✅ |
| Blocks PROD without human | guides via SKILL | ✅ enforces |
| Writes summary for human | ✅ | prints raw status |

---

### How we implement the orchestrator (concrete)

1. **`WorkflowContext`** — holds story ID, job IDs, target env, errors.
2. **`steps/`** — one file per action (`commit.ts`, `promote.ts`, `poll.ts`, …).
3. **`runWorkflow(ctx)`** — sequential `await` chain; each step returns next job ID or throws.
4. **`poll.ts`** — `while status === 'In Progress' { sleep; GET job }`.
5. **`approval.ts`** — `readline` or CLI prompt before PROD step.
6. **Wire in CLI** — `workflow run` command imports and calls `runWorkflow`.

No agent framework inside the orchestrator — plain TypeScript/Python async code.

---

## Demo path

1. Story `US-xxxx` exists; metadata (`Copado_Demo__c` + `Description__c`) in dev1 sandbox.
2. Terminal: `copado-genie workflow run --story US-xxxx --to UAT`
3. Show polling → UAT complete (object **and** field in UAT).
4. Optional: `test run`
5. Orchestrator asks PROD approval → user confirms → deploy → poll → summary.
6. No Copado browser UI during demo.

---

## Out of scope (MVP)

- Building metadata in Salesforce (Step 2)
- Back-promotion, pre/post deployment steps
- Full commit-grid UI parity (MVP: sensible default selection or flags)
- MCP server (optional later)

---

## Success = 

- [ ] Full checklist in `deployment-ui-flow.md` runnable headlessly  
- [ ] Async jobs polled like UI  
- [ ] PROD blocked without human approval  
- [ ] Agent can drive flow via SKILL + terminal  
