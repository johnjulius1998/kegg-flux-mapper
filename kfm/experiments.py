"""
Experiment-setup registry.

Each Experiment describes a growth medium as exchange-uptake bounds, expressed against
the compound keys in config.py so the same preset applies to BiGG, ModelSEED and
KEGG-annotated models alike.

Rules for constructed media:
  * Close every recognised carbon uptake, open the M9 minerals, then open the carbon
    source(s) and apply the O₂ / NH₄ regime.
  * `model_default` edits nothing ("trust XML"): use it when the model file already
    encodes the condition you want.
"""

from dataclasses import dataclass, field

from .config import COMPOUNDS, SCREEN_UPTAKE


@dataclass
class Experiment:
    key: str
    label: str
    description: str
    trust_xml: bool = False               # if True: do not edit any bounds
    carbon: dict = field(default_factory=dict)   # {compound_key: lower_bound}
    o2: float | None = None               # O₂ lower bound (None = leave unchanged)
    nh4: float | None = None              # NH₄ lower bound (None = leave unchanged)


# Ordered so the dropdown reads sensibly.
EXPERIMENTS: dict[str, Experiment] = {
    "model_default": Experiment(
        "model_default", "Model default (trust XML)",
        "Use the model's own exchange bounds and objective unchanged — for model files "
        "that already encode their growth condition.",
        trust_xml=True),

    "m9_fructose": Experiment(
        "m9_fructose", "M9 — Fructose (heterotrophic)",
        "M9 minerals + fructose at 2.6 mmol/gDW/h, aerobic.",
        carbon={"fructose": -2.6}, o2=-1000.0, nh4=-1000.0),

    "m9_succinate": Experiment(
        "m9_succinate", "M9 — Succinate (heterotrophic)",
        "M9 minerals + succinate at 3.5 mmol/gDW/h, aerobic.",
        carbon={"succinate": -3.5}, o2=-1000.0, nh4=-1000.0),

    "m9_gluconate": Experiment(
        "m9_gluconate", "M9 — Gluconate (heterotrophic)",
        "M9 minerals + gluconate at 3.5 mmol/gDW/h, aerobic.",
        carbon={"gluconate": -3.5}, o2=-1000.0, nh4=-1000.0),

    "m9_formate": Experiment(
        "m9_formate", "M9 — Formate (formatotrophic)",
        "M9 minerals + formate (10) and CO₂ (15), aerobic; carbon is fixed through the "
        "Calvin–Benson–Bassham (CBB) cycle.",
        carbon={"formate": -10.0, "co2": -15.0}, o2=-1000.0, nh4=-1000.0),

    "m9_auto": Experiment(
        "m9_auto", "M9 — CO₂ + H₂ (autotrophic)",
        "Knallgas growth: CO₂ (15) + H₂ (30) with O₂ limited to 10. Needs a model with an "
        "active CBB cycle and uptake hydrogenases.",
        carbon={"co2": -15.0, "h2": -30.0}, o2=-10.0, nh4=-1000.0),

    "phb_nlim": Experiment(
        "phb_nlim", "N-limited PHB (fructose, NH₄ cap)",
        "M9 + fructose (2.6) with ammonium capped at 0.1 (C:N ≈ 26) — the classic "
        "nitrogen-limited condition for polyhydroxybutyrate (PHB) accumulation.",
        carbon={"fructose": -2.6}, o2=-1000.0, nh4=-0.1),

    "m9_palmitate": Experiment(
        "m9_palmitate", "M9 — Palmitate (β-oxidation)",
        "M9 minerals + palmitate (C16:0) at 2.0 mmol/gDW/h as sole carbon source, aerobic.",
        carbon={"palmitate": -2.0}, o2=-1000.0, nh4=-1000.0),
}

# Model files whose name marks a pre-configured condition default to trusting their bounds.
_PRECONFIGURED_HINTS = ("auto_co2h2", "auto_phb", "formate", "phb_nlim", "phb_high")


def default_experiment_for(model_path: str) -> str:
    """Pick a sensible default experiment key from a model's filename."""
    name = model_path.lower()
    if any(h in name for h in _PRECONFIGURED_HINTS):
        return "model_default"
    return "m9_fructose"


def experiment_for_key(key: str) -> Experiment:
    """Resolve an experiment key to an Experiment.

    Static keys come from EXPERIMENTS; a dynamic ``substrate:<compound_key>`` key
    (emitted by the substrate growth screen) is turned into a one-off aerobic-M9
    experiment with that compound as the sole carbon source.
    """
    if key and key.startswith("substrate:"):
        ckey = key.split(":", 1)[1]
        name = COMPOUNDS.get(ckey, {}).get("name", ckey)
        return Experiment(
            key, f"M9 — {name} (sole carbon source)",
            f"M9 minerals + {name} at {abs(SCREEN_UPTAKE):g} mmol/gDW/h as the sole carbon "
            "source, aerobic. Constructed by the substrate growth screen.",
            carbon={ckey: SCREEN_UPTAKE}, o2=-1000.0, nh4=-1000.0)
    return EXPERIMENTS.get(key, EXPERIMENTS["model_default"])
