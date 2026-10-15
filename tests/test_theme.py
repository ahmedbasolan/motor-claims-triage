"""Theme liveness: every element the theme styles must still exist.

A CSS rule targeting a data-testid (or data attribute) that no shipped
Streamlit bundle contains styles nothing - the dead stArrowTable rule
left the bulk table unstyled to the brand for an unknown period
(defect log, round 4). This test parses app/theme.py's CSS and checks
each data-testid, data attribute, and .st* class against the frontend
assets of the INSTALLED Streamlit, matched as whole quoted tokens (so
"stError" cannot pass on "stErrorBoundary" hits). An upstream
rename/removal - or an invented selector in our CSS - fails here
instead of silently unstyling the UI.
"""

import pathlib
import re

import streamlit

_THEME = pathlib.Path(__file__).resolve().parents[1] / "app" / "theme.py"
_ASSET_SUFFIXES = (".js", ".css", ".html", ".json")


def _bundle_corpus() -> str:
    root = pathlib.Path(streamlit.__file__).parent
    static = root / "static"
    search = static if static.exists() else root
    assets = [p for p in search.rglob("*") if p.suffix in _ASSET_SUFFIXES]
    assert assets, (
        f"no frontend assets found under {search} - streamlit's layout changed; "
        "update this test's asset discovery before trusting its verdicts"
    )
    return "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in assets)


def _bounded(corpus: str, token: str) -> bool:
    """True if the token occurs as a whole double-quoted or backticked string."""
    return bool(re.search(r'["`]' + re.escape(token) + r'["`]', corpus))


def test_theme_targets_exist_in_installed_streamlit():
    css = _THEME.read_text(encoding="utf-8")
    corpus = _bundle_corpus()

    testids = sorted(set(re.findall(r'data-testid=\\?"([^"\\]+)\\?"', css)))
    classes = sorted(set(re.findall(r"(?<![\w-])\.(st[A-Za-z][\w-]*)", css)))
    attrs = sorted(set(re.findall(r"\[(data-[\w-]+)=", css)) - {"data-testid"})
    assert testids and classes, "theme.py parse found no targets - this test is blind"

    dead_testids = [t for t in testids if not _bounded(corpus, t)]
    dead_classes = [c for c in classes if not _bounded(corpus, c)]
    dead_attrs = [a for a in attrs if not _bounded(corpus, a)]

    assert dead_testids == [], (
        f"theme.py styles data-testids missing from streamlit "
        f"{streamlit.__version__}: {dead_testids}"
    )
    assert dead_classes == [], (
        f"theme.py styles .st classes missing from streamlit "
        f"{streamlit.__version__}: {dead_classes}"
    )
    assert dead_attrs == [], (
        f"theme.py styles data attributes missing from streamlit "
        f"{streamlit.__version__}: {dead_attrs}"
    )
