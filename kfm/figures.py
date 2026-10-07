"""
Plotly figures: the KEGG pathway flux overlay and the two-condition Δflux overlay.

The official KEGG PNG is drawn as a non-interactive background image in data
coordinates that match the KGML box coordinates; coloured rectangles + a hover/colour
marker trace are layered on top.  Nothing in the source image is modified.

Pipeline: `compute_overlays` (pure: which reaction/value each enzyme box shows) →
`_render` (Plotly) + the table/summary builders.
"""

import base64
from dataclasses import dataclass

import pandas as pd
import plotly.graph_objects as go

from . import kegg
from .config import FLUX_EPS

_FONT = "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
_DIVERGING = [[0.0, "rgb(232,96,38)"], [0.5, "rgb(225,225,225)"], [1.0, "rgb(34,170,110)"]]


def _flux_color(f: float, fmax: float, fill: bool) -> str:
    """Green = forward, orange = reverse, grey = ≈0. Alpha scales with |flux|/fmax."""
    if abs(f) < FLUX_EPS:
        return "rgba(150,150,150,0.30)" if fill else "rgba(140,140,140,0.55)"
    a = min(0.35 + 0.55 * (abs(f) / fmax if fmax else 0), 0.9) if fill else 0.9
    return f"rgba(34,170,110,{a:.2f})" if f > 0 else f"rgba(232,96,38,{a:.2f})"


def empty_figure(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, showarrow=False, font=dict(size=17, color="#8e8e93"))
    fig.update_layout(autosize=True, paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", font_family=_FONT,
                      xaxis_visible=False, yaxis_visible=False,
                      margin=dict(l=0, r=0, t=0, b=0))
    return fig


# ── Overlay computation (pure) ────────────────────────────────────────────────────

@dataclass(frozen=True)
class BoxOverlay:
    box: kegg.ReactionBox
    rxn_id: str
    value: float                # what the box is coloured by: flux, or Δ = fa − fb
    fa: float
    fb: float | None = None
    variable: bool = False      # FVA range wider than 1e-4


def _box_flux(box, fluxes: dict, R_to_rxn: dict) -> tuple[str | None, float]:
    """Pick the mapped reaction with the largest |flux| for a KGML box.

    Ties go to the alphabetically first reaction id, so the choice doesn't depend on
    set iteration order (which varies with PYTHONHASHSEED between processes).
    """
    candidates = sorted({rid for r in box.reactions for rid in R_to_rxn.get(r, ())})
    best_rxn, best_flux = None, 0.0
    for rid in candidates:
        f = fluxes.get(rid, 0.0)
        if best_rxn is None or abs(f) > abs(best_flux):
            best_flux, best_rxn = f, rid
    return best_rxn, best_flux


def compute_overlays(pmap, result_a, result_b=None, fva: dict | None = None) -> list[BoxOverlay]:
    """One overlay per enzyme box that maps to a model reaction (boxes chosen by A)."""
    out = []
    for box in pmap.boxes:
        rxn_id, fa = _box_flux(box, result_a.fluxes, result_a.R_to_rxn)
        if rxn_id is None:
            continue
        if result_b is not None:
            fb = result_b.fluxes.get(rxn_id, 0.0)
            out.append(BoxOverlay(box, rxn_id, fa - fb, fa, fb))
        else:
            variable = bool(fva) and rxn_id in fva and (fva[rxn_id][1] - fva[rxn_id][0]) > 1e-4
            out.append(BoxOverlay(box, rxn_id, fa, fa, variable=variable))
    return out


# ── Public builders ───────────────────────────────────────────────────────────────

def build_pathway_figure(map_id, result, fva: dict | None = None):
    """
    Returns (figure, table_df, summary_dict).  `result` is an AnalysisResult;
    `fva` is an optional {reaction_id: (min, max)} to annotate variable fluxes.
    """
    pmap = kegg.pathway_map(map_id)
    if not pmap.available:
        return (empty_figure("No coordinate map (KGML/image) available for this pathway."),
                pd.DataFrame(), {})

    overlays = compute_overlays(pmap, result, fva=fva)

    def hover(o):
        direction = "forward" if o.fa > FLUX_EPS else "reverse" if o.fa < -FLUX_EPS else "≈0"
        extra = f"<br>FVA: [{fva[o.rxn_id][0]:+.3f}, {fva[o.rxn_id][1]:+.3f}]" \
            if fva and o.rxn_id in fva else ""
        return (f"<b>{o.rxn_id}</b><br>{o.box.label}<br>"
                f"Flux: <b>{o.fa:+.5f}</b> ({direction})<br>"
                f"R: {', '.join(sorted(o.box.reactions))}{extra}<br><i>click for detail</i>")

    fig = _render(pmap, overlays, hover)
    return fig, _flux_table(overlays, result, fva), _summary(overlays)


def build_delta_figure(map_id, result_a, result_b):
    """Δflux (A − B) on the KEGG map for the reactions shared by both conditions."""
    pmap = kegg.pathway_map(map_id)
    if not pmap.available:
        return empty_figure("No coordinate map available for this pathway."), pd.DataFrame()

    overlays = compute_overlays(pmap, result_a, result_b)

    def hover(o):
        return (f"<b>{o.rxn_id}</b><br>{o.box.label}<br>"
                f"A: {o.fa:+.4f} · B: {o.fb:+.4f}<br><b>Δ: {o.value:+.4f}</b>")

    return _render(pmap, overlays, hover), _delta_table(overlays, result_a)


# ── Tables + summary ──────────────────────────────────────────────────────────────

def _flux_table(overlays, result, fva) -> pd.DataFrame:
    rows = {}
    for o in overlays:
        rxn = result.model.reactions.get_by_id(o.rxn_id)
        row = {"Reaction": o.rxn_id, "Name": (rxn.name or "")[:48],
               "Flux": round(o.fa, 5), "LB": round(rxn.lower_bound, 3),
               "UB": round(rxn.upper_bound, 3),
               "R-number": ", ".join(sorted(o.box.reactions & result.R_to_rxn.keys())[:3])}
        if fva is not None and o.rxn_id in fva:
            row["FVA min"], row["FVA max"] = fva[o.rxn_id]
        rows[o.rxn_id] = row
    return _sorted_by_abs(pd.DataFrame(list(rows.values())), "Flux")


def _delta_table(overlays, result_a) -> pd.DataFrame:
    rows = {o.rxn_id: {"Reaction": o.rxn_id,
                       "Name": (result_a.model.reactions.get_by_id(o.rxn_id).name or "")[:40],
                       "Flux A": round(o.fa, 5), "Flux B": round(o.fb, 5),
                       "Δ (A−B)": round(o.value, 5)}
            for o in overlays}
    return _sorted_by_abs(pd.DataFrame(list(rows.values())), "Δ (A−B)")


def _sorted_by_abs(df: pd.DataFrame, col: str) -> pd.DataFrame:
    if df.empty:
        return df
    return df.reindex(df[col].abs().sort_values(ascending=False).index).reset_index(drop=True)


def _summary(overlays) -> dict:
    mapped = len(overlays)
    active = sum(1 for o in overlays if abs(o.fa) >= FLUX_EPS)
    return {"mapped": mapped, "active": active,
            "total_flux": round(sum(abs(o.fa) for o in overlays), 4),
            "net_flux": round(sum(o.fa for o in overlays), 4),
            "pct_active": round(100 * active / mapped, 1) if mapped else 0}


# ── Rendering ─────────────────────────────────────────────────────────────────────

def _render(pmap, overlays, hover) -> go.Figure:
    vmax = max([FLUX_EPS] + [abs(o.value) for o in overlays])
    fig = go.Figure()
    fig.add_layout_image(dict(
        source="data:image/png;base64," + base64.b64encode(pmap.png).decode(),
        xref="x", yref="y", x=0, y=0, sizex=pmap.width, sizey=pmap.height,
        sizing="stretch", layer="below", yanchor="top"))
    for o in overlays:
        b = o.box
        fig.add_shape(type="rect", x0=b.x - b.w / 2, y0=b.y - b.h / 2,
                      x1=b.x + b.w / 2, y1=b.y + b.h / 2,
                      line=dict(color=_flux_color(o.value, vmax, False),
                                width=1.6 if o.variable else 1.4,
                                dash="dot" if o.variable else "solid"),
                      fillcolor=_flux_color(o.value, vmax, True), layer="above")
    fig.add_trace(go.Scatter(
        x=[o.box.x for o in overlays], y=[o.box.y for o in overlays], mode="markers",
        customdata=[o.rxn_id for o in overlays],
        marker=dict(size=11, color=[o.value for o in overlays], colorscale=_DIVERGING,
                    cmin=-vmax, cmax=vmax, line=dict(width=1, color="white"),
                    showscale=False),
        hovertext=[hover(o) for o in overlays], hoverinfo="text", showlegend=False))
    fig.update_layout(
        autosize=True, dragmode="pan", hovermode="closest", font_family=_FONT,
        xaxis=dict(range=[0, pmap.width], visible=False, constrain="domain"),
        yaxis=dict(range=[pmap.height, 0], visible=False, scaleanchor="x", scaleratio=1,
                   constrain="domain"),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="white",
        hoverlabel=dict(bgcolor="white", bordercolor="#d1d1d6",
                        font=dict(family=_FONT, size=12, color="#1d1d1f")),
        modebar=dict(orientation="v", bgcolor="rgba(0,0,0,0)",
                     color="#8e8e93", activecolor="#007aff"),
        margin=dict(l=0, r=0, t=0, b=0))
    return fig
