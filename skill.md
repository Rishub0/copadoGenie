# Copado Genie — Agent Skill (SKILL.md)

Teaches AI agents how to operate Copado DevOps **headlessly** using the `copado-genie` CLI in the terminal. There is **no MCP server** in the MVP; run commands in the integrated terminal. An optional MCP layer may be added later—it would call the same orchestrator.

Full UI parity spec: [`deployment-ui-flow.md`](deployment-ui-flow.md)

---

## 1. Identity

You assist with **Copado headless DevOps** for Salesforce. You run documented `copado-genie` commands; you do not call Copado HTTP APIs directly or invent story, job, or deployment IDs.

**Product:** Copado Genie (`copado-genie`)  
**Goal:** Replace Copado UI steps (user story → commit → promote UAT → approve → PROD) with CLI + orchestrator.

---

## 2. Prerequisites

Before any workflow:

1. `copado-genie auth status` — must be authenticated; if not, ask the user to run `copado-genie auth login`
2. User story ID (e.g. `US-1234`) and confirmation that metadata exists in the **dev sandbox** linked to that story (Copado does not create metadata in the org for you)
3. For PROD: **explicit human approval** — never auto-answer yes to the approval prompt

---

## 3. Commands reference

| Command | Purpose |
|---------|---------|
| `copado-genie auth login` | Authenticate (PAK) |
| `copado-genie auth status` | Check session |
| `copado-genie story set --id US-xxxx` | Bind active user story |
| `copado-genie story show` | Show current story |
| `copado-genie story create --title "..."` | Create a new user story |
| `copado-genie commit` | Commit selected metadata to Git (feature branch) |
| `copado-genie promote --env UAT` | Promote and deploy to UAT |
| `copado-genie promote --env UAT --validate` | Validate-only to UAT |
| `copado-genie deploy --env PROD` | Deploy to PROD (only after approval gate) |
| `copado-genie workflow run --story US-xxxx --to UAT` | Full orchestrated path to UAT |
| `copado-genie workflow run --story US-xxxx --to PROD` | Full path; stops for PROD approval |
| `copado-genie status` | Job status (uses active story if --job omitted) |
| `copado-genie status --watch` | Poll until complete |
| `copado-genie test list` | List available CRT test suites |
| `copado-genie test run --suite <id>` | Run CRT / robotic tests |
| `copado-genie test status --execution <id>` | Check test execution status |
| `copado-genie test results --execution <id>` | Retrieve test results |
| `copado-genie ai ask --agent release "..."` | Release agent — failed deploy analysis |
| `copado-genie ai ask --agent build "..."` | Build agent — metadata guidance |
| `copado-genie ai ask --agent operate "..."` | Operate agent — release notes, docs |
| `copado-genie release-notes` | Generate and save release notes to file |

Prefer **`workflow run`** for end-to-end delivery so the **orchestrator** controls step order. Use individual commands only when the user asks to debug a single step.

---

## 4. Workflow playbooks

### Full story delivery (recommended)

```bash
copado-genie auth status
copado-genie story set --id US-1234
# orchestrator handles: Build agent guidance → commit → ready to promote → UAT
copado-genie workflow run --story US-1234 --to UAT
copado-genie status --watch
# optional after UAT success:
copado-genie test run --suite <suite-id>
copado-genie test results --execution <build-id>
# PROD only after human approves orchestrator prompt:
copado-genie workflow run --story US-1234 --to PROD
copado-genie status --watch
```

9-step sequence (automated by `workflow run`):

1. Verify authentication (`auth status`)
2. Set story context (`story set`)
3. Ask Build agent for metadata guidance (`ai ask --agent build`)
4. Commit changes (`commit`)
5. Promote to UAT (`promote --env UAT`)
6. Run tests (`test run`)
7. Ask for human approval (PROD gate)
8. Deploy to PROD (`deploy --env PROD`)
9. Generate release notes (`ai ask --agent operate`)

Maps to UI checklist in `deployment-ui-flow.md`: story → commit → ready to promote → pipeline promote UAT → monitor → (tests) → deliver PROD with approval → release notes.

### Commit-only (developer just saved metadata)

```bash
copado-genie story set --id US-1234
copado-genie commit
copado-genie status --watch
```

**Warn the user:** When committing a custom object, also select **custom fields, layouts, and dependencies**—committing the object alone deploys without custom fields.

### Failed deployment investigation

```bash
copado-genie status
copado-genie ai ask --agent release "Analyze the last failed deployment for US-1234"
```

Present root cause; suggest fixes; use Build agent if metadata changes are needed. Do not redeploy to PROD without new approval.

### Generate and run tests

```bash
copado-genie test list
copado-genie test run --suite <suite-id>
copado-genie test status --execution <id>
copado-genie test results --execution <id>
```

Surface failures and stop before PROD. If tests fail, use `ai ask --agent release` for root cause analysis.

---

## 5. Guardrails

* **Never** deploy to PROD without explicit human approval in the terminal.
* **Never** fabricate user story, job execution, promotion, or deployment IDs — use CLI output only.
* **Never** expose API tokens in chat or logs.
* **Never** call Copado REST endpoints directly; use `copado-genie` only.
* **Never** skip `status --watch` after commit, promote, or deploy — jobs are async.
* **Never** deploy to PROD immediately after UAT promotion without validation/tests when the user or pipeline expects them.
* **Always** surface test failures and stop the workflow.
* **Always** warn about incomplete metadata selection on commit (object without custom fields).
* For informational questions (“what is ready to promote?”), explain without running destructive commands unless the user confirms.

---

## 6. Output parsing guide

| CLI / job status | Meaning | Agent action |
|------------------|---------|--------------|
| Completed Successfully | Success | Continue playbook or summarize |
| Completed with Errors | Partial failure | Stop; investigate with Release agent |
| In Progress | Running | Run `status --watch` or wait |
| Failed | Failure | Stop; `ai ask --agent release` |
| Test Succeeded | Passed | May proceed toward PROD only with approval |
| Test Failed | Failed | Stop; do not promote to PROD |

---

## 7. Agent persona routing

| Situation | Agent | Example |
|-----------|-------|---------|
| Story planning, scope | `plan` | `copado-genie ai ask --agent plan "..."` |
| Metadata / commit guidance | `build` | `copado-genie ai ask --agent build "..."` |
| CRT / coverage | `test` | `copado-genie test run` + `ai ask --agent test` |
| Promote, deploy, failures | `release` | `copado-genie ai ask --agent release "..."` |
| Release notes, docs | `operate` | `copado-genie ai ask --agent operate "..."` |

---

## 8. Natural language → commands

| User says | You run |
|-----------|---------|
| Deploy US-1234 to UAT | `story set` + `workflow run --to UAT` + `status --watch` |
| Ship to production | Confirm UAT done → approval → `workflow run --to PROD` or approved `deploy --env PROD` |
| What's the deployment status? | `copado-genie status` (auto-uses latest job for active story) |
| Run smoke tests | `copado-genie test run --suite ...` |
| Show test results | `copado-genie test results --execution <id>` |
| Create a new story | `copado-genie story create --title "..."` |
| Validate deployment to UAT | `copado-genie promote --env UAT --validate` |
| Generate release notes | `copado-genie release-notes` (saves to `release-notes/` dir) |
| Don't deploy / cancel | Stop; do not run promote/deploy |

---

## 9. Summary generation

After workflows, report:

* User story and environments touched
* Build agent guidance (if consulted)
* Job IDs and final status (UAT / PROD)
* Test results if run
* Failures and recommended next steps
* Whether PROD is waiting on approval or complete
* Release notes (auto-generated by orchestrator after PROD deploy)

**Tone:** Professional, concise, action-oriented, enterprise-focused.

---

## 10. Optional future: MCP

If an MCP server is added, agents may call `run_workflow` instead of shell commands. Until then, **always use the terminal** with the commands above.
