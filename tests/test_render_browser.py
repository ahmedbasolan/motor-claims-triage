"""In-browser render verification: computed styles, not CSS text.

tests/test_ui.py sees the element tree and asserts our stylesheet's
text; AppTest cannot see a rendered pixel, and rounds 3 and 4 both hit
that wall (the mono value spans, the dropdown rule, and the table spec
were verified as markup + stylesheet text only). This suite starts the
real app and reads computed styles back out of a real Chromium - the
outputs-vs-data audit, with the browser as the data.

Brand values are restated here from brand/tokens.css, per the suite's
rule: tests assert contracts, they never import them from app code.

Needs playwright + chromium (python -m playwright install chromium).
Skipped when either is missing; CI's render job sets
MCT_REQUIRE_BROWSER=1, which turns a missing browser into a failure.
"""

import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

sync_api = pytest.importorskip(
    "playwright.sync_api",
    reason="playwright not installed - render checks need: "
    "pip install playwright && python -m playwright install chromium",
)

REPO = Path(__file__).resolve().parents[1]
APP = REPO / "app" / "ui.py"

# --- restated brand contracts (brand/tokens.css) -------------------------
MONO = '"IBM Plex Mono", ui-monospace, "Cascadia Mono", monospace'
BODY = '"IBM Plex Sans", system-ui, -apple-system, sans-serif'
PAPER_50 = "rgb(253, 250, 244)"  # --paper-50: zebra table surface
PAPER_100 = "rgb(247, 241, 230)"  # --paper-100: app background
PAPER_200 = "rgb(240, 232, 217)"  # --paper-200: sidebar, table header
ARCHIVAL_100 = "rgb(220, 231, 225)"  # pass tint
OCHRE_100 = "rgb(240, 230, 208)"  # caution tint
OXBLOOD_100 = "rgb(243, 224, 226)"  # danger tint
OXBLOOD_600 = "rgb(140, 47, 57)"  # danger ink (stamps)

CHIP_TINTS = {
    "--pass": ARCHIVAL_100,
    "--caution": OCHRE_100,
    "--danger": OXBLOOD_100,
}

# react-aria ComboBox (verified in-browser, tests/test_render_browser.py):
# the selected claim ID lives in the combobox input, and the theme's mono
# rule is pointed at the same element.
SELECTBOX_TRIGGER = '[data-testid="stSelectbox"] input[role="combobox"]'
SELECTBOX_FIELD = '[data-testid="stSelectbox"] > div > div'
DROPDOWN = '[data-testid="stSelectboxVirtualDropdown"]'
NARRATIVE = '[data-testid="stMarkdownContainer"]:has(.mct-val)'


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="module")
def app_url():
    """The real app, served by streamlit exactly as a user would start it."""
    port = _free_port()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(APP),
            "--server.headless=true",
            "--server.address=127.0.0.1",
            f"--server.port={port}",
            "--browser.gatherUsageStats=false",
        ],
        cwd=REPO,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 90
    while True:
        try:
            with urllib.request.urlopen(url, timeout=2):
                break
        except Exception:
            if time.monotonic() > deadline:
                proc.kill()
                pytest.fail(f"streamlit did not come up on {url}")
            time.sleep(0.5)
    yield url
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="module")
def browser():
    pw = sync_api.sync_playwright().start()
    try:
        chromium = pw.chromium.launch()
    except Exception as exc:
        pw.stop()
        msg = "chromium unavailable - run: python -m playwright install chromium"
        if os.environ.get("MCT_REQUIRE_BROWSER") == "1":
            raise AssertionError(msg) from exc
        pytest.skip(msg)
    yield chromium
    chromium.close()
    pw.stop()


@pytest.fixture(scope="module")
def page(browser, app_url):
    tab = browser.new_page()
    tab.goto(app_url)
    tab.wait_for_selector('[data-testid="stSelectbox"]')  # claim panel up
    tab.wait_for_selector(".mct-table")  # bulk section below it
    yield tab
    tab.close()


def _style(tab, selector: str, css_property: str, index: int = 0) -> str:
    return (
        tab.locator(selector)
        .nth(index)
        .evaluate("(el, prop) => getComputedStyle(el)[prop]", css_property)
    )


def _trigger(tab):
    # The same selector the theme styles as the selectbox trigger; if the
    # DOM shape drifts, this locator failing IS the defect report.
    return tab.locator(SELECTBOX_TRIGGER).first


# --- tests ---------------------------------------------------------------
# Order matters: interactive tests run last and may leave state behind.


def test_app_surfaces_carry_the_paper_theme(page):
    assert _style(page, ".stApp", "backgroundColor") == PAPER_100
    assert _style(page, ".stApp", "fontFamily") == BODY
    assert _style(page, '[data-testid="stSidebar"]', "backgroundColor") == PAPER_200


def test_narrative_values_are_mono_and_prose_stays_sans(page):
    # The mono rule's spine: values a handler reads back are mono in the
    # narrative; the prose around them is not.
    assert page.locator(".mct-val").count() > 0
    assert _style(page, ".mct-val", "fontFamily") == MONO
    assert _style(page, ".mct-val", "fontVariantNumeric") == "tabular-nums"
    assert _style(page, NARRATIVE, "fontFamily") == BODY


def test_bulk_table_matches_the_brand_table_spec(page):
    # Brand table: sunken header, mono 13px tabular cells, zebra paper-50.
    assert page.locator(".mct-table tbody tr").count() == 38
    assert _style(page, ".mct-table td", "fontFamily") == MONO
    assert _style(page, ".mct-table td", "fontSize") == "13px"
    assert _style(page, ".mct-table td", "fontVariantNumeric") == "tabular-nums"
    assert _style(page, ".mct-table th", "fontFamily") == BODY
    assert _style(page, ".mct-table th", "textTransform") == "uppercase"
    assert _style(page, ".mct-table th", "backgroundColor") == PAPER_200
    odd = _style(page, ".mct-table tbody tr:nth-child(1) td", "backgroundColor")
    even = _style(page, ".mct-table tbody tr:nth-child(2) td", "backgroundColor")
    assert (odd, even) == ("rgba(0, 0, 0, 0)", PAPER_50)


def test_selectbox_field_and_trigger_are_styled(page):
    # Structure claims behind the theme's selectors: the field wrapper
    # exists inside stSelectbox and wears the surface color; the
    # combobox input carries the claim ID in mono (brand: IDs never sans).
    trigger = _trigger(page)
    assert trigger.count() > 0
    assert "CLM-" in trigger.input_value()  # the mono claim ID in the field
    assert _style(page, SELECTBOX_TRIGGER, "fontFamily") == MONO
    assert page.locator(SELECTBOX_FIELD).count() > 0
    assert _style(page, SELECTBOX_FIELD, "backgroundColor") == PAPER_50


def test_investigate_claim_renders_stamp_and_chip_tints(page):
    # CLM-007 is the engine's investigate case (restated ground truth).
    _trigger(page).click()
    page.locator(DROPDOWN).get_by_text("CLM-007").click()
    expect = sync_api.expect
    # The selection shows in the combobox's value attribute, not as text.
    expect(_trigger(page)).to_have_value(re.compile(r"CLM-007"))
    stamp = page.locator(".mct-stamp--danger")
    expect(stamp).to_be_visible()
    expect(stamp).to_contain_text("INVESTIGATE")
    assert _style(page, ".mct-stamp--danger", "color") == OXBLOOD_600
    chips = page.locator(".mct-chip")
    assert chips.count() >= 1
    for i in range(chips.count()):
        chip = chips.nth(i)
        classes = chip.get_attribute("class") or ""
        for chip_class, tint in CHIP_TINTS.items():
            if chip_class in classes:
                bg = chip.evaluate("(el) => getComputedStyle(el).backgroundColor")
                assert bg == tint


def test_open_dropdown_options_render_in_mono(page):
    # The round-4 fix's first rendered check: option rows (claim IDs)
    # inherit mono from the portaled container.
    _trigger(page).click()
    expect = sync_api.expect
    expect(page.locator(DROPDOWN)).to_be_visible(timeout=10_000)
    assert _style(page, DROPDOWN, "fontFamily") == MONO
    expect(page.locator(DROPDOWN)).to_contain_text("CLM-")
