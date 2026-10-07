"""Phase 2 building blocks: LRU cache, pure overlays, memoised maps, typed records."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from kfm import analysis, figures, kegg
from kfm.cache import LRUCache


def test_lru_evicts_least_recently_used():
    c = LRUCache(2)
    c.get_or_compute("a", lambda: 1)
    c.get_or_compute("b", lambda: 2)
    assert c.get("a") == 1          # touch a → b is now oldest
    c.get_or_compute("c", lambda: 3)
    assert c.get("b") is None and c.get("a") == 1 and len(c) == 2


def test_lru_single_flight():
    c, calls = LRUCache(4), []

    def slow():
        calls.append(threading.get_ident())
        time.sleep(0.2)
        return "v"

    with ThreadPoolExecutor(8) as pool:
        out = list(pool.map(lambda _: c.get_or_compute("k", slow), range(8)))
    assert out == ["v"] * 8 and len(calls) == 1


def test_lru_failure_is_not_cached():
    c = LRUCache(2)
    with pytest.raises(RuntimeError):
        c.get_or_compute("k", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert c.get_or_compute("k", lambda: 5) == 5


def test_pathway_map_is_memoised_and_immutable():
    pm = kegg.pathway_map("map00710")
    assert kegg.pathway_map("map00710") is pm
    with pytest.raises(AttributeError):
        pm.boxes[0].x = 1.0


def test_compute_overlays_pure(fructose, autotrophic):
    pm = kegg.pathway_map("map00010")
    single = figures.compute_overlays(pm, fructose[1])
    delta = figures.compute_overlays(pm, fructose[1], autotrophic[1])
    assert [o.rxn_id for o in single] == [o.rxn_id for o in delta]
    for s, d in zip(single, delta):
        assert s.value == s.fa and d.value == pytest.approx(d.fa - d.fb)
    assert figures.compute_overlays(pm, fructose[1]) == single


def test_fva_for_pathway_cached(fructose):
    key, _ = fructose
    first = analysis.fva_for_pathway(key, "map00010")
    assert first and analysis.fva_for_pathway(key, "map00010") is first


def test_typed_records(fructose):
    res = fructose[1]
    assert isinstance(res.balance, analysis.Balance)
    assert all(isinstance(e, analysis.Exchange) for e in res.exchanges)
    assert {e.role for e in res.exchanges} == {"uptake", "secretion"}
