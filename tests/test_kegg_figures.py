import pytest

from kfm import figures, kegg


# KEGG data is downloaded live and changes between releases, so these checks are
# structural; exact numbers are pinned only for model results.

def test_png_size():
    assert kegg.png_size(b"not a png") == (0, 0)
    pm = kegg.pathway_map("map00710")
    w, h = kegg.png_size(pm.png)
    assert (w, h) == (pm.width, pm.height) and w > 500 and h > 500


def test_pathway_map_parsed():
    pm = kegg.pathway_map("map00710")
    assert pm.available and len(pm.boxes) >= 20
    assert all(b.reactions for b in pm.boxes)


def test_global_tables():
    index = kegg.pathway_index()
    assert len(index) > 150 and index["map00010"]["name"].startswith("Glycolysis")
    assert len(kegg.ec_to_reactions()) > 5000


def test_pathway_figure(fructose):
    fig, df, summary = figures.build_pathway_figure("map00710", fructose[1])
    assert summary["mapped"] == 27 and summary["active"] == 17
    assert summary["total_flux"] == pytest.approx(18.2086, abs=1e-3)
    assert summary["net_flux"] == pytest.approx(9.5717, abs=1e-3)
    assert list(df.columns) == ["Reaction", "Name", "Flux", "LB", "UB", "R-number"]
    assert len(df) == 17 and len(fig.layout.shapes) == 27
    assert df["Flux"].abs().is_monotonic_decreasing


def test_pathway_figure_with_fva(fructose):
    res = fructose[1]
    fva = {"PGK": (-1.0, 1.0)}
    _, df, _ = figures.build_pathway_figure("map00010", res, fva=fva)
    assert {"FVA min", "FVA max"} <= set(df.columns)


def test_delta_figure(fructose, autotrophic):
    fig, df = figures.build_delta_figure("map00010", fructose[1], autotrophic[1])
    assert list(df.columns) == ["Reaction", "Name", "Flux A", "Flux B", "Δ (A−B)"]
    assert len(df) == 19
    assert df["Δ (A−B)"].abs().max() == pytest.approx(13.6669, abs=1e-3)


def test_map_without_enzyme_boxes(fructose):
    fig, df, summary = figures.build_pathway_figure("map01100", fructose[1])
    assert df.empty and summary["mapped"] == 0
