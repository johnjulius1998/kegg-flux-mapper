"""
KEGG Flux Mapper — active flux on KEGG pathway maps
===================================================
Linear workflow (see README.md):

  Step 1  Pick / upload a genome-scale model and an experiment setup (a documented
          uptake medium), then press "Analyse".  pFBA is solved once per configuration.
          (Step 1b) The growth screen ranks the biomass growth rate µ for a curated list
          of carbon sources (standard sugars/acids and polyethylene-derived alcohols and
          fatty acids), each tested as the sole carbon source on aerobic M9; clicking a
          row loads that substrate's full flux analysis.
  Step 2  Every model reaction is mapped to KEGG reaction R-numbers (directly via
          kegg.reaction annotations, or via EC numbers).  Reference KEGG pathways are
          scored by coverage.
  Step 3  Browse the ranked, searchable pathway list in the sidebar.
  Step 4  Click a pathway → the official KEGG map is shown with each reaction box
          colour-coded by flux (green = forward, orange = reverse, grey = ≈0), plus
          growth/yield panels, a per-reaction table, click-through reaction detail,
          optional FVA ranges, two-condition Δflux comparison, and CSV/PNG export.

Implementation lives in the kfm/ package; this file is just the entry point.
KEGG images are used unmodified as a static background layer (KEGG terms,
non-commercial); the flux overlay is a separate layer drawn on top.

Usage:
    python app.py                 # http://127.0.0.1:8050
    KFM_DEBUG=1 python app.py     # dev mode; other settings in kfm/config.py
    gunicorn app:server -w 1 --threads 8 -b 127.0.0.1:8050
                         # keep one worker: analysis results are cached in-process
"""

import logging
import warnings

import dash_bootstrap_components as dbc
from dash import Dash

from kfm.config import DEBUG, HOST, PORT
from kfm.ui import build_layout, register_callbacks

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO if DEBUG else logging.WARNING,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app() -> Dash:
    app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.BOOTSTRAP],
               title="KEGG Flux Mapper", update_title=None,
               suppress_callback_exceptions=True)
    app.layout = build_layout()
    register_callbacks(app)
    return app


app = create_app()
server = app.server  # for gunicorn / WSGI deployment

if __name__ == "__main__":
    app.run(debug=DEBUG, host=HOST, port=PORT)
