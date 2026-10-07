"""
Paths, constants and shared lookup tables for the KEGG Flux Mapper.

Runtime settings come from the environment (all optional):
  KFM_HOST (127.0.0.1)   KFM_PORT (8050)   KFM_DEBUG (off; 1/true/yes/on enables)
  KFM_CACHE_SIZE (8)     KFM_KEGG_CACHE (<repo>/kegg_cache)
"""

import os
from pathlib import Path


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


# ── Runtime ──────────────────────────────────────────────────────────────────────
HOST  = os.environ.get("KFM_HOST", "127.0.0.1")
PORT  = _env_int("KFM_PORT", 8050)
DEBUG = os.environ.get("KFM_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}

# ── Paths ────────────────────────────────────────────────────────────────────────
ROOT       = Path(__file__).resolve().parent.parent   # repository root
MODELS_DIR = ROOT / "models"
KEGG_CACHE = Path(os.environ.get("KFM_KEGG_CACHE", ROOT / "kegg_cache")).resolve()
UPLOAD_DIR = KEGG_CACHE / "_uploads"
MODELS_DIR.mkdir(exist_ok=True)
KEGG_CACHE.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)

# ── KEGG / numerical constants ───────────────────────────────────────────────────
KEGG_REST = "https://rest.kegg.jp"
KEGG_WEB  = "https://www.kegg.jp"
FLUX_EPS  = 1e-7        # |flux| below this is treated as inactive
ANALYSIS_CACHE_SIZE = max(1, _env_int("KFM_CACHE_SIZE", 8))  # LRU bound on analysis results


# ── Local models (every SBML file under ./models, labelled by relative path) ──────
def discover_models() -> dict[str, str]:
    """Return {relative_label: absolute_path} for all SBML models under models/."""
    return {
        str(p.relative_to(MODELS_DIR)): str(p)
        for p in sorted(MODELS_DIR.rglob("*.xml"))
    }


# ── Compound identity table ──────────────────────────────────────────────────────
# Each metabolite of interest is keyed by a short name and carries every namespace
# id we might meet across model families (KEGG C-numbers on BiGG/KEGG-annotated
# models, ModelSEED cpd-numbers on ModelSEED/gapseq-built models).  apply_experiment()
# and the exchange summary match an exchange to a compound if *any* of these ids
# appears in the metabolite's annotation.
COMPOUNDS: dict[str, dict] = {
    # key            display              KEGG C-numbers          SEED cpd-numbers
    "h2o":      {"name": "H₂O",        "kegg": ["C00001"],          "seed": ["cpd00001"]},
    "phosphate":{"name": "Phosphate",  "kegg": ["C00009"],          "seed": ["cpd00009"]},
    "sulfate":  {"name": "Sulfate",    "kegg": ["C00059"],          "seed": ["cpd00048"]},
    "proton":   {"name": "H⁺",         "kegg": ["C00080"],          "seed": ["cpd00067"]},
    "nh4":      {"name": "NH₄⁺",       "kegg": ["C00014", "C01342"],"seed": ["cpd00013"]},
    "fe2":      {"name": "Fe²⁺",       "kegg": ["C14818", "C00023"],"seed": ["cpd10515"]},
    "o2":       {"name": "O₂",         "kegg": ["C00007"],          "seed": ["cpd00007"]},
    "co2":      {"name": "CO₂",        "kegg": ["C00011"],          "seed": ["cpd00011"]},
    "h2":       {"name": "H₂",         "kegg": ["C00282"],          "seed": ["cpd11640"]},
    "fructose": {"name": "D-Fructose", "kegg": ["C00095"],          "seed": ["cpd00082"]},
    "succinate":{"name": "Succinate",  "kegg": ["C00042"],          "seed": ["cpd00036"]},
    "gluconate":{"name": "D-Gluconate","kegg": ["C00257"],          "seed": ["cpd00222"]},
    "formate":  {"name": "Formate",    "kegg": ["C00058"],          "seed": ["cpd00047"]},
    "palmitate":{"name": "Palmitate",  "kegg": ["C00249"],          "seed": ["cpd00214"]},
    "acetate":  {"name": "Acetate",    "kegg": ["C00033"],          "seed": ["cpd00029"]},
    "glucose":  {"name": "D-Glucose",  "kegg": ["C00031"],          "seed": ["cpd00027"]},
    "pyruvate": {"name": "Pyruvate",   "kegg": ["C00022"],          "seed": ["cpd00020"]},

    # Polyethylene (LDPE) depolymerisation products: long-chain alcohols, fatty acids
    # and short organic acids.  Metabolites without a seed.compound annotation are
    # also matched by a ModelSEED cpd-number in their id (see _met_compound_key).
    "octadecanol": {"name": "1-Octadecanol (C18-OH)", "kegg": [],         "seed": ["cpd11545"]},
    "hexadecanol": {"name": "1-Hexadecanol (C16-OH)", "kegg": [],         "seed": ["cpd01352"]},
    "tetradecanol":{"name": "1-Tetradecanol (C14-OH)","kegg": [],         "seed": ["cpd03298"]},
    "dodecanol":   {"name": "1-Dodecanol (C12-OH)",   "kegg": [],         "seed": ["cpd01091"]},
    "decanol":     {"name": "1-Decanol (C10-OH)",     "kegg": [],         "seed": ["cpd01090"]},
    "oleate":      {"name": "Oleate (C18:1)",         "kegg": ["C00712"], "seed": ["cpd15269"]},
    "palmitoleate":{"name": "Palmitoleate (C16:1)",   "kegg": [],         "seed": ["cpd15237"]},
    "myristate":   {"name": "Myristate (C14:0)",      "kegg": ["C06424"], "seed": ["cpd03847"]},
    "decanoate":   {"name": "Decanoate (C10:0)",      "kegg": ["C01571"], "seed": ["cpd01107"]},
    "octanoate":   {"name": "Octanoate (C8:0)",       "kegg": ["C06423"], "seed": ["cpd03846"]},
    "hexanoate":   {"name": "Hexanoate (C6:0)",       "kegg": ["C01585"], "seed": ["cpd01113"]},
    "butyrate":    {"name": "Butyrate (C4:0)",        "kegg": ["C00246"], "seed": ["cpd00211"]},
    "propionate":  {"name": "Propionate (C3:0)",      "kegg": ["C00163"], "seed": ["cpd00141"]},
    "glycolate":   {"name": "Glycolate",              "kegg": ["C00160"], "seed": ["cpd00139"]},
    "lactate":     {"name": "L-Lactate",              "kegg": ["C00186"], "seed": ["cpd00159"]},
}

# M9 mineral salts opened (lb = −1000) in every constructed medium.
M9_MINERALS = ["h2o", "phosphate", "sulfate", "proton", "fe2"]

# LDPE-depolymerization substrates screened as sole carbon source (display order).
LDPE_SUBSTRATES = ["octadecanol", "hexadecanol", "tetradecanol", "dodecanol", "decanol",
                   "oleate", "palmitoleate", "palmitate", "myristate", "decanoate",
                   "octanoate", "hexanoate", "butyrate", "propionate", "glycolate", "lactate"]

# Standard reference carbon sources also offered in the growth screen.
STANDARD_SUBSTRATES = ["fructose", "glucose", "succinate", "gluconate", "acetate", "pyruvate"]

# Full ordered list driving the substrate growth screen.
SUBSTRATE_SCREEN = LDPE_SUBSTRATES + STANDARD_SUBSTRATES

# Sole-carbon uptake bound used by the substrate growth screen.
SCREEN_UPTAKE = -10.0

# Carbon/energy sources whose uptake is closed before a medium opens its own.
CARBON_SOURCES = ["fructose", "succinate", "gluconate", "formate", "co2", "h2",
                  "acetate", "glucose", "pyruvate"] + LDPE_SUBSTRATES


def compound_id_sets() -> dict[str, set[str]]:
    """Return {compound_key: {all namespace ids}} for fast membership tests."""
    return {
        key: set(spec["kegg"]) | set(spec["seed"])
        for key, spec in COMPOUNDS.items()
    }
