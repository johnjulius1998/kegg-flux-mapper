# KEGG Flux Mapper

An interactive web app that solves a genome-scale metabolic model with parsimonious FBA
(pFBA) and paints the resulting reaction fluxes onto the official KEGG pathway maps.

Pick a model and a growth medium, press **Analyse**, then browse the KEGG pathways your
model covers. Each enzyme box on the map is coloured by the flux it carries. Green is
forward, orange is reverse and grey is inactive.

Built with [Dash](https://dash.plotly.com), [COBRApy](https://opencobra.github.io/cobrapy/)
and the [KEGG REST API](https://www.kegg.jp/kegg/rest/keggapi.html).

## Features

- **Pathway coverage ranking.** Every model reaction is mapped to KEGG reaction numbers
  through `kegg.reaction` annotations or EC numbers. KEGG reference pathways are then
  ranked by how much of each pathway the model contains.
- **Flux on the KEGG map.** Fluxes are drawn over the original KEGG image. You can zoom
  and pan, hover over a box for its values, and click a box to inspect the reaction:
  flux, equation, EC number, genes and KEGG links.
- **Δ Compare.** Solve two growth conditions and show the flux difference (A − B) on
  the same map.
- **FVA ranges.** Optional flux variability analysis for the reactions of the selected
  pathway. Reactions whose flux can vary are drawn with dashed boxes.
- **Growth screen.** Rank growth rate µ for a list of carbon sources, each tested as the
  sole carbon source on aerobic M9. The list covers standard sugars and acids plus
  polyethylene-derived alcohols and fatty acids. Click a row to open its full analysis.
- **Balance summary.** Carbon uptake, CO₂ output, carbon efficiency, respiratory quotient,
  C:N ratio, and the largest uptakes and secretions.
- **Export.** Download the flux table as CSV or the map as a PNG.
- Long solves run in the background with live progress and can be cancelled. The
  interface has a light and a dark theme.

## Quick start

Requires Python ≥ 3.10.

```bash
git clone <this-repo-url> kegg-flux-mapper
cd kegg-flux-mapper
python -m venv .venv && source .venv/bin/activate     # or use a conda env
pip install -e ".[dev]"
```

Put one or more SBML models into `models/`. Any `*.xml` file there, including in
sub-folders, shows up in the app. For example, `e_coli_core.xml` from
[BiGG Models](http://bigg.ucsd.edu) works. See [models/README.md](models/README.md).

```bash
python app.py                  # http://127.0.0.1:8050
KFM_DEBUG=1 python app.py      # development mode with auto-reload
```

You can also upload an SBML, JSON or MATLAB `.mat` model from the app.

The first time you open a pathway, its map and coordinates are downloaded from KEGG
and cached in `kegg_cache/`, so an internet connection is needed for pathways you
haven't opened before.

## Using the app

1. **New Analysis.** The setup wizard opens automatically. You can reopen it later from
   the model · experiment pill in the toolbar.
   1. Choose a model, or upload one.
   2. Choose a growth medium (see the presets below).
   3. Optionally turn on *Compare* and choose a second medium.
2. **Pathways.** The sidebar lists every KEGG pathway the model touches, ranked by
   coverage. Use the search field to filter by name or map ID.
3. **Map.**
   - Drag to pan, scroll or pinch to zoom, double-click to reset.
   - The floating cards show the active-reaction count, Σ|flux|, net flux and the colour
     legend.
   - Click a reaction box to open the **Inspector**.
4. **Toolbar.**
   - *Flux | Δ Compare* switches between single-condition and difference views.
   - The table button opens the per-reaction flux table.
   - The **⋯** menu holds the Growth Screen, Balance Summary, FVA ranges, CSV export and
     the light/dark toggle.

### Experiment presets

Constructed media close every recognised carbon uptake, open the M9 minerals, then open
the listed carbon source(s). Bounds are in mmol/gDW/h. Presets are defined in
[`kfm/experiments.py`](kfm/experiments.py).

| Preset | Carbon source(s) | O₂ | NH₄ |
|---|---|---|---|
| Model default (trust XML) | the model's own bounds | — | — |
| M9 — Fructose | fructose 2.6 | open | open |
| M9 — Succinate | succinate 3.5 | open | open |
| M9 — Gluconate | gluconate 3.5 | open | open |
| M9 — Formate | formate 10 + CO₂ 15 | open | open |
| M9 — CO₂ + H₂ (autotrophic) | CO₂ 15 + H₂ 30 | 10 | open |
| N-limited PHB | fructose 2.6 | open | 0.1 |
| M9 — Palmitate | palmitate 2.0 | open | open |

Exchange reactions are matched to compounds by KEGG C-numbers, ModelSEED `cpd` ids, or
a `cpd` id embedded in the metabolite id. This works for BiGG-, KEGG- and
ModelSEED/gapseq-style models without editing them. If a constructed medium is
infeasible for a model, the app falls back to the model's own bounds and says so.

## Configuration

All settings are optional environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `KFM_HOST` | `127.0.0.1` | Interface to bind |
| `KFM_PORT` | `8050` | Port |
| `KFM_DEBUG` | off | `1`/`true`/`yes`/`on` enables Dash debug mode and auto-reload |
| `KFM_CACHE_SIZE` | `8` | Number of solved analyses kept in memory |
| `KFM_KEGG_CACHE` | `./kegg_cache` | Where downloaded KEGG files (and uploads) are stored |

### Deployment

Analysis results, including the solved COBRA models, are cached in memory in one
process. Run a single worker with several threads:

```bash
gunicorn app:server -w 1 --threads 8 -b 127.0.0.1:8050
```

Uploaded files are restricted to model formats and 50 MB, and only files under
`models/` or the upload folder can be loaded. The app has no authentication, so put it
behind one if you expose it beyond your machine.

## Project layout

```
app.py                  entry point (create_app, WSGI `server`)
kfm/
  config.py             paths, env settings, compound id table, substrate lists
  experiments.py        growth-medium presets
  kegg.py               KEGG REST client with on-disk cache; KGML/PNG parsing
  analysis.py           model loading, media, pFBA/FVA, KEGG mapping, balances
  figures.py            map overlay computation and Plotly rendering
  cache.py              thread-safe LRU cache with single-flight computation
  jobs.py               in-process background jobs with progress reporting
  ui/                   Dash layout, render helpers and callbacks
assets/                 stylesheet and light/dark theme script
models/                 your SBML models (not tracked)
tests/                  pytest suite (+ optional browser tests in tests/e2e)
```

## Tests

```bash
pytest                  # unit and characterization tests
pytest -m e2e           # browser walkthrough (needs: playwright install chromium)
```

The characterization tests pin results for a reference model
(`models/RehMBEL1391_sbml_L3V1.xml`). They are skipped when that file is absent, and the
rest of the suite still runs. Tests that touch KEGG download the files they need on
first run.

## KEGG data and licensing

The code is released under the [MIT License](LICENSE). KEGG pathway images, KGML files
and link tables are **not** part of this repository. They are downloaded at runtime
from the KEGG REST API, shown unmodified as the map background, and remain subject to
[KEGG's terms of use](https://www.kegg.jp/kegg/legal.html). Those terms include
restrictions on commercial use and on redistributing KEGG data. Check that your use
complies before deploying publicly.

## Limitations

- Each enzyme box is coloured by the mapped model reaction with the largest |flux|.
  Isozymes and multi-reaction boxes are therefore summarised, not drawn separately.
- Pathway coverage depends on the model's annotations. Reactions without
  `kegg.reaction` or `ec-code` annotations can't be placed on maps.
- FVA runs on request for one pathway at a time and isn't run in the background.
