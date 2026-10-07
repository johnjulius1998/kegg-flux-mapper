import pytest

from kfm import analysis
from kfm.experiments import default_experiment_for, experiment_for_key

from .conftest import MODEL


def test_fructose_characterization(fructose):
    key, res = fructose
    assert key == f"{MODEL}|m9_fructose"
    assert res.method == "pFBA"
    assert res.objective_rxn == "Biomass"
    assert res.objective_value == pytest.approx(0.2472477, rel=1e-5)
    assert (res.n_rxn, res.n_active, res.n_mapped) == (1538, 362, 512)
    assert len(res.scores) == 121
    top = res.scores.iloc[0]
    assert (top["KEGG ID"], top["Coverage %"], top["Rxns mapped"]) == ("map00710", 91.7, 20)


def test_fructose_balance(fructose):
    b = fructose[1].balance
    assert b.objective == "Biomass"
    assert b.c_uptake == pytest.approx(15.6, abs=1e-3)
    assert b.co2_out == pytest.approx(5.331, abs=1e-3)
    assert b.carbon_efficiency == pytest.approx(0.6583, abs=1e-4)
    assert b.respiratory_quotient == pytest.approx(1.0728, abs=1e-4)
    assert b.c_to_n == pytest.approx(5.9254, abs=1e-4)


def test_exchanges_sorted_and_classified(fructose):
    ex = fructose[1].exchanges
    assert abs(ex[0].flux) >= abs(ex[-1].flux)
    h2o = next(e for e in ex if e.compound == "h2o")
    assert h2o.role == "secretion" and h2o.flux == pytest.approx(20.68443, abs=1e-4)


def test_autotrophic_objective(autotrophic):
    assert autotrophic[1].objective_value == pytest.approx(0.1608384, rel=1e-5)


def test_cache_returns_same_object(fructose, model_path):
    key, res = fructose
    assert analysis.get_analysis(model_path, "m9_fructose")[1] is res


def test_fva_ranges(fructose):
    fva = analysis.fva_for_reactions(fructose[1], ["PGK", "GAPD", "not_a_reaction"])
    assert set(fva) == {"PGK", "GAPD"}
    assert fva["PGK"] == pytest.approx((-4.73987, 3.62971), abs=1e-4)


def test_experiment_registry():
    sub = experiment_for_key("substrate:octadecanol")
    assert sub.carbon == {"octadecanol": -10.0} and "Octadecanol" in sub.label
    assert experiment_for_key("nope").key == "model_default"
    assert default_experiment_for("/models/example_auto_phb.xml") == "model_default"
    assert default_experiment_for("/models/example.xml") == "m9_fructose"
