"""
Model loading, medium application, flux solving and KEGG mapping.

The public entry point is `get_analysis(model_path, experiment_key)`, which returns a
cached `AnalysisResult`.  Heavy objects (the cobra model, the flux vector, the KEGG
mapping) live only in the server-side LRU cache; Dash stores hold the cache key.
"""

import logging
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import cobra
import cobra.io
import pandas as pd
from cobra.exceptions import OptimizationError

from . import kegg
from .cache import LRUCache
from .config import (ANALYSIS_CACHE_SIZE, COMPOUNDS, CARBON_SOURCES, FLUX_EPS,
                     LDPE_SUBSTRATES, M9_MINERALS, MODELS_DIR, SCREEN_UPTAKE,
                     SUBSTRATE_SCREEN, UPLOAD_DIR, compound_id_sets)
from .experiments import experiment_for_key

log = logging.getLogger("kfm")

Progress = Callable[[str], None] | None


def _noop(_stage: str) -> None:
    pass


# ── Result records ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Exchange:
    id: str
    metabolite: str
    compound: str | None        # COMPOUNDS key, if recognised
    flux: float                 # < 0 = uptake, > 0 = secretion
    carbon: int                 # C atoms in the exchanged metabolite

    @property
    def role(self) -> str:
        return "uptake" if self.flux < 0 else "secretion"


@dataclass(frozen=True)
class Balance:
    objective: str
    objective_value: float
    c_uptake: float             # mmol C/gDW/h
    c_products: float
    co2_out: float
    o2_uptake: float
    carbon_efficiency: float | None     # fraction of C not lost as CO₂
    biomass_yield_per_c: float | None
    respiratory_quotient: float | None  # CO₂ / O₂
    c_to_n: float | None


@dataclass
class AnalysisResult:
    model: cobra.Model
    fluxes: dict
    method: str
    objective_value: float
    objective_rxn: str
    rxn_to_R: dict
    R_to_rxn: dict
    scores: pd.DataFrame
    notes: list
    exchanges: list[Exchange]
    balance: Balance
    n_rxn: int
    n_active: int
    n_mapped: int
    # Guards solver use of the shared cached `model` (e.g. FVA) across request threads.
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)


# ── Caches ────────────────────────────────────────────────────────────────────────

_results: LRUCache[AnalysisResult] = LRUCache(ANALYSIS_CACHE_SIZE)
_screens: LRUCache[pd.DataFrame] = LRUCache(ANALYSIS_CACHE_SIZE)
_fva: LRUCache[dict] = LRUCache(64)


def get_analysis(model_path: str, experiment_key: str,
                 progress: Progress = None) -> tuple[str, AnalysisResult]:
    """Return (cache_key, AnalysisResult), computing + caching on first request."""
    model_path = trusted_model_path(model_path)
    key = f"{model_path}|{experiment_key}"
    return key, _results.get_or_compute(
        key, lambda: run_analysis(model_path, experiment_key, progress))


def get_by_key(key: str | None) -> AnalysisResult | None:
    """Resolve a browser-held cache key, recomputing if it was evicted.

    Keys round-trip through the client, so the embedded model path is re-validated.
    Returns None for malformed or untrusted keys.
    """
    if not key:
        return None
    hit = _results.get(key)
    if hit is not None:
        return hit
    model_path, sep, experiment_key = key.rpartition("|")
    if not sep:
        return None
    try:
        return get_analysis(model_path, experiment_key)[1]
    except ValueError as exc:
        log.warning("Rejected analysis key %r: %s", key, exc)
        return None


def get_substrate_screen(model_path: str, progress: Progress = None) -> pd.DataFrame:
    """Cached `screen_substrates` keyed on the model path."""
    model_path = trusted_model_path(model_path)
    return _screens.get_or_compute(
        model_path, lambda: screen_substrates(model_path, progress=progress))


def fva_for_pathway(key: str, map_id: str) -> dict:
    """Cached FVA ranges for the model reactions mapped onto one KEGG pathway."""
    result = get_by_key(key)
    if result is None:
        return {}

    def compute():
        prs = kegg.pathway_index().get(map_id, {}).get("reactions", set())
        rxn_ids = sorted({rid for r in prs for rid in result.R_to_rxn.get(r, ())})
        return fva_for_reactions(result, rxn_ids)

    return _fva.get_or_compute((key, map_id), compute)


# ── Model files: trusted locations + uploads ──────────────────────────────────────

_MODEL_ROOTS = (MODELS_DIR.resolve(), UPLOAD_DIR.resolve())
UPLOAD_SUFFIXES = {".xml", ".sbml", ".json", ".mat"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def trusted_model_path(path: str) -> str:
    """Resolve `path`, accepting only existing files under the models/upload dirs."""
    p = Path(path or "").resolve()
    if not any(p.is_relative_to(root) for root in _MODEL_ROOTS) or not p.is_file():
        raise ValueError(f"Model file not available: {path}")
    return str(p)


def save_upload(filename: str, data: bytes) -> str:
    """Store an uploaded model under UPLOAD_DIR using only its base name."""
    name = Path((filename or "").replace("\\", "/")).name
    if not name or Path(name).suffix.lower() not in UPLOAD_SUFFIXES:
        raise ValueError("Unsupported file type — upload SBML (.xml/.sbml), JSON or .mat.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"File too large (limit {MAX_UPLOAD_BYTES // 2**20} MB).")
    dest = UPLOAD_DIR / name
    dest.write_bytes(data)
    return str(dest.resolve())


# ── Model loading ─────────────────────────────────────────────────────────────────

def load_model(path: str) -> cobra.Model:
    p = path.lower()
    if p.endswith(".json"):
        return cobra.io.load_json_model(path)
    if p.endswith(".mat"):
        return cobra.io.load_matlab_model(path)
    return cobra.io.read_sbml_model(path)


def _objective_reaction(model: cobra.Model) -> str | None:
    return next((r.id for r in model.reactions if r.objective_coefficient != 0), None)


def _as_list(v):
    if v is None:
        return []
    return list(v) if isinstance(v, (list, tuple, set)) else [v]


def _met_compound_key(met, id_sets: dict) -> str | None:
    """Which COMPOUNDS key (if any) this metabolite matches.

    Primary match is on kegg.compound / seed.compound annotations; as a fallback we
    also parse any ModelSEED cpd-number embedded in the metabolite id (e.g.
    ``M_cpd11545_e0``), for metabolites that carry no annotation.
    """
    ids = set(_as_list(met.annotation.get("kegg.compound"))) | \
          set(_as_list(met.annotation.get("seed.compound"))) | \
          set(re.findall(r"cpd\d+", met.id))
    for key, valid in id_sets.items():
        if ids & valid:
            return key
    return None


def _exchange_index(model: cobra.Model, id_sets: dict) -> dict:
    """{compound_key: exchange_reaction} for medium handling + exchange summary."""
    idx = {}
    for ex in model.exchanges:
        for met in ex.metabolites:
            key = _met_compound_key(met, id_sets)
            if key:
                idx.setdefault(key, ex)
    return idx


def _element_count(met, element: str) -> int:
    if met is None:
        return 0
    try:
        return int(met.elements.get(element, 0))
    except (TypeError, ValueError):
        return 0


# ── Medium application ────────────────────────────────────────────────────────────

def set_medium(model: cobra.Model, comp2ex: dict, carbon: dict,
               o2: float | None, nh4: float | None) -> list[str]:
    """Construct an M9 + carbon-source medium in-place; return human-readable notes.

    Closes every recognised carbon uptake, opens M9 minerals, applies the O₂/NH₄
    regimes, then opens the requested carbon source(s).  `comp2ex` is the
    {compound_key: exchange_reaction} index from `_exchange_index`.
    """
    notes = []

    # 1. Close every recognised carbon/energy uptake.
    for ckey in CARBON_SOURCES:
        ex = comp2ex.get(ckey)
        if ex is not None and ex.lower_bound < 0:
            ex.lower_bound = 0.0

    # 2. Open M9 minerals.
    for mkey in M9_MINERALS:
        ex = comp2ex.get(mkey)
        if ex is not None:
            ex.lower_bound = min(ex.lower_bound, -1000.0)

    # 3. O₂ and NH₄ regimes.
    for ckey, bound in (("o2", o2), ("nh4", nh4)):
        if bound is None:
            continue
        ex = comp2ex.get(ckey)
        if ex is not None:
            ex.lower_bound = bound
        else:
            notes.append(f"⚠ no exchange found for {COMPOUNDS[ckey]['name']}")

    # 4. Open the carbon source(s).
    for ckey, bound in carbon.items():
        ex = comp2ex.get(ckey)
        if ex is not None:
            ex.lower_bound = bound
            notes.append(f"opened {ex.id} ({COMPOUNDS[ckey]['name']}) at {abs(bound):g}")
        else:
            notes.append(f"⚠ no exchange found for {COMPOUNDS[ckey]['name']}")
    return notes


def apply_experiment(model: cobra.Model, experiment_key: str) -> list[str]:
    """Apply an experiment's medium in-place (rules in experiments.py)."""
    exp = experiment_for_key(experiment_key)
    if exp.trust_xml:
        return ["Using the model's own exchange bounds (trust XML)."]
    comp2ex = _exchange_index(model, compound_id_sets())
    return set_medium(model, comp2ex, exp.carbon, exp.o2, exp.nh4)


# ── Flux solving ──────────────────────────────────────────────────────────────────

def solve_fluxes(model: cobra.Model) -> tuple[dict, str]:
    """Return ({reaction_id: flux}, method). Tries pFBA, falls back to plain FBA."""
    from cobra.flux_analysis import pfba
    try:
        sol = pfba(model)
        return sol.fluxes.to_dict(), "pFBA"
    except OptimizationError as exc:
        log.info("pFBA failed (%s); falling back to FBA", exc)
    sol = model.optimize()
    if sol.status != "optimal":
        raise RuntimeError(f"FBA returned status '{sol.status}'.")
    return sol.fluxes.to_dict(), "FBA"


# ── KEGG mapping + pathway scoring ────────────────────────────────────────────────

def map_reactions_to_kegg(model: cobra.Model) -> tuple[dict, dict]:
    """rxn_to_R {reaction_id: set(R)} and its inverse R_to_rxn (direct + EC-expanded)."""
    ec2rn = kegg.ec_to_reactions()
    rxn_to_R, R_to_rxn = {}, {}
    for rxn in model.reactions:
        rs = set()
        for r in _as_list(rxn.annotation.get("kegg.reaction")):
            if isinstance(r, str) and r.startswith("R"):
                rs.add(r)
        for ec in _as_list(rxn.annotation.get("ec-code")):
            rs |= ec2rn.get(ec, set())
        if rs:
            rxn_to_R[rxn.id] = rs
            for r in rs:
                R_to_rxn.setdefault(r, set()).add(rxn.id)
    return rxn_to_R, R_to_rxn


def score_pathways(model_R: set, R_to_rxn: dict) -> pd.DataFrame:
    """Coverage = fraction of a pathway's R-numbers present in the model."""
    rows = []
    for pid, info in kegg.pathway_index().items():
        prs = info["reactions"]
        hit = prs & model_R
        if not hit:
            continue
        mapped = {rid for r in hit for rid in R_to_rxn.get(r, ())}
        rows.append({
            "KEGG ID": pid, "Pathway": info["name"],
            "Coverage %": round(100 * len(hit) / len(prs), 1),
            "Rxns mapped": len(mapped), "Pathway rxns": len(prs),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values(["Coverage %", "Rxns mapped"], ascending=False).reset_index(drop=True)


# ── Exchange summary + carbon balance ─────────────────────────────────────────────

def exchange_summary(model, fluxes, id_sets) -> list[Exchange]:
    """Active exchange fluxes named by metabolite, largest |flux| first."""
    rows = []
    for ex in model.exchanges:
        f = fluxes.get(ex.id, 0.0)
        if abs(f) < FLUX_EPS:
            continue
        met = next(iter(ex.metabolites), None)
        rows.append(Exchange(
            id=ex.id,
            metabolite=met.name if met else ex.id,
            compound=_met_compound_key(met, id_sets) if met else None,
            flux=f,
            carbon=_element_count(met, "C"),
        ))
    return sorted(rows, key=lambda e: abs(e.flux), reverse=True)


def carbon_balance(model, fluxes, exchanges: list[Exchange], objective_rxn: str,
                   objective_value: float) -> Balance:
    """Carbon/nitrogen balance and yield metrics from the exchange fluxes."""
    uptakes = [e for e in exchanges if e.role == "uptake"]
    secretions = [e for e in exchanges if e.role == "secretion"]
    c_in = sum(-e.flux * e.carbon for e in uptakes)
    c_out_prod = sum(e.flux * e.carbon for e in secretions if e.compound != "co2")
    co2_out = sum(e.flux for e in secretions if e.compound == "co2")
    o2_in = sum(-e.flux for e in uptakes if e.compound == "o2")

    n_in = 0.0
    for ex in model.exchanges:
        f = fluxes.get(ex.id, 0.0)
        if f < -FLUX_EPS:
            n_in += -f * _element_count(next(iter(ex.metabolites), None), "N")

    # Carbon into biomass = remainder of the carbon balance (C_in − products − CO₂).
    c_biomass = max(c_in - c_out_prod - co2_out, 0.0)

    def ratio(a, b):
        return a / b if b > FLUX_EPS else None

    return Balance(
        objective=objective_rxn,
        objective_value=objective_value,
        c_uptake=c_in,
        c_products=c_out_prod,
        co2_out=co2_out,
        o2_uptake=o2_in,
        carbon_efficiency=ratio(c_biomass + c_out_prod, c_in),
        biomass_yield_per_c=ratio(objective_value, c_in),
        respiratory_quotient=ratio(co2_out, o2_in),
        c_to_n=ratio(c_in, n_in),
    )


# ── Driver ────────────────────────────────────────────────────────────────────────

def run_analysis(model_path: str, experiment_key: str,
                 progress: Progress = None) -> AnalysisResult:
    step = progress or _noop
    step("Loading model…")
    model = load_model(model_path)
    step("Applying medium…")
    notes = apply_experiment(model, experiment_key)
    step("Solving pFBA…")
    try:
        fluxes, method = solve_fluxes(model)
    except RuntimeError:
        if experiment_key == "model_default":
            raise
        model = load_model(model_path)
        notes = [f"⚠ '{experiment_for_key(experiment_key).label}' was infeasible for this "
                 "model; reverted to the model's default bounds."]
        fluxes, method = solve_fluxes(model)

    obj_rxn = _objective_reaction(model) or "objective"
    obj_val = fluxes.get(obj_rxn, 0.0)

    step("Mapping to KEGG…")
    rxn_to_R, R_to_rxn = map_reactions_to_kegg(model)
    scores = score_pathways(set(R_to_rxn), R_to_rxn)

    step("Summarising exchanges…")
    exchanges = exchange_summary(model, fluxes, compound_id_sets())
    balance = carbon_balance(model, fluxes, exchanges, obj_rxn, obj_val)

    return AnalysisResult(
        model=model, fluxes=fluxes, method=method,
        objective_value=obj_val, objective_rxn=obj_rxn,
        rxn_to_R=rxn_to_R, R_to_rxn=R_to_rxn, scores=scores, notes=notes,
        exchanges=exchanges, balance=balance,
        n_rxn=len(model.reactions),
        n_active=sum(1 for f in fluxes.values() if abs(f) >= FLUX_EPS),
        n_mapped=len(rxn_to_R),
    )


# ── Substrate growth screen ───────────────────────────────────────────────────────

def screen_substrates(model_path: str, substrate_keys: list[str] | None = None,
                      uptake: float = SCREEN_UPTAKE, o2: float = -1000.0,
                      nh4: float = -1000.0, progress: Progress = None) -> pd.DataFrame:
    """Growth rate µ for each candidate substrate as the sole carbon source on M9.

    Each substrate is opened at `uptake` (aerobic M9); the biomass objective is
    maximised (pFBA → FBA).  Returns a DataFrame sorted by µ descending.  Substrates
    with no exchange in the model, or that cannot support growth, are reported too.
    KEGG mapping is skipped, so the sweep is fast (one objective solve per substrate).
    """
    keys = substrate_keys or SUBSTRATE_SCREEN
    step = progress or _noop
    step("Loading model…")
    model = load_model(trusted_model_path(model_path))
    comp2ex = _exchange_index(model, compound_id_sets())
    obj_rxn = _objective_reaction(model)

    rows = []
    for i, ckey in enumerate(keys, 1):
        name = COMPOUNDS.get(ckey, {}).get("name", ckey)
        step(f"Screening {name} ({i}/{len(keys)})…")
        klass = "LDPE" if ckey in LDPE_SUBSTRATES else "standard"
        ex = comp2ex.get(ckey)
        if ex is None:
            rows.append({"Substrate": name, "Class": klass, "Exchange": "—",
                         "mu": None, "yield_c": None, "Feasible": "no exchange",
                         "_key": ckey})
            continue
        carbon = _element_count(next(iter(ex.metabolites), None), "C")
        with model:                      # cobra restores all bounds on exit
            set_medium(model, comp2ex, {ckey: uptake}, o2, nh4)
            try:
                fluxes, _ = solve_fluxes(model)
                mu = fluxes.get(obj_rxn, 0.0) if obj_rxn else 0.0
            except (OptimizationError, RuntimeError):
                mu = 0.0
        mu = round(max(mu, 0.0), 5)
        yld = (round(mu / (abs(uptake) * carbon), 5)
               if carbon and abs(uptake) > FLUX_EPS else None)
        rows.append({"Substrate": name, "Class": klass, "Exchange": ex.id,
                     "mu": mu, "yield_c": yld,
                     "Feasible": "yes" if mu > FLUX_EPS else "no", "_key": ckey})

    df = pd.DataFrame(rows)
    df["_sort"] = df["mu"].fillna(-1.0)
    return df.sort_values("_sort", ascending=False).drop(columns="_sort").reset_index(drop=True)


# ── FVA (lazy, scoped to a set of reactions) ──────────────────────────────────────

def fva_for_reactions(result: AnalysisResult, rxn_ids: list[str],
                      fraction: float = 0.9) -> dict:
    """{reaction_id: (min, max)} from FVA over just `rxn_ids`. Empty on failure."""
    from cobra.flux_analysis import flux_variability_analysis
    model = result.model
    rxn_ids = [r for r in rxn_ids if r in model.reactions]
    if not rxn_ids:
        return {}
    try:
        with result.lock:
            df = flux_variability_analysis(
                model, reaction_list=rxn_ids, fraction_of_optimum=fraction)
    except OptimizationError as exc:
        log.warning("FVA failed for %d reactions: %s", len(rxn_ids), exc)
        return {}
    return {rid: (round(float(row["minimum"]), 5), round(float(row["maximum"]), 5))
            for rid, row in df.iterrows()}
