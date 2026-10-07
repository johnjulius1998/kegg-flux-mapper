"""Browser walkthrough of the app.

    pytest -m e2e      # starts a fresh server on port 8765 (cold cache)
    KFM_E2E_URL=http://127.0.0.1:8050/ pytest -m e2e    # or use a running server

Needs `playwright` + Chromium, and the reference model in models/ (see tests/conftest.py).
The server is started with $KFM_PYTHON (default: this interpreter). The job tests expect
uncached experiments, so prefer the fresh-server mode.
"""

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e
sync_api = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parents[2]
SLOW = 240_000

if not (ROOT / "models" / "RehMBEL1391_sbml_L3V1.xml").is_file():
    pytest.skip("reference model not found in models/", allow_module_level=True)


@pytest.fixture(scope="module")
def url():
    if os.environ.get("KFM_E2E_URL"):
        yield os.environ["KFM_E2E_URL"]
        return
    port = "8765"
    proc = subprocess.Popen([os.environ.get("KFM_PYTHON", sys.executable), "app.py"], cwd=ROOT,
                            env={**os.environ, "KFM_PORT": port, "KFM_DEBUG": "0"},
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}/"
    try:
        for _ in range(120):
            try:
                urllib.request.urlopen(base, timeout=1)
                break
            except OSError:
                time.sleep(0.5)
        else:
            pytest.fail("app server did not start")
        yield base
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture(scope="module")
def page(browser, url):
    pg = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    pg.goto(url)
    yield pg


def test_full_flow(page):
    page.wait_for_selector("#config-modal .modal-content", timeout=20_000)
    page.click("#analyse-btn")
    page.wait_for_selector("#pathway-list .pw-row", timeout=SLOW)
    page.wait_for_selector("#pathway-graph .scatterlayer .point", timeout=SLOW)
    assert page.locator("#pathway-list .pw-row").count() > 50
    assert "reactions active" in page.inner_text("#map-subtitle")

    page.locator("#pathway-graph .scatterlayer .point").nth(3).click(force=True)
    page.wait_for_selector("#reaction-offcanvas.show", timeout=30_000)
    page.click("#reaction-offcanvas .btn-close")

    page.fill("#pathway-search", "glyco")
    page.wait_for_timeout(1000)
    page.locator("#pathway-list .pw-row").first.click()
    page.wait_for_function(
        "document.querySelector('#map-title').innerText.includes('Glycolysis')", timeout=SLOW)

    page.click("#open-table")
    page.wait_for_selector("#table-sheet.show", timeout=10_000)
    page.click("#table-sheet .btn-close")

    page.locator("#mode-seg label", has_text="Compare").click()
    page.wait_for_selector("#experiment-b-wrap.show", timeout=10_000)
    assert page.locator("#mode-seg label.active").inner_text() == "Flux"
    page.click("#analyse-btn")
    page.wait_for_function(
        "document.querySelector('#map-subtitle').innerText.includes('Δ')", timeout=SLOW)

    page.click(".tb-menu > button")
    page.click("#theme-toggle")
    assert page.evaluate("document.documentElement.dataset.bsTheme") in ("dark", "light")

    errors = page.locator(".dash-debug-menu__error-count")
    assert not errors.count() or errors.first.inner_text() == "0"
    assert not page.errors


def _start_analysis(page, experiment):
    page.click("#open-config")
    page.wait_for_selector("#config-modal .modal-content", timeout=10_000)
    page.click("#experiment-select")
    page.get_by_role("option", name=experiment).click()
    page.click("#analyse-btn")


def test_background_job_keeps_ui_responsive(page, browser, url):
    """Runs after test_full_flow (shared page). Uses experiments not yet cached."""
    page.wait_for_selector("#mode-seg")
    _start_analysis(page, "M9 — Palmitate (β-oxidation)")
    page.wait_for_selector("#job-cancel:not([hidden])", timeout=3_000)
    assert "…" in page.inner_text("#analyse-status")

    second = browser.new_page()
    t0 = time.time()
    second.goto(url)
    second.wait_for_selector("#config-modal .modal-content", timeout=10_000)
    assert page.locator("#job-cancel:not([hidden])").count() == 1, "job finished too early"
    assert time.time() - t0 < 10
    second.close()

    page.wait_for_selector("#job-cancel", state="hidden", timeout=SLOW)
    assert "Palmitate" in page.inner_text("#context-label")


def test_cancel_keeps_previous_results(page):
    title = page.inner_text("#map-title")
    context = page.inner_text("#context-label")
    _start_analysis(page, "N-limited PHB (fructose, NH₄ cap)")
    page.wait_for_selector("#job-cancel:not([hidden])", timeout=3_000)
    page.click("#job-cancel")
    page.wait_for_function(
        "document.querySelector('#analyse-status').innerText.includes('Cancelled')",
        timeout=5_000)
    assert page.inner_text("#map-title") == title
    assert page.inner_text("#context-label") == context
    page.click("#open-config")
    page.wait_for_selector("#analyse-btn", timeout=10_000)
    assert page.locator("#analyse-btn").is_enabled()
