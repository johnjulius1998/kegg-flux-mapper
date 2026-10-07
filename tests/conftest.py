"""Shared fixtures.

Characterization tests pin numbers for the reference model below.  Model files are
not distributed with the repository; tests that need it are skipped when it is absent.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MODEL = str(ROOT / "models" / "RehMBEL1391_sbml_L3V1.xml")


@pytest.fixture(scope="session")
def model_path():
    if not Path(MODEL).is_file():
        pytest.skip(f"reference model not found: {MODEL}")
    return MODEL


@pytest.fixture(scope="session")
def fructose(model_path):
    from kfm import analysis
    return analysis.get_analysis(model_path, "m9_fructose")


@pytest.fixture(scope="session")
def autotrophic(model_path):
    from kfm import analysis
    return analysis.get_analysis(model_path, "m9_auto")
