# Copado UI Deployment Flow — Beginner's Guide

This document explains **how Copado moves Salesforce changes from a developer sandbox all the way to Production**, using the real end-to-end flow from our reference demo (custom object + field on a dev1 → UAT → Production pipeline).

If you are building the **headless CLI** (`copado-genie`), treat each section's **"Headless equivalent"** notes as the commands or API calls you will eventually automate.

---

## The Big Picture

Think of Copado like a **package delivery system**:

| Real world | Copado |
|------------|--------|
| Shipping label | **User story** — nothing ships without one |
| Your workshop (where you build) | **Dev sandbox** (linked via **Credentials**) |
| Packing your items into a box | **Commit** — select metadata and save to Git |
| "Ready for pickup" sticker | **Ready to Promote** — tells the release manager you're done |
| Truck to the next warehouse | **Promote and Deploy** — merge Git branches and install in the next org |
| Final delivery | **Production** deploy |

```text
  [Dev Sandbox]     [UAT Org]          [Production]
       │                │                    │
   Build metadata   Test changes        Live users
       │                │                    │
       └──── Commit ────┴── Promote/Deploy ──┘
              (via User Story + Git branches)
```

**Golden rule:** In Copado, you **cannot deploy anything without a user story**. Every change is tied to a story for traceability and selective releases.

---

## What We Deploy in the Demo

| Item | Detail |
|------|--------|
| Custom object | `Copado_Demo__c` (example name in video) |
| Custom field | `Description__c` on that object |
| Dev org | **dev1** sandbox (chosen when creating the user story) |
| Route | dev1 → **UAT** → **Production** (defined by **Pipeline** + **Project**) |

---

## Step 1 — Create a User Story

**Where in UI:** Copado org → **New User Story**

A user story is the **container** for your work. It links your Salesforce changes, Git commits, and deployments together.

### Required fields

| Field | Why it matters |
|-------|----------------|
| **Title** | Describes the work (e.g. "Create Copado Demo object") |
| **Project** | **Required.** Your pipeline is connected to a project — the story must belong to that project |
| **Credentials** | **Required.** Tells Copado *which Salesforce org* you develop in (e.g. dev1 sandbox) |

Other fields are optional for the demo.

### What happens after you save

- Copado assigns a **user story number** (e.g. US-0001234).
- A **path** appears on the story — a visual route through environments (e.g. dev1 → UAT → PROD).
- The path is **automatic**: it comes from your **pipeline** configuration and the **credentials** you picked, not something you draw by hand.

```text
  User Story
  ├── Title: "Create Copado Demo object"
  ├── Project: MyProject          ← links to pipeline
  ├── Credentials: dev1        ← dev org
  └── Path: dev1 → UAT → PROD  ← auto-generated
```

> **Tip for beginners:** Stories can also arrive from Jira or other tools and sync into Copado. For learning, creating the story directly in Copado is fine.

**Headless equivalent:** `copado-genie story create`, `copado-genie story set --id <id>`

---

## Step 2 — Build in Salesforce (Dev Org)

**Where in UI:** User story → **Credentials** record → **Open Org**

This step happens **inside Salesforce**, not in Copado's deployment screens:

1. Open the dev sandbox (dev1).
2. Go to **Setup → Object Manager**.
3. Create the custom object and fields (e.g. `Description__c`).

Copado does not create metadata for you here — you build first, then **tell Copado what to pick up** in the next step.

```text
  Developer                    Salesforce (dev1)
      │                              │
      │── Open Org ─────────────────►│ Create object + fields
      │                              │
      │◄── metadata exists in org ───│
```

**Headless equivalent:** No Copado API — document in SKILL.md that metadata must exist in the dev org before commit.

---

## Step 3 — Commit Changes (Attach Metadata to the Story)

**Where in UI:** User story → **Copado Changes** → **Commit Changes**

Committing means: *"Take the Salesforce metadata I select and save it to Git, linked to this user story."*

### 3.1 — The metadata grid

You see a **grid of all metadata** in your dev org. Use it to select what goes into this commit.

| UI action | What it does |
|-----------|----------------|
| **Refresh Retrieve Changes** | Calls your org and pulls the **latest** metadata (use this if you just created something and don't see it) |
| **Last refreshed** | Shown at the bottom of the grid — know how fresh the list is |
| **Filters** | Find items by name, type, who modified, date, etc. |
| **Select rows** | Choose components to include in this commit |
| **Selected Metadata** | Review only what you've checked |
| **Branch name** | Can edit before committing (advanced) |
| **Commit Changes** | Starts the commit job |

### 3.2 — Critical beginner mistake (from the video)

The demo committed **only the custom object**, not the **Description** field.

**Result:** Object appeared in UAT, but the custom field did **not**.

| You select | What actually gets committed |
|------------|------------------------------|
| Object only | Object + **standard fields only** |
| Object + custom fields + layouts + etc. | Everything you explicitly selected |

**Rule of thumb:** When you commit an object, also select **every related piece** you need:

- Custom fields  
- Page layouts  
- Record types  
- Validation rules  
- Other dependencies  

```text
  ❌  Select: CustomObject only
      →  UAT gets object, misses Description__c

  ✅  Select: CustomObject + CustomField + layouts...
      →  UAT gets the full package
```

### 3.3 — What Copado does behind the scenes (Git)

On **first commit** for a user story, Copado:

1. Creates a new **feature branch** from the **master** (main) branch.  
2. **Compares** your selected metadata to what is on master.  
3. **Commits** the differences into that feature branch.

On **later commits** for the **same** user story:

- **No new branch** — changes go to the **same feature branch**.

```text
  master (main)
      │
      └── feature/US-1234  ← one branch per user story
              ├── commit 1: object
              └── commit 2: more metadata (same branch)
```

**Why feature branches per story?**  
So Copado can deploy **by user story**. If five stories are ready but the business only wants two, you select those two at promotion time — each story's changes live in its own branch.

### 3.4 — After commit finishes

| Where to check | Purpose |
|----------------|---------|
| Job / progress screen | Real-time status; you can **Go back and work** while it runs |
| **Build** tab on user story | Double-check selected metadata |
| **View in Git** | See the feature branch, latest commit, and files |

**Headless equivalent:** `copado-genie commit`, `POST /actions/commit` (+ retrieve/refresh before select)

---

## Step 4 — Mark "Ready to Promote" (Handoff to Release)

**Where in UI:** User story → **Deliver** tab → **Ready to Promote** checkbox → **Save**

This step does **not** deploy anything yet. It is a **signal**:

> "Development is done. This story can move to the next environment."

### What changes on the Pipeline Manager

Before checking the box:

```text
  Pipeline:  dev1 [0]  →  UAT  →  Production
                      ↑
                 zero stories waiting
```

After checking **Ready to Promote**:

```text
  Pipeline:  dev1 [1]  →  UAT  →  Production
                      ↑
                 one story ready to promote
```

The number is a **count** of ready stories. Five stories ready → **[5]**.

**Headless equivalent:** Story status / ready flag (confirm exact API with hackathon credentials)

---

## Step 5 — Promote and Deploy to UAT

**Where in UI:** **Pipeline Manager** → click the count on the source environment (e.g. **dev1 [1]**)

### 5.1 — Select stories and start

1. See all user stories marked **Ready to Promote**.  
2. **Select** which ones to include (one or many).  
3. Click **Promote and Deploy**.

### 5.2 — What Copado does behind the scenes

```text
  destination branch (e.g. "UAT")
      │
      └── new promotion branch
              │
              ├── merge feature branch(es) from selected stories
              ├── create deployment package
              └── deploy package → UAT Salesforce org
```

| Term | Simple meaning |
|------|----------------|
| **Feature branch** | Your story's changes in Git (from commit) |
| **Destination branch** | The Git branch for the target env (e.g. UAT) |
| **Promotion branch** | Temporary branch for *this* promotion run |
| **Package** | Bundle Copado installs into the target org |

You do **not** have to stay on the progress screen — the job runs in the background.

### 5.3 — Monitor the job

| Record / screen | What you see |
|-----------------|--------------|
| **Promotion record** | Which feature branches merge in; which user stories are included |
| **Deployment record** | Linked from promotion; overall job status |
| **View deployment status** | Per-component progress (helpful for large deployments) |
| **Steps** | e.g. promotion step; pipelines may add pre/post deployment steps later |

Success looks like: **Completed**, **100%**.

### 5.4 — After UAT succeeds

Copado **automatically updates** the user story:

| Field / UI | New value |
|------------|-----------|
| **Credentials** | Points to UAT org |
| **Environment** | UAT |
| **Path** | Shows progress — current stage is UAT |
| **Ready to Promote** | **Unchecked** (reset for the next leg) |
| **Pipeline — UAT node** | **Green icon** = deployed successfully |

Verify in Salesforce: log into UAT → Object Manager → confirm your object (and fields you committed!) exist.

**Headless equivalent:** `copado-genie promote --env UAT`, `copado-genie status --watch`, `GET /job-executions/{id}`

---

## Step 6 — Promote and Deploy to Production

**Where in UI:** User story → **Deliver** tab (again)

After UAT, the story is ready for the **final leg**. The video uses a slightly different checkbox than Step 4.

### Two checkboxes on Deliver (important!)

| Checkbox | What it does |
|----------|----------------|
| **Ready to Promote** | **Flag only** — story shows on pipeline count; release manager promotes later |
| **Promote and Deploy** | **Starts** promotion + deployment **immediately** when you save |

For **Production** in the demo:

1. **Ready to Promote** was **unchecked** after UAT (automatic reset).  
2. Check **Promote and Deploy** (not only Ready to Promote).  
3. **Save**.

Copado creates **promotion** and **deployment** records in the background and starts the job.

### Monitor (same pattern as UAT)

- Open **Promotions** on the user story.  
- Promotion shows path: **UAT → Production**.  
- Open **Deployment** → watch status until complete.

### After Production succeeds

| Signal | Meaning |
|--------|---------|
| Pipeline **Production** node | Green icon |
| User story **path** | All stages green |
| Salesforce Production org | Object (and committed components) are live |

**Headless equivalent:** `copado-genie deploy --env PROD` or promote to PROD; **mandatory human approval** before PROD in your orchestrator (not shown in UI video, but required for your hackathon design)

---

## Git Branches — Visual Summary

Two branch types appear in every Copado deployment. Beginners often confuse them — this table helps:

```text
  COMMIT (once per story, reused)
  ─────────────────────────────────
  master ──► feature/US-xxxx  (your story's work)

  PROMOTE & DEPLOY (each promotion run)
  ───────────────────────────────────────
  uat-branch ──► promotion-run-123 ──► merge features ──► deploy to UAT org
```

| Branch type | Created when | Branched from | How many |
|-------------|--------------|---------------|----------|
| **Feature branch** | First commit on a user story | Master | **One per user story** (reused for more commits) |
| **Promotion branch** | Each Promote and Deploy | Destination env branch (UAT, PROD, etc.) | **One per promotion/deployment run** |

**Selective release example:**

```text
  Ready:  US-1, US-2, US-3, US-4, US-5  (all on pipeline count)
  Ship:   US-2, US-4 only               (select in promote screen)
          → only those feature branches merge and deploy
```

---

## Full Flow Checklist

Use this as a linear checklist when learning or scripting the headless path:

```text
 ☐  1.  Create user story (title, project*, credentials*)
 ☐  2.  Open dev org → build metadata in Salesforce
 ☐  3.  Copado Changes → Commit Changes
 ☐  4.  Refresh Retrieve Changes (if new metadata missing from grid)
 ☐  5.  Select ALL needed metadata (object + fields + dependencies)
 ☐  6.  Commit Changes → wait for job (feature branch created/updated)
 ☐  7.  Verify: Build tab, View in Git
 ☐  8.  Deliver → Ready to Promote → Save
 ☐  9.  Pipeline Manager → click env count → select stories → Promote and Deploy
 ☐ 10.  Monitor promotion + deployment → 100% complete
 ☐ 11.  Confirm UAT: story path/credentials, pipeline green, org has metadata
 ☐ 12.  Deliver → Promote and Deploy → Save  (for Production in demo)
 ☐ 13.  Monitor UAT → PROD job
 ☐ 14.  Confirm PROD: path all green, pipeline green, object in Production
```

---

## Extra Concepts (Mentioned in Video)

### Back-promotion

Sometimes a story is promoted **upstream**, but a **lower** environment's Git branch does not have those changes yet. The pipeline may show a **backward error count**.

**Back-promotion** syncs metadata from a higher environment back to lower ones. Plan as a future CLI feature; not step-by-step in the demo.

### Pre- and post-deployment steps

Real pipelines can run steps **before** and **after** deployment (e.g. backups, manual tasks). The simple demo only showed the core **promotion** step.

### Async jobs

Commit, promote, and deploy are **background jobs**. You can navigate away and check status later — your CLI should **poll** status (`status --watch`) the same way the UI's "View deployment status" does.

---

## Mapping UI → Headless CLI (Quick Reference)

| UI step | Suggested automation |
|---------|----------------------|
| Create / set user story | `story create`, `story set` |
| Refresh metadata list | Retrieve before commit (API TBD with credentials) |
| Commit selected metadata | `commit` |
| Ready to promote | Story flag / status update |
| Promote to UAT | `promote --env UAT` |
| Validate (recommended) | `promote --env UAT --validate` |
| Poll job | `status`, `status --watch` |
| Deploy to PROD | `deploy --env PROD` + **approval gate** |
| Run tests | `test run` (CRT — not in UI video) |
| Failed deploy analysis | `ai ask --agent release` |

---

## Suggested Orchestrator Workflow

For `copado-genie workflow run` and **SKILL.md** playbooks, encode this **deterministic** sequence:

```text
auth login
  → story set --id <US-xxxx>
  → commit                    (warn: select full metadata set)
  → ready_to_promote          (or skip if using promote-and-deploy only)
  → promote --env UAT
  → status --watch            (until complete)
  → test run                  (if in your pipeline)
  → APPROVAL GATE             (human: deploy to PROD?)
  → deploy --env PROD
  → status --watch
  → print deployment summary
```

---

## Source

Derived from the end-to-end Copado UI walkthrough in [`transcript.txt`](transcript.txt) (custom object demo). **Our dev org:** dev1 → UAT → Production.

For hackathon architecture and priorities, see [`decisions.md`](decisions.md) and [`architecture.md`](architecture.md).

**Implementation note:** Headless automation is delivered via **`copado-genie` CLI + orchestrator** (and [`skill.md`](skill.md) for IDE agents). An optional MCP wrapper may be added later; it would call the same orchestrator without changing this flow.
