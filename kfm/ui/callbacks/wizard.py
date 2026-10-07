"""Analysis setup: wizard inputs, Analyse, and the substrate growth screen."""

import base64
from pathlib import Path
from typing import Any, NamedTuple

import dash_bootstrap_components as dbc
from dash import Input, Output, State, no_update

from ... import analysis, jobs
from ...experiments import default_experiment_for, experiment_for_key
from .. import components as ui
from ..common import MODEL_OPTIONS, model_label


class AnalysisView(NamedTuple):
    """Everything an analysis run updates; field order defines the callback Outputs."""
    key_a: Any
    key_b: Any
    mode: Any
    status: Any
    info: Any
    pathways: Any
    run: Any


_TARGETS = AnalysisView(
    key_a=("store-key-a", "data"), key_b=("store-key-b", "data"),
    mode=("mode-seg", "value"), status=("analyse-status", "children"),
    info=("info-panels", "children"), pathways=("store-pathways", "data"),
    run=("store-run", "data"))
_UNCHANGED = AnalysisView(*[no_update] * len(AnalysisView._fields))


def analysis_outputs():
    return [Output(cid, prop, allow_duplicate=True) for cid, prop in _TARGETS]


def run_and_render(model_path, exp_a, compare_on, exp_b, progress=None) -> AnalysisView:
    """Run pFBA for `exp_a` (+ optional `exp_b`) and build every view update.

    Runs inside a `jobs` worker thread; `progress` receives stage labels.
    """
    step = progress or (lambda _s: None)
    if not model_path:
        return _UNCHANGED._replace(status=ui.status(False, "Choose or upload a model first."))
    try:
        key_a, res_a = analysis.get_analysis(
            model_path, exp_a, progress=(lambda s: step(f"A · {s}")) if compare_on else step)
        key_b = analysis.get_analysis(model_path, exp_b, progress=lambda s: step(f"B · {s}"))[0] \
            if compare_on else None
    except Exception as exc:  # UI boundary: report any failure in the status line
        return _UNCHANGED._replace(
            status=ui.status(False, f"Analysis failed — {type(exc).__name__}: {exc}"))

    run = {"model": model_label(model_path), "a": experiment_for_key(exp_a).label,
           "b": experiment_for_key(exp_b).label if compare_on else None}
    if res_a.scores.empty:
        return AnalysisView(key_a, key_b, "single",
                            ui.status(False, "Solved, but no reactions map to KEGG pathways "
                                             "(no kegg.reaction or ec-code annotations)."),
                            ui.info_panels(res_a), [], run)

    status = ui.status(True, f"{res_a.method}  ·  objective {res_a.objective_value:.4g}  ·  "
                             f"{res_a.n_active}/{res_a.n_rxn} active",
                       title=" | ".join(res_a.notes))
    return AnalysisView(key_a, key_b, "compare" if compare_on else "single", status,
                        ui.info_panels(res_a), res_a.scores.to_dict("records"), run)


def register(app):

    @app.callback(Output("model-select", "options"), Output("model-select", "value"),
                  Output("experiment-select", "value"), Output("upload-error", "children"),
                  Input("model-upload", "contents"), State("model-upload", "filename"),
                  prevent_initial_call=True)
    def on_upload(contents, filename):
        if not contents or not filename:
            return no_update, no_update, no_update, no_update
        b64 = contents.split(",", 1)[-1]
        if len(b64) * 3 // 4 > analysis.MAX_UPLOAD_BYTES:
            return no_update, no_update, no_update, "File too large."
        try:
            dest = analysis.save_upload(filename, base64.b64decode(b64))
        except ValueError as exc:
            return no_update, no_update, no_update, str(exc)
        opts = MODEL_OPTIONS + [{"label": f"⬆ {Path(dest).name}", "value": dest}]
        return opts, dest, default_experiment_for(dest), None

    @app.callback(Output("experiment-select", "value", allow_duplicate=True),
                  Input("model-select", "value"), prevent_initial_call=True)
    def on_model_change(model_path):
        return default_experiment_for(model_path or "")

    @app.callback(Output("experiment-desc", "children"), Input("experiment-select", "value"))
    def show_desc(key):
        return experiment_for_key(key).description if key else ""

    @app.callback(Output("experiment-b-wrap", "is_open"),
                  Output("experiment-b-select", "value"),
                  Input("compare-toggle", "value"), State("experiment-select", "value"))
    def toggle_compare(value, exp_a):
        if "on" not in (value or []):
            return False, no_update
        return True, "m9_auto" if exp_a != "m9_auto" else "m9_fructose"

    @app.callback(Output("context-label", "children"), Input("store-run", "data"),
                  prevent_initial_call=True)
    def show_context(run):
        if not run:
            return no_update
        exp = run["a"] + (f"  vs  {run['b']}" if run.get("b") else "")
        return f"{run['model']}  ·  {exp}"

    # ── Analysis jobs: start → poll → apply (or cancel) ──
    def _job_outputs():
        return [Output("store-job", "data", allow_duplicate=True),
                Output("job-poll", "disabled", allow_duplicate=True),
                Output("analyse-status", "children", allow_duplicate=True),
                Output("analyse-btn", "disabled", allow_duplicate=True),
                Output("job-cancel", "hidden", allow_duplicate=True)]

    def _start(*args):
        return jobs.submit(run_and_render, *args), False, ui.running("Starting…"), True, False

    @app.callback(
        *_job_outputs(),
        Input("analyse-btn", "n_clicks"),
        State("model-select", "value"), State("experiment-select", "value"),
        State("compare-toggle", "value"), State("experiment-b-select", "value"),
        prevent_initial_call=True)
    def on_analyse(_, model_path, exp_a, compare, exp_b):
        compare_on = bool("on" in (compare or []) and exp_b and exp_b != exp_a)
        return _start(model_path, exp_a, compare_on, exp_b)

    @app.callback(
        *_job_outputs(),
        Input("substrate-screen-dt", "selected_rows"),
        State("substrate-screen-dt", "data"), State("model-select", "value"),
        prevent_initial_call=True)
    def on_screen_select(selected, rows, model_path):
        row = rows[selected[0]] if selected and rows else {}
        ckey = row.get("_key")
        if not ckey or row.get("Feasible") == "no exchange":
            return (no_update,) * 5
        return _start(model_path, f"substrate:{ckey}", False, None)

    @app.callback(
        *analysis_outputs(),
        Output("store-job", "data", allow_duplicate=True),
        Output("job-poll", "disabled", allow_duplicate=True),
        Output("analyse-btn", "disabled", allow_duplicate=True),
        Output("job-cancel", "hidden", allow_duplicate=True),
        Input("job-poll", "n_intervals"), State("store-job", "data"),
        prevent_initial_call=True)
    def poll_job(_, job_id):
        finished = (None, True, False, True)
        if not job_id:
            return (*_UNCHANGED, no_update, True, no_update, no_update)
        job = jobs.get(job_id)
        if job is None:  # e.g. the server restarted mid-run
            return (*_UNCHANGED._replace(
                status=ui.status(False, "Analysis interrupted — please run it again.")),
                *finished)
        if not job.done:
            return (*_UNCHANGED._replace(status=ui.running(job.stage)),
                    no_update, no_update, no_update, no_update)
        view = job.result()
        jobs.forget(job_id)
        return (*view, *finished)

    @app.callback(*_job_outputs(), Input("job-cancel", "n_clicks"), State("store-job", "data"),
                  prevent_initial_call=True)
    def cancel_job(_, job_id):
        jobs.forget(job_id)
        return (None, True, ui.status(False, "Cancelled — previous results kept."),
                False, True)

    # ── Growth screen job ──
    @app.callback(Output("store-screen-job", "data"), Output("screen-poll", "disabled"),
                  Output("screen-table-wrap", "children"), Output("screen-btn", "disabled"),
                  Input("screen-btn", "n_clicks"), State("model-select", "value"),
                  prevent_initial_call=True)
    def on_screen(_, model_path):
        return jobs.submit(_screen_job, model_path), False, ui.running("Starting…"), True

    @app.callback(Output("screen-table-wrap", "children", allow_duplicate=True),
                  Output("store-screen-job", "data", allow_duplicate=True),
                  Output("screen-poll", "disabled", allow_duplicate=True),
                  Output("screen-btn", "disabled", allow_duplicate=True),
                  Input("screen-poll", "n_intervals"), State("store-screen-job", "data"),
                  prevent_initial_call=True)
    def poll_screen(_, job_id):
        job = jobs.get(job_id)
        if job is None:
            return no_update, None, True, False
        if not job.done:
            return ui.running(job.stage), no_update, no_update, no_update
        out = job.result()
        jobs.forget(job_id)
        return out, None, True, False


def _screen_job(model_path, progress=None):
    try:
        return ui.screen_table(analysis.get_substrate_screen(model_path, progress))
    except Exception as exc:  # UI boundary
        return dbc.Alert(f"Screen failed: {type(exc).__name__}: {exc}", color="danger")
