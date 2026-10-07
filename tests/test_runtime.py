"""Phase 3: in-process job runner, progress stages, env-driven config."""

import os
import subprocess
import sys
import time

from kfm import analysis, jobs
from kfm.config import ROOT


def _wait(job_id, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = jobs.get(job_id)
        if job.done:
            return job
        time.sleep(0.05)
    raise TimeoutError(job_id)


def test_job_reports_progress_and_result():
    def work(x, progress):
        progress("half")
        time.sleep(0.2)
        progress("done")
        return x * 2

    jid = jobs.submit(work, 21)
    job = _wait(jid)
    assert job.result() == 42 and job.stage == "done"
    jobs.forget(jid)
    assert jobs.get(jid) is None


def test_analysis_job_builds_full_view(fructose, model_path):
    from kfm.ui.callbacks.wizard import AnalysisView, run_and_render
    view = _wait(jobs.submit(run_and_render, model_path, "m9_fructose", False, None)).result()
    assert isinstance(view, AnalysisView)
    assert view.key_a == fructose[0] and view.key_b is None and view.mode == "single"
    assert len(view.pathways) == 121 and view.run["a"].startswith("M9 — Fructose")


def test_analysis_job_reports_failure_in_status():
    from kfm.ui.callbacks.wizard import run_and_render
    view = _wait(jobs.submit(run_and_render, "/etc/passwd", "m9_fructose", False, None)).result()
    assert "Analysis failed" in str(view.status)


def test_progress_stages_in_order(model_path):
    stages = []
    analysis.run_analysis(model_path, "m9_succinate", progress=stages.append)
    assert stages == ["Loading model…", "Applying medium…", "Solving pFBA…",
                      "Mapping to KEGG…", "Summarising exchanges…"]


def test_env_config():
    env = {**os.environ, "KFM_PORT": "9123", "KFM_DEBUG": "yes", "KFM_CACHE_SIZE": "oops",
           "KFM_HOST": "0.0.0.0"}
    out = subprocess.run(
        [sys.executable, "-c",
         "from kfm import config as c; print(c.HOST, c.PORT, c.DEBUG, c.ANALYSIS_CACHE_SIZE)"],
        cwd=ROOT, env=env, capture_output=True, text=True, check=True).stdout.split()
    assert out == ["0.0.0.0", "9123", "True", "8"]
