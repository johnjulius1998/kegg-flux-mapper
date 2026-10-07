"""In-process background jobs, so long solves don't hold a Dash request thread.

Jobs run in this process (not Dash's DiskcacheManager workers) so their results land
in the same in-memory analysis cache that the map callbacks read from.
"""

import threading
import uuid
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="kfm-job")
_jobs: "OrderedDict[str, Job]" = OrderedDict()
_lock = threading.Lock()
_MAX_JOBS = 32


@dataclass
class Job:
    id: str
    stage: str = "Queued…"
    future: Future | None = field(default=None, repr=False)

    @property
    def done(self) -> bool:
        return self.future is not None and self.future.done()

    def result(self):
        return self.future.result()


def submit(fn: Callable, *args) -> str:
    """Run `fn(*args, progress=callback)` in the pool; returns the job id."""
    job = Job(uuid.uuid4().hex)

    def progress(stage: str):
        job.stage = stage

    with _lock:
        _jobs[job.id] = job
        while len(_jobs) > _MAX_JOBS:
            oldest = next(iter(_jobs.values()))
            if not oldest.done:
                break
            _jobs.popitem(last=False)
    job.future = _executor.submit(fn, *args, progress=progress)
    return job.id


def get(job_id: str | None) -> Job | None:
    with _lock:
        return _jobs.get(job_id) if job_id else None


def forget(job_id: str | None) -> None:
    """Stop tracking a job. A solve already running finishes and still fills the cache."""
    with _lock:
        job = _jobs.pop(job_id, None) if job_id else None
    if job is not None and job.future is not None:
        job.future.cancel()
