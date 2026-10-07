"""Phase 1 defect fixes: uploads, untrusted keys, cache eviction, FVA concurrency, tie-break."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from kfm import analysis, figures
from kfm.cache import LRUCache
from kfm.config import ROOT, UPLOAD_DIR
from kfm.kegg import ReactionBox

from .conftest import MODEL


@pytest.mark.parametrize("name", ["../../etc/evil.xml", "/abs/path/evil.xml",
                                  "..\\..\\win\\evil.xml", "evil.xml"])
def test_upload_keeps_only_base_name(name):
    dest = Path(analysis.save_upload(name, b"<sbml/>"))
    try:
        assert dest == (UPLOAD_DIR / "evil.xml").resolve()
    finally:
        dest.unlink()


@pytest.mark.parametrize("name", ["evil.exe", "", "..", "noext"])
def test_upload_rejects_bad_names(name):
    with pytest.raises(ValueError):
        analysis.save_upload(name, b"x")


def test_upload_rejects_oversize(monkeypatch):
    monkeypatch.setattr(analysis, "MAX_UPLOAD_BYTES", 4)
    with pytest.raises(ValueError, match="too large"):
        analysis.save_upload("big.xml", b"12345")


@pytest.mark.parametrize("path", ["/etc/passwd", str(ROOT / "app.py"),
                                  str(ROOT / "models" / ".." / "app.py"),
                                  str(ROOT / "models" / "missing.xml"), ""])
def test_untrusted_model_paths_rejected(path):
    with pytest.raises(ValueError):
        analysis.trusted_model_path(path)


@pytest.mark.parametrize("key", [None, "", "no-separator", "/etc/passwd|m9_fructose"])
def test_get_by_key_rejects_bad_keys(key):
    assert analysis.get_by_key(key) is None


def test_get_by_key_recomputes_after_eviction(fructose, monkeypatch):
    key, res = fructose
    monkeypatch.setattr(analysis, "_results", LRUCache(8))
    again = analysis.get_by_key(key)
    assert again is not res
    assert again.objective_value == pytest.approx(res.objective_value)


def test_concurrent_fva_on_shared_result(fructose):
    res = fructose[1]
    with ThreadPoolExecutor(8) as pool:
        out = list(pool.map(lambda _: analysis.fva_for_reactions(res, ["PGK", "GAPD"]),
                            range(8)))
    assert all(o == out[0] for o in out) and set(out[0]) == {"PGK", "GAPD"}


def test_box_tie_break_is_alphabetical():
    box = ReactionBox(0, 0, 1, 1, {"R1", "R2"}, "x")
    R_to_rxn = {"R1": {"ZZZ"}, "R2": {"AAA", "MMM"}}
    assert figures._box_flux(box, {"ZZZ": 2.0, "AAA": 2.0, "MMM": -2.0}, R_to_rxn) == ("AAA", 2.0)
    assert figures._box_flux(box, {"MMM": -3.0}, R_to_rxn) == ("MMM", -3.0)
    assert figures._box_flux(box, {}, R_to_rxn) == ("AAA", 0.0)
