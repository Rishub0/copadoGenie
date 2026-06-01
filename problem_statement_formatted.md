# 🚀 CopadoCON Bangalore — June 2026

# Copado Headless Hackathon
**The Future of Salesforce DevOps Has No Browser Tab**

---

# 🎯 Vision

> "What if a developer never had to open Copado's UI again?"

The Copado Headless Hackathon challenges teams to build open-source tools that allow Salesforce developers and release engineers to execute end-to-end Copado DevOps workflows without using the browser UI.

The goal is to enable operations such as:

- Managing user stories
- Committing metadata
- Running robotic tests
- Promoting deployments
- Interacting with Copado AI agents

All from:

- Terminal
- IDE
- Git workflows
- AI agents

---

# Core Challenge Statement

Build an open-source utility, extension, framework, or agentic workflow that enables Salesforce developers and release engineers to execute Copado DevOps operations completely headless.

---

# Three Ways to Compete

| Track | Description |
|---------|-------------|
| 🔵 Track A — Headless CLI | Build `copado-hx`, a unified CLI wrapping Copado APIs |
| 🟣 Track B — Agentic Orchestrator | Extend Track A with `SKILL.md` so AI agents can operate autonomously |
| 🟠 Track C — Your Headless Idea | Build any headless Copado integration using APIs |

---

# 🔵 Track A — copado-hx: The Headless Developer CLI

## Authentication

```bash
copado-hx auth login
copado-hx auth login --token <api-token>
copado-hx auth status
copado-hx auth logout
```

## User Story Management

```bash
copado-hx story list
copado-hx story set --id US-1234
copado-hx story show
copado-hx story create --title "Add lead scoring"
```

## CI/CD Operations

```bash
copado-hx commit
copado-hx promote --env UAT
copado-hx promote --env UAT --validate
copado-hx deploy --env PROD
copado-hx status
copado-hx status --watch
```

## Test Execution

```bash
copado-hx test list
copado-hx test run --suite <suite-id>
copado-hx test status --execution <id>
copado-hx test results --execution <id>
```

## AI Agent Conversations

```bash
copado-hx ai ask --agent plan "..."
copado-hx ai ask --agent build "..."
copado-hx ai ask --agent test "..."
copado-hx ai ask --agent release "..."
copado-hx ai ask --agent operate "..."
```

---

# Copado AI Agents

| Agent | Purpose |
|---------|----------|
| Plan | User story refinement and planning |
| Build | Code generation and metadata analysis |
| Test | Test automation and coverage |
| Release | Deployments and release management |
| Operate | Documentation and change management |

---

# Example Track A Flow

```text
auth login
→ story set
→ ai ask build
→ commit
→ promote
→ run tests
→ deploy
→ generate release notes
```

---

# 🟣 Track B — Agentic Orchestrator

## What is SKILL.md?

`SKILL.md` is a structured instruction file that teaches AI agents how to use `copado-hx`.

### Required Sections

1. Identity
2. Prerequisites
3. Commands Reference
4. Workflow Playbooks
5. Guardrails
6. Output Parsing Guide
7. Agent Persona Routing

## Example Guardrails

- Never deploy to PROD without explicit human approval.
- Never fabricate IDs.
- Never deploy immediately after promotion without validation.
- Never expose API tokens.
- Always surface test failures.

---

# Workflow Playbooks

## Full Story Delivery

1. Verify authentication
2. Set story context
3. Ask Build Agent for guidance
4. Commit changes
5. Promote to UAT
6. Run tests
7. Ask for approval
8. Deploy to PROD
9. Generate release notes

## Failed Deployment Investigation

1. Retrieve failed job
2. Ask Release Agent for analysis
3. Present root cause
4. Request Build Agent fixes if needed

## Generate and Run Tests

1. Generate CRT script
2. Present for review
3. Ask for approval
4. Run suite
5. Retrieve results

---

# Output Parsing Guide

| Status | Meaning | Action |
|----------|----------|---------|
| Completed Successfully | Success | Continue |
| Completed with Errors | Partial failure | Stop |
| In Progress | Running | Poll |
| Failed | Failure | Invoke Release Agent |
| Test Succeeded | Passed | Continue |
| Test Failed | Failed | Stop |

---

# 🟠 Track C — Your Headless Idea

Example ideas:

- VS Code Extension
- Git Hooks Framework
- Slack / Teams Bot
- Raycast Extension
- MCP Server
- GitHub Actions Integration

Requirements:

- Use at least two Copado API surfaces
- Remove at least one browser-based workflow
- Open-source repository required

---

# Copado APIs

## CI/CD Actions API

| Method | Endpoint |
|----------|----------|
| POST | /actions/commit |
| POST | /actions/promote |
| POST | /actions/validate |
| POST | /actions/deploy |
| GET | /user-stories |
| GET | /environments |
| GET | /job-executions/{id} |

## Agentia Testing (CRT)

| Method | Endpoint |
|----------|----------|
| POST | /pace/v4/projects/{projectId}/jobs/{jobId}/builds |
| GET | Build Status |
| GET | Results |
| GET | Available Jobs |

Authentication: Personal Access Key (PAK)

## Agentia AI Context Hub

| Method | Endpoint |
|----------|----------|
| POST | /dialogues |
| POST | /dialogues/{id}/messages |
| GET | /dialogues/{id} |
| GET | /organizations/{orgId}/workspaces |

Agent IDs:

- plan
- build
- test
- release
- operate

---

# Submission Requirements

- GitHub Repository
- README.md
- SKILL.md (Track B required)
- Demo Video (≤ 5 min)
- Live Demo (10 min)
- Slide Deck (≤ 8 slides)

---

# Recommended Tech Stack

| Layer | Options |
|---------|---------|
| CLI | Oclif, Commander.js, Typer, Click, Cobra |
| Terminal UI | Ink, Rich, Bubble Tea |
| MCP | modelcontextprotocol/sdk, mcp |
| Auth | keytar, keyring |
| HTTP | axios, httpx |
| Formatting | chalk, rich, lipgloss |

---

# Rules

1. All code must be written during the hackathon.
2. Open-source libraries are allowed.
3. Use provided Copado credentials.
4. Never commit credentials.
5. Teams of 1–5 participants.
6. Copado UI allowed only for setup.
7. Use only Plan, Build, Test, Release, Operate agents.
8. Track C must document APIs and UI interactions removed.

---

## CopadoCON Bangalore | June 2026

> "Developers can do everything from the CLI."
