"""Pure render helpers: domain objects in, Dash components out."""

from dash import dash_table, html

from ..config import FLUX_EPS, KEGG_WEB
from .common import NEG, POS, TABLE_STYLE, group, kv


# ── Status + summary ──────────────────────────────────────────────────────────────

def status(ok, text, title=None):
    return html.Div([html.Span(className=f"dot {'ok' if ok else 'err'}"), text], title=title)


def running(stage):
    return html.Div([html.Span(className="spinner-border me-2", role="status"), stage],
                    className="running")


def _tile(title, value, sub=""):
    return html.Div([html.Div(title, className="tile-k"), html.Div(value, className="tile-v"),
                     html.Div(sub, className="tile-s")], className="tile")


def info_panels(result):
    b = result.balance
    def fmt(v): return "—" if v is None else f"{v:.4g}"
    tiles = html.Div([
        _tile("Objective", f"{b.objective_value:.5g}", b.objective),
        _tile("C uptake", fmt(b.c_uptake), "mmol C/gDW/h"),
        _tile("CO₂ out", fmt(b.co2_out), "mmol/gDW/h"),
        _tile("Carbon efficiency", fmt(b.carbon_efficiency), "C retained / C in"),
        _tile("Respiratory quotient", fmt(b.respiratory_quotient), "CO₂ / O₂"),
        _tile("C : N", fmt(b.c_to_n), "uptake ratio"),
    ], className="tile-grid")

    def ex_list(role, color):
        items = [e for e in result.exchanges if e.role == role][:6]
        return [html.Div([html.Span(e.metabolite),
                          html.Span(f"{e.flux:+.4g}", style={"color": color}, className="num")],
                         className="kv")
                for e in items] or html.Div("—", className="muted")

    return html.Div([
        tiles,
        html.Div([group("Top uptakes", ex_list("uptake", NEG)),
                  group("Top secretions", ex_list("secretion", POS))],
                 className="two-col"),
    ])


# ── Map overlays: stats card + legend ─────────────────────────────────────────────

def _stat(k, v):
    return html.Div([html.Div(v, className="stat-v"), html.Div(k, className="stat-k")],
                    className="stat")


def flux_stats(summary):
    if not summary:
        return None
    return [_stat("Active", f"{summary['active']} / {summary['mapped']}"),
            _stat("Σ |flux|", f"{summary['total_flux']:.3g}"),
            _stat("Net", f"{summary['net_flux']:+.3g}"),
            html.Div("mmol/gDW/h", className="stat-unit")]


def delta_stats(df):
    if df is None or df.empty:
        return None
    d = df["Δ (A−B)"]
    return [_stat("Mapped", str(len(df))),
            _stat("Higher in A", str(int((d > FLUX_EPS).sum()))),
            _stat("Higher in B", str(int((d < -FLUX_EPS).sum())))]


def legend(df, col, labels=None, fva=False):
    if df is None or df.empty:
        return None
    m = float(df[col].abs().max()) or FLUX_EPS
    neg, pos = ("Higher in B", "Higher in A") if labels else ("Reverse", "Forward")
    out = [html.Div("Δ Flux  A − B" if labels else "Flux  mmol/gDW/h", className="lg-title"),
           html.Div(className="lg-bar"),
           html.Div([html.Span(f"−{m:.3g}"), html.Span("0"), html.Span(f"+{m:.3g}")],
                    className="lg-ticks"),
           html.Div([html.Span(neg), html.Span(pos)], className="lg-caps")]
    if labels:
        out += [html.Div([html.B("A "), labels[0]], className="lg-note"),
                html.Div([html.B("B "), labels[1]], className="lg-note")]
    if fva:
        out.append(html.Div([html.Span(className="lg-dash"), "Variable under FVA"],
                            className="lg-note"))
    return out


# ── Inspector ─────────────────────────────────────────────────────────────────────

def _direction_chip(f):
    if f > FLUX_EPS:
        return html.Span("Forward", className="chip fwd")
    if f < -FLUX_EPS:
        return html.Span("Reverse", className="chip rev")
    return html.Span("Inactive", className="chip zero")


def inspector(result, rid, result_b=None, run=None):
    rxn = result.model.reactions.get_by_id(rid)
    fa = result.fluxes.get(rid, 0)
    if result_b is not None:
        fb = result_b.fluxes.get(rid, 0)
        run = run or {}
        flux = [kv(f"A · {run.get('a', '')}", f"{fa:+.5f}"),
                kv(f"B · {run.get('b', '')}", f"{fb:+.5f}"),
                kv("Δ  A − B", html.B(f"{fa - fb:+.5f}"))]
    else:
        flux = [html.Div([html.Span(f"{fa:+.5f}", className="insp-flux"),
                          _direction_chip(fa)], className="insp-flux-row"),
                html.Div("mmol/gDW/h", className="muted small")]

    ec = rxn.annotation.get("ec-code")
    links = [html.A(r, href=f"{KEGG_WEB}/entry/{r}", target="_blank", className="link-pill")
             for r in sorted(result.rxn_to_R.get(rid, []))[:6]]
    return html.Div([
        html.Div([html.Div(rid, className="insp-id"),
                  html.Div(rxn.name or rid, className="insp-name")], className="insp-head"),
        group("Flux", flux),
        group("Equation", html.Div(rxn.build_reaction_string(use_metabolite_names=True),
                                   className="insp-eq")),
        group("Annotation", [
            kv("EC", str(ec or "—")),
            kv("Subsystem", rxn.subsystem or "—"),
            kv("Bounds", f"[{rxn.lower_bound:g}, {rxn.upper_bound:g}]"),
        ]),
        group("Genes", html.Div(rxn.gene_reaction_rule or "—", className="insp-genes")),
        group("KEGG", html.Div(links, className="link-row") if links else "—"),
    ])


# ── Lists + tables ────────────────────────────────────────────────────────────────

def pathway_row(r):
    cov = r["Coverage %"]
    return html.Div([
        html.Div([html.Span(r["Pathway"], className="pw-name"),
                  html.Span(f"{cov:.0f}%", className="pw-pct")], className="pw-top"),
        html.Div(html.Div(style={"width": f"{min(cov, 100)}%"}), className="pw-bar"),
        html.Div(f"{r['KEGG ID']}  ·  {r['Rxns mapped']} of {r['Pathway rxns']} reactions",
                 className="pw-meta"),
    ])


def screen_table(df):
    cols = [("Substrate", "Substrate"), ("Class", "Class"), ("Exchange", "Exchange"),
            ("µ (h⁻¹)", "mu"), ("Yield /C", "yield_c"), ("Feasible", "Feasible")]
    return dash_table.DataTable(
        id="substrate-screen-dt",
        columns=[{"name": n, "id": i} for n, i in cols],
        data=df.to_dict("records"), sort_action="native", page_action="none",
        row_selectable="single", **TABLE_STYLE,
        style_data_conditional=[
            {"if": {"filter_query": "{mu} > 0", "column_id": "mu"},
             "backgroundColor": "rgba(52,199,89,0.14)", "fontWeight": 600},
            {"if": {"filter_query": "{Feasible} = no", "column_id": "Feasible"},
             "color": NEG},
            {"if": {"filter_query": '{Feasible} = "no exchange"', "column_id": "Feasible"},
             "color": "var(--label-2)"}])


def flux_table(df):
    if df is None or df.empty:
        return html.Div("No mapped reactions in this pathway.", className="muted small")
    flux_col = "Δ (A−B)" if "Δ (A−B)" in df.columns else "Flux"
    return dash_table.DataTable(
        columns=[{"name": c, "id": c} for c in df.columns],
        data=df.to_dict("records"), sort_action="native", page_action="none",
        **TABLE_STYLE,
        style_data_conditional=[
            {"if": {"filter_query": f"{{{flux_col}}} > 0", "column_id": flux_col},
             "color": POS, "fontWeight": 600},
            {"if": {"filter_query": f"{{{flux_col}}} < 0", "column_id": flux_col},
             "color": NEG, "fontWeight": 600}])
