"""Shared UI constants and small building blocks."""

from pathlib import Path

from dash import html

from ..config import discover_models
from ..experiments import EXPERIMENTS

MODEL_OPTIONS = [{"label": k, "value": v} for k, v in discover_models().items()]
_MODEL_LABELS = {o["value"]: o["label"] for o in MODEL_OPTIONS}
EXP_OPTIONS = [{"label": e.label, "value": e.key} for e in EXPERIMENTS.values()]

GRAPH_CONFIG = {"displaylogo": False, "scrollZoom": True, "doubleClick": "reset",
                "modeBarButtonsToRemove": ["zoom2d", "pan2d", "select2d", "lasso2d",
                                           "autoScale2d"],
                "toImageButtonOptions": {"format": "png", "filename": "kegg_flux_map",
                                         "scale": 2}}
TABLE_STYLE = dict(
    style_table={"overflowX": "auto"},
    style_cell={"fontSize": "12px", "padding": "6px 8px", "textAlign": "left",
                "fontFamily": "var(--font)", "border": "none",
                "borderBottom": "1px solid var(--separator)"},
    style_header={"fontWeight": 600, "backgroundColor": "var(--surface-2)",
                  "color": "var(--label)"},
    style_data={"backgroundColor": "transparent", "color": "var(--label)"},
)
POS, NEG = "#1f9d63", "#e0561c"


def model_label(path):
    return _MODEL_LABELS.get(path) or Path(path or "").name


def icon(name, cls=""):
    return html.I(className=f"bi bi-{name} {cls}".strip())


def group(title, children):
    return html.Div([html.Div(title, className="grp-title"),
                     html.Div(children, className="grp-box")], className="grp")


def check_label(text, on):
    return [html.Span("✓" if on else "", className="menu-check"), text]


def empty_list(title="No Analysis",
               text="Choose a model and experiment to list the matching pathways."):
    return html.Div([html.B(title), html.Span(text)], className="sb-empty")


def kv(k, v):
    return html.Div([html.Span(k, className="muted"), html.Span(v, className="kv-v")],
                    className="kv")
