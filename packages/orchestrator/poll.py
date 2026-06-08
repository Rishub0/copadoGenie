"""
Poll a Copado async job until it finishes.
Mirrors the UI's "View deployment status" screen — jobs run in the background.
"""

import asyncio
import time
from typing import Callable, Optional

from copado_api.client import CopadoClient, JobStatus

TERMINAL_STATUSES = {"Completed", "Completed with Errors", "Failed", "Successful", "Succeeded"}

DEFAULT_INTERVAL_S = 5
DEFAULT_TIMEOUT_S = 600   # 10 minutes


async def poll_until_complete(
    client: CopadoClient,
    job_id: str,
    on_progress: Optional[Callable[[JobStatus], None]] = None,
    interval_s: int = DEFAULT_INTERVAL_S,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> JobStatus:
    """
    Loops GET /job-executions/{id} until the job reaches a terminal state.
    Raises RuntimeError on timeout or failure.
    """
    start = time.monotonic()

    while True:
        status = await client.get_job_status(job_id)

        if on_progress:
            on_progress(status)

        if status.status in TERMINAL_STATUSES:
            return status

        elapsed = time.monotonic() - start
        if elapsed > timeout_s:
            raise RuntimeError(
                f"Job {job_id} timed out after {timeout_s}s "
                f"(last status: {status.status})"
            )

        await asyncio.sleep(interval_s)
