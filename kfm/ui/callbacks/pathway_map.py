"""Pathway list, map rendering, reaction inspector and CSV export."""

import pandas as pd
from dash import Input, Output, State, callback_context, dcc, no_update

from ... import analysis, figures, kegg
from .. import components as ui
from ..common import empty_list


def register(app):

    @app.callback(Output("pathway-list", "options"), Output("pathway-list", "value"),
                  Output("pathway-empty", "children"),
                  Input("store-pathways", "data"), Input("pathway-search", "value"),
                  State("pathway-list", "value"))
    def render_pathway_list(rows, query, current):
        rows = rows or []
        if not rows:
            return [], None, empty_list()
        q = (query or "").strip().lower()
        shown = [r for r in rows
                 if not q or q in r["Pathway"].lower() or q in r["KEGG ID"].lower()]
        options = [{"label": ui.pathway_row(r), "value": r["KEGG ID"]} for r in shown]
        value = no_update
        if callback_context.triggered_id == "store-pathways":
            ids = {r["KEGG ID"] for r in rows}
            value = current if current in ids else rows[0]["KEGG ID"]
        empty = None if shown else empty_list("No Results", f"Nothing matches “{query}”.")
        return options, value, empty

    @app.callback(
        Output("pathway-graph", "figure"), Output("pathway-table", "children"),
        Output("map-title", "children"), Output("map-subtitle", "children"),
        Output("throughput-bar", "children"), Output("map-legend", "children"),
        Output("store-pathway-csv", "data"), Output("reaction-detail", "children"),
        Input("pathway-list", "value"), Input("store-fva", "data"),
        Input("mode-seg", "value"), Input("store-key-a", "data"),
        State("store-key-b", "data"), State("store-run", "data"),
        prevent_initial_call=True)
    def on_pathway_select(map_id, fva_on, mode, key_a, key_b, run):
        res_a = analysis.get_by_key(key_a)
        if not map_id or res_a is None:
            return (no_update,) * 8
        name = kegg.pathway_names().get(map_id, map_id)
        run = run or {}

        res_b = analysis.get_by_key(key_b) if mode == "compare" else None
        if res_b is not None:
            fig, df = figures.build_delta_figure(map_id, res_a, res_b)
            return (fig, ui.flux_table(df), name, f"{map_id}  ·  Δ flux, A − B",
                    ui.delta_stats(df), ui.legend(df, "Δ (A−B)", (run.get("a"), run.get("b"))),
                    df.to_dict("records"), None)

        fva = analysis.fva_for_pathway(key_a, map_id) if fva_on else None
        fig, df, summary = figures.build_pathway_figure(map_id, res_a, fva=fva)
        sub = map_id
        if summary:
            sub += f"  ·  {summary['active']} of {summary['mapped']} reactions active"
        return (fig, ui.flux_table(df), name, sub, ui.flux_stats(summary),
                ui.legend(df, "Flux", fva=bool(fva)), df.to_dict("records"), None)

    @app.callback(Output("reaction-detail", "children", allow_duplicate=True),
                  Input("pathway-graph", "clickData"),
                  State("store-key-a", "data"), State("store-key-b", "data"),
                  State("mode-seg", "value"), State("store-run", "data"),
                  prevent_initial_call=True)
    def on_reaction_click(click, key_a, key_b, mode, run):
        if not click:
            return no_update
        res = analysis.get_by_key(key_a)
        pts = click.get("points", [])
        rid = pts[0].get("customdata") if pts else None
        if res is None or not rid or rid not in res.model.reactions:
            return no_update
        res_b = analysis.get_by_key(key_b) if mode == "compare" else None
        return ui.inspector(res, rid, res_b, run)

    @app.callback(Output("download-csv", "data"),
                  Input("csv-btn", "n_clicks"), Input("csv-menu", "n_clicks"),
                  State("store-pathway-csv", "data"), prevent_initial_call=True)
    def download_csv(_, __, data):
        if not data:
            return no_update
        return dcc.send_data_frame(pd.DataFrame(data).to_csv,
                                   "kegg_pathway_fluxes.csv", index=False)
