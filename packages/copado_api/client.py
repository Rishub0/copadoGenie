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


@dataclass
class JobStatus:
    id: str
    status: Literal["In Progress", "Completed", "Completed with Errors", "Failed"]
    progress: int = 0        # 0–100
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
        r.raise_for_status()

    async def _sobject_create(self, sobject: str, fields: dict) -> str:
        """Create a record and return its Id."""
        r = await self._sf().post(
            f"/services/data/v60.0/sobjects/{sobject}",
            json=fields,
        )
        r.raise_for_status()
        return r.json()["id"]

    # ── User stories (CI/CD via Salesforce REST) ─────────────────

    async def get_user_story(self, story_id: str) -> UserStory:
        """Fetch user story by Name (e.g. US-0000024) or by Salesforce Id."""
        if story_id.startswith("a"):
            # Looks like a Salesforce record Id
            d = await self._sobject_get("copado__User_Story__c", story_id)
        else:
            # Lookup by Name
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

    # ── CI/CD Actions (via Salesforce REST) ──────────────────────

    async def commit(self, story_id: str, metadata: list[dict]) -> str:
        """Trigger a commit via Copado. Returns the Job Execution Id."""
        # Mark story as ready and create a snapshot commit action
        job_id = await self._sobject_create(
            "copado__JobExecution__c",
            {
                "copado__UserStoryCommit__c": story_id,
                "copado__Status__c": "In Progress",
            },
        )
        return job_id

    async def promote(self, story_id: str, environment: str = "", validate: bool = False) -> str:
        """Mark story for promotion and trigger deployment to environment.

        Returns a Job Execution Id that can be polled.
        """
        # Set Promote_Change flag on the user story
        await self._sobject_patch(
            "copado__User_Story__c",
            story_id,
            {"copado__Promote_Change__c": True},
        )

        # Create a promote+deploy job execution so we can poll it
        job_id = await self._sobject_create(
            "copado__JobExecution__c",
            {
                "copado__User_Story__c": story_id,
                "copado__Status__c": "In Progress",
                "copado__Type__c": "Validate and Deploy" if validate else "Promote and Deploy",
                "copado__To_Environment__c": environment,
            },
        )
        return job_id

    async def validate(self, story_id: str, environment: str = "") -> str:
        """Validate-only deployment (dry run) to an environment. Returns job Id."""
        return await self.promote(story_id, environment, validate=True)

    async def deploy(self, story_id: str, environment: str = "") -> str:
        """Deploy a promoted story to an environment. Returns job Id.

        Queries for the latest Promotion record, then triggers a deploy action on it.
        """
        # Query for the latest promotion related to this story
        data = await self._soql(
            f"SELECT Id, Name FROM copado__Promotion__c "
            f"WHERE copado__User_Story__c = '{story_id}' "
            f"ORDER BY CreatedDate DESC LIMIT 1"
        )
        if not data.get("records"):
            raise RuntimeError(
                f"No promotion found for story {story_id}. "
                "Run promote first before deploying."
            )

        promo_id = data["records"][0]["Id"]

        # Create a deploy job execution tied to this promotion
        job_id = await self._sobject_create(
            "copado__JobExecution__c",
            {
                "copado__Promotion__c": promo_id,
                "copado__User_Story__c": story_id,
                "copado__Status__c": "In Progress",
                "copado__Type__c": "Deploy",
                "copado__To_Environment__c": environment or "Production",
            },
        )
        return job_id

    # ── Job lookup (CI/CD via Salesforce REST) ──────────────────

    async def get_latest_job_for_story(self, story_id: str) -> Optional[str]:
        """Return the most recent Job Execution ID for a story, or None."""
        data = await self._soql(
            f"SELECT Id FROM copado__JobExecution__c "
            f"WHERE copado__User_Story__c = '{story_id}' "
            f"ORDER BY CreatedDate DESC LIMIT 1"
        )
        records = data.get("records", [])
        return records[0]["Id"] if records else None

    # ── Job polling (CI/CD via Salesforce REST) ──────────────────

    async def get_job_status(self, job_id: str) -> JobStatus:
        """Get status of a Copado Job Execution."""
        try:
            d = await self._sobject_get("copado__JobExecution__c", job_id)
            return JobStatus(
                id=d["Id"],
                status=d.get("copado__Status__c", "In Progress"),
                progress=0,
                error_message=d.get("copado__ErrorMessage__c"),
            )
        except httpx.HTTPStatusError:
            # Might be a promotion ID — check promotion status
            d = await self._sobject_get("copado__Promotion__c", job_id)
            return JobStatus(
                id=d["Id"],
                status=d.get("copado__Status__c", "In Progress"),
                progress=0,
                error_message=None,
            )

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
