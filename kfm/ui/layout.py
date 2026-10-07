"""Page structure: toolbar, sidebar, map canvas, modals and sheets."""

import dash_bootstrap_components as dbc
from dash import dcc, html

from .. import figures
from ..config import SCREEN_UPTAKE
from .common import (EXP_OPTIONS, GRAPH_CONFIG, MODEL_OPTIONS, check_label, empty_list,
                     group, icon)


def build_layout():
    return html.Div([
        _toolbar(),
        html.Div([_sidebar(), _canvas()], id="app-shell", className="app-shell"),

        _config_modal(),
        _screen_modal(),
        _summary_modal(),
        dbc.Offcanvas(html.Div(id="reaction-detail"), id="reaction-offcanvas",
                      title="Inspector", placement="end", backdrop=False,
                      scrollable=True, is_open=False, className="inspector"),
        _table_sheet(),

        dcc.Store(id="store-key-a"),
        dcc.Store(id="store-key-b"),
        dcc.Store(id="store-run"),
        dcc.Store(id="store-fva", data=False),
        dcc.Store(id="store-pathway-csv"),
        dcc.Store(id="store-job"),
        dcc.Store(id="store-screen-job"),
        dcc.Interval(id="job-poll", interval=500, disabled=True),
        dcc.Interval(id="screen-poll", interval=500, disabled=True),
        dcc.Download(id="download-csv"),
        html.Div(id="theme-dummy", hidden=True),
    ], className="app")


def _toolbar():
    menu = dbc.DropdownMenu([
        dbc.DropdownMenuItem("Growth Screen…", id="open-screen"),
        dbc.DropdownMenuItem("Balance Summary…", id="open-summary"),
        dbc.DropdownMenuItem(divider=True),
        dbc.DropdownMenuItem(check_label("FVA Flux Ranges", False), id="fva-item"),
        dbc.DropdownMenuItem("Export Flux Table (CSV)", id="csv-menu"),
        dbc.DropdownMenuItem(divider=True),
        dbc.DropdownMenuItem("Toggle Light / Dark", id="theme-toggle"),
    ], label=icon("three-dots"), caret=False, align_end=True, color="link",
        toggleClassName="tb-icon", className="tb-menu")

    return html.Header([
        html.Div([
            html.Button(icon("layout-sidebar"), id="sidebar-toggle", className="tb-icon",
                        title="Show / hide sidebar"),
            html.Div([
                html.Div("KEGG Flux Mapper", id="map-title", className="tb-title"),
                html.Div("No pathway selected", id="map-subtitle", className="tb-subtitle"),
            ], className="tb-titles"),
        ], className="tb-left"),

        html.Button([html.Span("Choose model & experiment", id="context-label"),
                     icon("chevron-down", "tb-chev")],
                    id="open-config", className="tb-context",
                    title="Change model or experiment"),

        html.Div([
            dbc.RadioItems(id="mode-seg", className="segmented", inputClassName="btn-check",
                           labelClassName="seg-btn", labelCheckedClassName="active",
                           options=[{"label": "Flux", "value": "single"},
                                    {"label": "Δ Compare", "value": "compare"}],
                           value="single"),
            html.Button(icon("table"), id="open-table", className="tb-icon",
                        title="Flux table"),
            menu,
        ], className="tb-right"),
    ], className="toolbar")


def _sidebar():
    return html.Aside([
        html.Div([icon("search", "search-icon"),
                  dbc.Input(id="pathway-search", type="search", placeholder="Search",
                            debounce=False, className="search-field", autoComplete="off")],
                 className="sb-search"),
        html.Div("Pathways", className="sb-section"),
        dcc.Loading(html.Div([
            dbc.RadioItems(id="pathway-list", options=[], value=None, className="pw-list",
                           labelClassName="pw-row", labelCheckedClassName="active"),
            html.Div(id="pathway-empty", children=empty_list()),
            dcc.Store(id="store-pathways"),
        ]), target_components={"store-pathways": "data"}, type="circle",
            color="var(--accent)", parent_className="sb-scroll", delay_show=150),
        html.Div([html.Div(id="analyse-status", className="sb-status"),
                  html.Button("Cancel", id="job-cancel", className="sb-cancel", hidden=True)],
                 className="sb-footer"),
    ], className="sidebar")


def _canvas():
    return html.Main([
        dcc.Loading(
            dcc.Graph(id="pathway-graph", config=GRAPH_CONFIG, responsive=True,
                      className="map-graph",
                      figure=figures.empty_figure(
                          "<b>No Pathway Selected</b><br>"
                          "<span style='font-size:13px'>Run an analysis, then choose a "
                          "pathway from the sidebar.</span>")),
            target_components={"pathway-graph": "figure"}, type="circle",
            color="var(--accent)", parent_className="map-loading", delay_show=200,
            overlay_style={"visibility": "visible", "opacity": 0.55}),
        html.Div(id="throughput-bar", className="float-card stats-card"),
        html.Div(id="map-legend", className="float-card legend-card"),
    ], className="canvas")


def _table_sheet():
    title = html.Div([html.Span("Flux Table"),
                      dbc.Button([icon("download", "me-1"), "Export CSV"], id="csv-btn",
                                 size="sm", className="btn-soft")], className="sheet-title")
    return dbc.Offcanvas(
        html.Div(id="pathway-table",
                 children=html.Div("Select a pathway to see its reactions.",
                                   className="muted small")),
        id="table-sheet", title=title, placement="bottom", backdrop=False,
        scrollable=True, is_open=False, className="sheet")


def _config_modal():
    return dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("New Analysis")),
        dbc.ModalBody([
            group("1 · Model", [
                dcc.Dropdown(id="model-select", options=MODEL_OPTIONS,
                             value=MODEL_OPTIONS[0]["value"] if MODEL_OPTIONS else None,
                             placeholder="No models in models/ — upload one below",
                             clearable=False),
                dcc.Upload(id="model-upload", className="drop-zone",
                           children=html.Div([icon("upload", "me-1"),
                                              "Drop or choose your own model — "
                                              "SBML, JSON or .mat"])),
                html.Div(id="upload-error", className="grp-error"),
            ]),
            group("2 · Experiment", [
                dcc.Dropdown(id="experiment-select", options=EXP_OPTIONS,
                             value="m9_fructose", clearable=False),
                html.Div(id="experiment-desc", className="grp-note"),
            ]),
            group("3 · Compare (optional)", [
                dbc.Checklist(id="compare-toggle", switch=True, className="mb-0",
                              options=[{"label": "Compare with a second experiment",
                                        "value": "on"}], value=[]),
                dbc.Collapse(dcc.Dropdown(id="experiment-b-select", options=EXP_OPTIONS,
                                          value="m9_auto", clearable=False,
                                          placeholder="Experiment B…", className="mt-2"),
                             id="experiment-b-wrap", is_open=False),
            ]),
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="config-cancel", className="btn-soft"),
            dbc.Button("Analyse", id="analyse-btn", color="primary", className="px-4"),
        ]),
    ], id="config-modal", is_open=True, size="lg", centered=True, className="sheet-modal")


def _screen_modal():
    return dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Growth Screen")),
        dbc.ModalBody([
            html.P("Each substrate is screened as the sole carbon source on aerobic M9 "
                   f"(uptake {abs(SCREEN_UPTAKE):g} mmol/gDW/h); µ is the biomass flux. Choose "
                   "a row to open its full flux analysis.", className="muted small"),
            dbc.Button("Run Screen", id="screen-btn", color="primary", size="sm"),
            html.Div(id="screen-table-wrap", className="mt-3"),
        ]),
    ], id="screen-modal", is_open=False, size="xl", scrollable=True, className="sheet-modal")


def _summary_modal():
    return dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Balance Summary")),
        dbc.ModalBody(html.Div(id="info-panels",
                               children=html.Div("No analysis yet.", className="muted small"))),
    ], id="summary-modal", is_open=False, size="lg", className="sheet-modal")
