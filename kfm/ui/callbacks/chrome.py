"""Window chrome: wizard/modals open-close, sidebar, sheets, FVA and theme toggles."""

from dash import Input, Output, State, callback_context, no_update

from ..common import check_label


def register(app):

    @app.callback(Output("config-modal", "is_open"),
                  Input("open-config", "n_clicks"), Input("analyse-btn", "n_clicks"),
                  Input("config-cancel", "n_clicks"), prevent_initial_call=True)
    def toggle_config(*_):
        return callback_context.triggered_id == "open-config"

    @app.callback(Output("mode-seg", "value", allow_duplicate=True),
                  Output("config-modal", "is_open", allow_duplicate=True),
                  Output("compare-toggle", "value"),
                  Input("mode-seg", "value"), State("store-key-b", "data"),
                  prevent_initial_call=True)
    def on_mode(mode, key_b):
        # Compare needs a second experiment: send the user to the wizard to pick one.
        if mode == "compare" and not key_b:
            return "single", True, ["on"]
        return no_update, no_update, no_update

    @app.callback(Output("screen-modal", "is_open"), Input("open-screen", "n_clicks"),
                  prevent_initial_call=True)
    def open_screen(_):
        return True

    @app.callback(Output("screen-modal", "is_open", allow_duplicate=True),
                  Input("substrate-screen-dt", "selected_rows"), prevent_initial_call=True)
    def close_screen_on_pick(selected):
        return False if selected else no_update

    @app.callback(Output("summary-modal", "is_open"), Input("open-summary", "n_clicks"),
                  prevent_initial_call=True)
    def open_summary(_):
        return True

    @app.callback(Output("app-shell", "className"), Input("sidebar-toggle", "n_clicks"),
                  prevent_initial_call=True)
    def toggle_sidebar(n):
        return "app-shell collapsed" if n % 2 else "app-shell"

    @app.callback(Output("table-sheet", "is_open"), Input("open-table", "n_clicks"),
                  State("table-sheet", "is_open"), prevent_initial_call=True)
    def toggle_table(_, is_open):
        return not is_open

    @app.callback(Output("reaction-offcanvas", "is_open"), Input("reaction-detail", "children"))
    def toggle_inspector(children):
        return bool(children)

    @app.callback(Output("store-fva", "data"), Output("fva-item", "children"),
                  Input("fva-item", "n_clicks"), State("store-fva", "data"),
                  prevent_initial_call=True)
    def toggle_fva(_, on):
        return not on, check_label("FVA Flux Ranges", not on)

    app.clientside_callback(
        "function(n){ if(n){ window.kfmToggleTheme(); } return window.dash_clientside.no_update; }",
        Output("theme-dummy", "children"), Input("theme-toggle", "n_clicks"),
        prevent_initial_call=True)
