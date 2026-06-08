"""
Copado Genie — API client.

Two API surfaces:
  1. Copado AI Platform (Agentia): workspaces, dialogues, AI agent chat
     Base: https://copadogpt-api.robotic.copado.com
  2. Copado CI/CD Actions: commit, promote, deploy, job-executions
     Base: Salesforce org REST (via Copado managed package)

All external HTTP communication lives here — orchestrator never imports httpx directly.
"""

import json as jsonlib
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

import httpx


# ── Config & models ───────────────────────────────────────────────

COPADO_AI_BASE_URLS = {
    "US": "https://copadogpt-api.robotic.copado.com",
    "EU": "https://copadogpt-api.eu-robotic.copado.com",
    "AU": "https://copadogpt-api.au-robotic.copado.com",
    "SG": "https://copadogpt-api.sg-robotic.copado.com",
}


@dataclass
class CopadoConfig:
    api_key: str                     # Personal Access Key (PAK)
    org_id: int                      # Organization ID (integer)
    ai_base_url: str = COPADO_AI_BASE_URLS["US"]
    cicd_base_url: str = ""          # Salesforce org instance URL (for CI/CD)
    sf_token: str = ""               # Salesforce session token (for CI/CD REST)
    workspace_id: Optional[str] = None
    region: str = "US"


@dataclass
class UserStory:
    id: str
    name: str
    title: str
    project: str
    environment: str
    ready_to_promote: bool
    status: str = ""


@dataclass
class JobStatus:
    id: str
    status: str  # e.g. "In Progress", "Completed", "Successful", "Failed"
    progress: int = 0        # 0-100
    error_message: Optional[str] = None


@dataclass
class Workspace:
    id: str
    name: str
    description: str = ""
    capabilities: list[str] = field(default_factory=list)


@dataclass
class Dialogue:
    id: str
    name: str
    workspace_id: Optional[str] = None


# ── Client ────────────────────────────────────────────────────────

class CopadoClient:
    """Unified async client for Copado AI Platform + CI/CD APIs."""

    def __init__(self, config: CopadoConfig) -> None:
        self._config = config

        # Copado AI Platform client (workspaces, dialogues, agents)
        self._ai = httpx.AsyncClient(
            base_url=config.ai_base_url,
            headers={
                "X-Authorization": config.api_key,
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )

        # Copado CI/CD Actions client (commit, promote, deploy)
        # Uses Salesforce session token for auth against managed package REST API
        self._cicd = httpx.AsyncClient(
            base_url=config.cicd_base_url,
            headers={
                "Authorization": f"Bearer {config.sf_token}",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        ) if config.cicd_base_url and config.sf_token else None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self._ai.aclose()
        if self._cicd:
            await self._cicd.aclose()

    @property
    def org_id(self) -> int:
        return self._config.org_id

    # ── Workspace management (Copado AI Platform) ─────────────────

    async def list_workspaces(self) -> list[Workspace]:
        r = await self._ai.get(f"/organizations/{self.org_id}/workspaces")
        r.raise_for_status()
        return [
            Workspace(
                id=w["id"],
                name=w["name"],
                description=w.get("description", ""),
            )
            for w in r.json()
        ]

    async def create_workspace(
        self,
        name: str,
        description: str = "",
        capabilities: Optional[list[str]] = None,
    ) -> Workspace:
        body: dict[str, Any] = {"name": name, "description": description}
        if capabilities:
            body["capabilities"] = capabilities
        r = await self._ai.post(
            f"/organizations/{self.org_id}/workspaces", json=body
        )
        r.raise_for_status()
        d = r.json()
        return Workspace(
            id=d["id"],
            name=d["name"],
            description=d.get("description", ""),
            capabilities=d.get("capabilities", []),
        )

    async def get_workspace(self, workspace_id: str) -> Workspace:
        r = await self._ai.get(
            f"/organizations/{self.org_id}/workspaces/{workspace_id}"
        )
        r.raise_for_status()
        d = r.json()
        return Workspace(
            id=d["id"],
            name=d["name"],
            description=d.get("description", ""),
            capabilities=d.get("capabilities", []),
        )

    # ── Dialogue management (Copado AI Platform) ──────────────────

    async def create_dialogue(
        self,
        name: str,
        workspace_id: Optional[str] = None,
        assistant_id: str = "knowledge",
    ) -> Dialogue:
        ws_id = workspace_id or self._config.workspace_id
        body: dict[str, Any] = {"name": name}
        r = await self._ai.post(
            f"/organizations/{self.org_id}/dialogues", json=body
        )
        r.raise_for_status()
        d = r.json()
        return Dialogue(id=d["id"], name=d.get("name", name), workspace_id=ws_id)

    async def list_dialogues(
        self, workspace_id: Optional[str] = None, limit: int = 20
    ) -> list[Dialogue]:
        ws_id = workspace_id or self._config.workspace_id
        params: dict[str, Any] = {"limit": limit}
        if ws_id:
            params["workspace_id"] = ws_id
        r = await self._ai.get(
            f"/organizations/{self.org_id}/dialogues", params=params
        )
        r.raise_for_status()
        return [
            Dialogue(id=d["id"], name=d.get("name", ""))
            for d in r.json()
        ]

    async def get_dialogue(self, dialogue_id: str) -> dict:
        r = await self._ai.get(
            f"/organizations/{self.org_id}/dialogues/{dialogue_id}"
        )
        r.raise_for_status()
        return r.json()

    async def delete_dialogue(self, dialogue_id: str) -> None:
        r = await self._ai.delete(
            f"/organizations/{self.org_id}/dialogues/{dialogue_id}"
        )
        r.raise_for_status()

    # ── AI Agent chat (Copado AI Platform) ────────────────────────

    async def chat(
        self,
        dialogue_id: str,
        prompt: str,
        assistant_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Send a message in a dialogue and return the agent reply.

        The API returns application/x-ndjson (streaming tokens).
        We collect all token chunks and concatenate them.
        """
        body: dict[str, Any] = {
            "prompt": prompt,
            "request_id": str(uuid.uuid4()),
        }
        r = await self._ai.post(
            f"/organizations/{self.org_id}/dialogues/{dialogue_id}/messages",
            json=body,
            timeout=120.0,
        )
        r.raise_for_status()

        # Parse NDJSON stream: each line is a JSON object
        tokens: list[str] = []
        for line in r.text.strip().splitlines():
            if not line.strip():
                continue
            try:
                chunk = jsonlib.loads(line)
            except jsonlib.JSONDecodeError:
                continue
            if chunk.get("type") == "token":
                tokens.append(chunk.get("content", ""))
        return "".join(tokens)

    async def ask_agent(
        self,
        agent: str,
        message: str,
        workspace_id: Optional[str] = None,
    ) -> str:
        """Convenience: create a dialogue, send one message, return reply."""
        dialogue = await self.create_dialogue(
            name=f"copado-genie-{agent}",
            workspace_id=workspace_id,
            assistant_id=agent,
        )
        reply = await self.chat(
            dialogue_id=dialogue.id,
            prompt=message,
            assistant_id=agent,
        )
        return reply

    # ── Salesforce REST helpers ────────────────────────────────────

    def _sf(self) -> httpx.AsyncClient:
        """Return the CI/CD (Salesforce) client or raise."""
        if not self._cicd:
            raise RuntimeError(
                "CI/CD not configured. Run: copado-genie auth login --cicd-url <url> --sf-token <token>"
            )
        return self._cicd

    async def _soql(self, query: str) -> dict:
        """Execute a SOQL query and return parsed JSON."""
        r = await self._sf().get(
            "/services/data/v60.0/query/", params={"q": query}
        )
        r.raise_for_status()
        return r.json()

    async def _sobject_get(self, sobject: str, record_id: str) -> dict:
        r = await self._sf().get(
            f"/services/data/v60.0/sobjects/{sobject}/{record_id}"
        )
        r.raise_for_status()
        return r.json()

    async def _sobject_patch(self, sobject: str, record_id: str, fields: dict) -> None:
        r = await self._sf().patch(
            f"/services/data/v60.0/sobjects/{sobject}/{record_id}",
            json=fields,
        )
        if r.status_code >= 400:
            try:
                errors = r.json()
                msg = "; ".join(
                    e.get("message", str(e)) for e in errors
                ) if isinstance(errors, list) else str(errors)
            except Exception:
                msg = r.text
            raise httpx.HTTPStatusError(
                f"{r.status_code} {r.reason_phrase}: {msg}",
                request=r.request,
                response=r,
            )
        r.raise_for_status()

    async def _sobject_create(self, sobject: str, fields: dict) -> str:
        """Create a record and return its Id."""
        r = await self._sf().post(
            f"/services/data/v60.0/sobjects/{sobject}",
            json=fields,
        )
        r.raise_for_status()
        return r.json()["id"]

    # ── Environment resolution ────────────────────────────────────

    _env_cache: dict[str, str] = {}
    _env_name_cache: dict[str, str] = {}

    async def get_environment_name(self, env_id: str) -> str:
        """Get environment name by Id (cached)."""
        if not env_id:
            return "(none)"
        if env_id in self._env_name_cache:
            return self._env_name_cache[env_id]
        d = await self._sobject_get("copado__Environment__c", env_id)
        name = d.get("Name", env_id)
        self._env_name_cache[env_id] = name
        return name

    async def get_story_environment(self, story_id: str) -> tuple[str, str]:
        """Return (env_id, env_name) for the story's current environment."""
        data = await self._soql(
            f"SELECT copado__Environment__c FROM copado__User_Story__c "
            f"WHERE Id = '{story_id}' LIMIT 1"
        )
        records = data.get("records", [])
        if not records:
            raise ValueError(f"Story {story_id} not found")
        env_id = records[0].get("copado__Environment__c")
        if not env_id:
            return "", "(none)"
        env_name = await self.get_environment_name(env_id)
        return env_id, env_name

    async def resolve_environment(self, name: str) -> str:
        """Resolve an environment name (e.g. 'UAT') to its Salesforce record Id.

        Caches results for the lifetime of the client.
        """
        key = name.upper()
        if key in self._env_cache:
            return self._env_cache[key]

        data = await self._soql(
            f"SELECT Id, Name FROM copado__Environment__c "
            f"WHERE Name LIKE '%{name}%' ORDER BY Name ASC LIMIT 5"
        )
        records = data.get("records", [])
        if not records:
            raise ValueError(
                f"Environment '{name}' not found. "
                f"Check available environments with: copado-genie env list"
            )
        env_id = records[0]["Id"]
        self._env_cache[key] = env_id
        return env_id

    async def list_environments(self) -> list[dict]:
        """List all environments in the pipeline."""
        data = await self._soql(
            "SELECT Id, Name, copado__Type__c, copado__Platform__c "
            "FROM copado__Environment__c ORDER BY Name"
        )
        return data.get("records", [])

    # ── User stories (CI/CD via Salesforce REST) ─────────────────

    async def get_user_story(self, story_id: str) -> UserStory:
        """Fetch user story by Name (e.g. US-0000024) or by Salesforce Id."""
        if story_id.startswith("a"):
            d = await self._sobject_get("copado__User_Story__c", story_id)
        else:
            data = await self._soql(
                f"SELECT Id, Name, copado__User_Story_Title__c, copado__Status__c, "
                f"copado__Environment__c, copado__Project__c, copado__Promote_Change__c "
                f"FROM copado__User_Story__c WHERE Name = '{story_id}' LIMIT 1"
            )
            if not data.get("records"):
                raise ValueError(f"User story '{story_id}' not found")
            d = data["records"][0]
        return UserStory(
            id=d["Id"],
            name=d.get("Name", ""),
            title=d.get("copado__User_Story_Title__c", ""),
            project=d.get("copado__Project__c", ""),
            environment=d.get("copado__Environment__c", ""),
            ready_to_promote=d.get("copado__Promote_Change__c", False),
            status=d.get("copado__Status__c", ""),
        )

    async def list_user_stories(self, limit: int = 20) -> list[UserStory]:
        """List recent user stories."""
        data = await self._soql(
            f"SELECT Id, Name, copado__User_Story_Title__c, copado__Status__c, "
            f"copado__Environment__c, copado__Project__c, copado__Promote_Change__c "
            f"FROM copado__User_Story__c ORDER BY CreatedDate DESC LIMIT {limit}"
        )
        return [
            UserStory(
                id=r["Id"],
                name=r.get("Name", ""),
                title=r.get("copado__User_Story_Title__c", ""),
                project=r.get("copado__Project__c", ""),
                environment=r.get("copado__Environment__c", ""),
                ready_to_promote=r.get("copado__Promote_Change__c", False),
                status=r.get("copado__Status__c", ""),
            )
            for r in data.get("records", [])
        ]

    async def create_user_story(self, title: str, project_id: Optional[str] = None) -> UserStory:
        """Create a new user story and return it."""
        fields: dict[str, Any] = {
            "copado__User_Story_Title__c": title,
        }
        if project_id:
            fields["copado__Project__c"] = project_id
        record_id = await self._sobject_create("copado__User_Story__c", fields)
        return await self.get_user_story(record_id)

    async def update_story_status(self, story_id: str, fields: dict) -> None:
        """Update user story fields. story_id must be a Salesforce record Id."""
        await self._sobject_patch("copado__User_Story__c", story_id, fields)

    # ── CI/CD Actions ─────────────────────────────────────────────
    #
    # Field names verified against the actual Copado org via describe:
    #   User_Story_Commit__c: copado__User_Story__c, copado__CommitMessage__c,
    #                         copado__LastJobExecutionId__c, copado__Status__c
    #   Promotion__c:         copado__Source_Environment__c, copado__Destination_Environment__c,
    #                         copado__Project__c, copado__Status__c,
    #                         copado__Last_Promotion_Execution_Id__c
    #   User_Story__c:        copado__Promote_Change__c (flag only),
    #                         copado__Promote_and_Deploy__c (triggers job)
    #   JobExecution__c:      copado__UserStoryCommit__c, copado__Promotion__c,
    #                         copado__Status__c, copado__ErrorMessage__c

    async def _wait_for_promotion_job(
        self, story_sf_id: str, after_ts: str = "", timeout: int = 60
    ) -> str:
        """Poll until Copado creates a Promotion for the story after a flag update."""
        import asyncio
        import time

        start = time.monotonic()
        ts_clause = f"AND CreatedDate > {after_ts} " if after_ts else ""
        while True:
            data = await self._soql(
                f"SELECT Id, copado__Status__c, copado__Last_Promotion_Execution_Id__c "
                f"FROM copado__Promotion__c "
                f"WHERE Id IN (SELECT copado__Promotion__c FROM copado__Promoted_User_Story__c "
                f"WHERE copado__User_Story__c = '{story_sf_id}') "
                f"{ts_clause}"
                f"ORDER BY CreatedDate DESC LIMIT 1"
            )
            records = data.get("records", [])
            if records:
                job_id = records[0].get("copado__Last_Promotion_Execution_Id__c")
                return job_id or records[0]["Id"]

            if time.monotonic() - start > timeout:
                raise RuntimeError(
                    f"Timed out waiting for Copado to create a promotion for story {story_sf_id}."
                )
            await asyncio.sleep(5)

    async def commit(self, story_id: str, metadata: list[dict]) -> Optional[str]:
        """Trigger a commit for the user story via Copado.

        If a completed commit already exists, returns it immediately.
        Otherwise tries to create a User_Story_Commit__c record.
        Returns None if commit can't be done via API (needs Copado UI).
        """
        import asyncio
        import time

        # Check for existing commit first
        data = await self._soql(
            f"SELECT Id, copado__Status__c, copado__LastJobExecutionId__c "
            f"FROM copado__User_Story_Commit__c "
            f"WHERE copado__User_Story__c = '{story_id}' "
            f"ORDER BY CreatedDate DESC LIMIT 1"
        )
        existing = data.get("records", [])
        if existing:
            rec = existing[0]
            status = rec.get("copado__Status__c", "")
            if status in ("Complete", "Completed", "Successful"):
                return rec.get("copado__LastJobExecutionId__c") or rec["Id"]

        # No existing commit — try to create one
        try:
            commit_id = await self._sobject_create(
                "copado__User_Story_Commit__c",
                {
                    "copado__User_Story__c": story_id,
                },
            )
        except httpx.HTTPStatusError:
            # Copado requires Git snapshot reference — can't create via API
            return None

        start = time.monotonic()
        while time.monotonic() - start < 60:
            d = await self._sobject_get("copado__User_Story_Commit__c", commit_id)
            job_id = d.get("copado__LastJobExecutionId__c")
            if job_id:
                return job_id
            status = d.get("copado__Status__c", "")
            if status and status not in ("Draft", ""):
                return commit_id
            await asyncio.sleep(4)

        return commit_id

    async def promote(self, story_id: str, environment: str = "", validate: bool = False) -> str:
        """Promote (and deploy) a user story to the next environment.

        Sets copado__Promote_and_Deploy__c = True on the story, which
        triggers Copado to create a Promotion + Deployment automatically.
        Then polls until a NEW promotion appears and completes.
        """
        import asyncio
        import time

        # Get the latest promotion ID before we trigger
        before_data = await self._soql(
            f"SELECT Id FROM copado__Promotion__c "
            f"WHERE Id IN (SELECT copado__Promotion__c FROM copado__Promoted_User_Story__c "
            f"WHERE copado__User_Story__c = '{story_id}') "
            f"ORDER BY CreatedDate DESC LIMIT 1"
        )
        before_records = before_data.get("records", [])
        before_id = before_records[0]["Id"] if before_records else None

        await self._sobject_patch(
            "copado__User_Story__c",
            story_id,
            {"copado__Promote_and_Deploy__c": True},
        )

        # Poll for a NEW promotion (different ID from before_id)
        start = time.monotonic()
        promo_id = None
        exec_id = None

        while time.monotonic() - start < 180:
            data = await self._soql(
                f"SELECT Id, copado__Status__c, copado__Last_Promotion_Execution_Id__c "
                f"FROM copado__Promotion__c "
                f"WHERE Id IN (SELECT copado__Promotion__c FROM copado__Promoted_User_Story__c "
                f"WHERE copado__User_Story__c = '{story_id}') "
                f"ORDER BY CreatedDate DESC LIMIT 1"
            )
            records = data.get("records", [])
            if records:
                rec = records[0]
                new_id = rec["Id"]
                # Only process if this is a NEW promotion
                if new_id != before_id:
                    promo_id = new_id
                    exec_id = rec.get("copado__Last_Promotion_Execution_Id__c")
                    status = rec.get("copado__Status__c", "")
                    if status in ("Completed", "Succeeded", "Successful", "Done"):
                        return exec_id or promo_id
                    if "Error" in status or "Fail" in status:
                        raise RuntimeError(f"Promotion failed with status: {status}")
            await asyncio.sleep(5)

        return exec_id or promo_id or "unknown"

    async def validate(self, story_id: str, environment: str = "") -> str:
        """Validate-only deployment (dry run). Sets Promote_Change flag only."""
        await self._sobject_patch(
            "copado__User_Story__c",
            story_id,
            {"copado__Promote_Change__c": True},
        )
        from datetime import datetime, timezone
        now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return await self._wait_for_promotion_job(story_id, after_ts=now_ts)

    async def deploy(self, story_id: str, environment: str = "") -> str:
        """Deploy a promoted story to the next environment (typically PROD).

        After UAT, the story is on UAT. Setting Promote_and_Deploy again
        pushes it to the next pipeline stage (Production).
        """
        return await self.promote(story_id, environment)

    # ── Job lookup (CI/CD via Salesforce REST) ──────────────────

    async def get_latest_job_for_story(self, story_id: str) -> Optional[str]:
        """Return the most recent Job Execution ID for a story, or None.

        Jobs link to stories via User_Story_Commit or Promotion, not directly.
        """
        data = await self._soql(
            f"SELECT Id FROM copado__User_Story_Commit__c "
            f"WHERE copado__User_Story__c = '{story_id}' "
            f"ORDER BY CreatedDate DESC LIMIT 1"
        )
        records = data.get("records", [])
        if records:
            d = await self._sobject_get("copado__User_Story_Commit__c", records[0]["Id"])
            job_id = d.get("copado__LastJobExecutionId__c")
            if job_id:
                return job_id

        data = await self._soql(
            f"SELECT Id, copado__Last_Promotion_Execution_Id__c FROM copado__Promotion__c "
            f"WHERE Id IN (SELECT copado__Promotion__c FROM copado__Promoted_User_Story__c "
            f"WHERE copado__User_Story__c = '{story_id}') "
            f"ORDER BY CreatedDate DESC LIMIT 1"
        )
        records = data.get("records", [])
        if records:
            return records[0].get("copado__Last_Promotion_Execution_Id__c") or records[0]["Id"]
        return None

    # ── Job polling (CI/CD via Salesforce REST) ──────────────────

    async def get_job_status(self, job_id: str) -> JobStatus:
        """Get status of a Copado Job Execution or Promotion."""
        try:
            d = await self._sobject_get("copado__JobExecution__c", job_id)
            return JobStatus(
                id=d["Id"],
                status=d.get("copado__Status__c", "In Progress"),
                progress=0,
                error_message=d.get("copado__ErrorMessage__c"),
            )
        except httpx.HTTPStatusError:
            pass
        try:
            d = await self._sobject_get("copado__Promotion__c", job_id)
            return JobStatus(
                id=d["Id"],
                status=d.get("copado__Status__c", "In Progress"),
                progress=0,
                error_message=None,
            )
        except httpx.HTTPStatusError:
            pass
        try:
            d = await self._sobject_get("copado__User_Story_Commit__c", job_id)
            return JobStatus(
                id=d["Id"],
                status=d.get("copado__Status__c", "In Progress"),
                progress=0,
                error_message=None,
            )
        except httpx.HTTPStatusError:
            pass
        return JobStatus(id=job_id, status="Completed", progress=100)

    # ── Testing (Agentia CRT — optional) ──────────────────────────

    async def list_test_suites(self, project_id: str) -> list[dict]:
        """List available CRT test suites for a project."""
        r = await self._sf().get(
            f"/pace/v4/projects/{project_id}/jobs"
        )
        r.raise_for_status()
        return r.json()

    async def run_tests(self, project_id: str, suite_id: str) -> str:
        """Trigger a CRT test suite run. Returns build/job ID."""
        r = await self._sf().post(
            f"/pace/v4/projects/{project_id}/jobs/{suite_id}/builds"
        )
        r.raise_for_status()
        return r.json()["buildId"]

    async def get_test_results(self, project_id: str, build_id: str) -> dict:
        """Retrieve CRT test results for a completed build."""
        r = await self._sf().get(
            f"/pace/v4/projects/{project_id}/builds/{build_id}/results"
        )
        r.raise_for_status()
        return r.json()

    # ── Platform Workflows (Copado AI Platform) ───────────────────

    async def list_workflows(self) -> list[dict]:
        r = await self._ai.get(f"/organizations/{self.org_id}/workflows")
        r.raise_for_status()
        return r.json()

    async def create_workflow_run(
        self, workflow_id: str, workspace_id: str
    ) -> dict:
        r = await self._ai.post(
            f"/organizations/{self.org_id}/workflows/runs",
            json={
                "workflow_id": workflow_id,
                "workspace_id": workspace_id,
            },
        )
        r.raise_for_status()
        return r.json()

    async def get_workflow_runs(
        self, status: Optional[list[str]] = None, limit: int = 10
    ) -> list[dict]:
        params: dict[str, Any] = {"limit": limit}
        if status:
            for s in status:
                params.setdefault("status", []).append(s)
        r = await self._ai.get(
            f"/organizations/{self.org_id}/workflows/runs", params=params
        )
        r.raise_for_status()
        return r.json()
