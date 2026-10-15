"""Dossier theme for the Streamlit UI.

Loads the brand fonts and tokens (brand/tokens.css) and restyles Streamlit's
DOM to the brand book (brand/BRAND.md). Also exposes small HTML helpers for
the signature components: stamps, chips, fact grids, case notes, risk panels.

All dynamic strings passed to the HTML helpers are escaped here; prose
surfaces additionally wrap money, dates and identifiers in mono spans per the
brand book's mono rule ("IDs are never sans").
"""

from __future__ import annotations

import html
import re
from datetime import datetime
from pathlib import Path
from typing import Literal

import streamlit as st

Kind = Literal["pass", "caution", "danger", "info"]

_TOKENS_CSS_PATH = Path(__file__).resolve().parent.parent / "brand" / "tokens.css"

FONT_IMPORT = (
    "@import url('https://fonts.googleapis.com/css2?"
    "family=IBM+Plex+Mono:wght@400;500&"
    "family=IBM+Plex+Sans:wght@400;500;600&"
    "family=Source+Serif+4:ital,wght@0,600;0,700;1,600&display=swap');"
)

THEME_CSS = """
/* ── Reset to Dossier paper ─────────────────────────────────────── */
.stApp, [data-testid="stAppViewContainer"] {
  background: var(--color-bg-app);
}
.stApp {
  font-family: var(--font-body);
  font-size: 15px;
  color: var(--color-fg-default);
}
[data-testid="stHeader"] {
  background: transparent;
  border-bottom: 1px solid var(--color-border);
}
[data-testid="stMainBlockContainer"] {
  padding-top: var(--space-5);
  padding-bottom: var(--space-8);
}
[data-testid="stSidebar"] {
  background: var(--color-bg-sunken);
  border-right: 1px solid var(--color-border);
}

/* ── Typography ─────────────────────────────────────────────────── */
/* Out-specify Streamlit's own markdown heading rules. */
[data-testid="stMarkdownContainer"] h1,
[data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3,
[data-testid="stMarkdownContainer"] h4,
h1, h2, h3, h4 {
  font-family: var(--font-display);
  color: var(--color-fg-default);
  font-weight: 600;
  letter-spacing: -0.01em;
  line-height: 1.2;
}
[data-testid="stMarkdownContainer"] h1,
h1 { font-size: var(--text-3xl); }
[data-testid="stMarkdownContainer"] h2,
h2 { font-size: var(--text-xl); }
[data-testid="stMarkdownContainer"] h3,
h3 { font-size: var(--text-lg); }
.stApp p, .stApp li {
  color: var(--color-fg-default);
  font-size: var(--text-md);
  line-height: 1.5;
}
.stApp strong, .stApp b { font-weight: 600; }
code, pre, [data-testid="stCode"] {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
}

/* ── Sidebar brand + widget labels ──────────────────────────────── */
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] li {
  color: var(--color-fg-secondary);
}
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
[data-testid="stSidebar"] label,
p[data-testid="stWidgetLabel"] {
  font-family: var(--font-body);
  font-size: var(--text-2xs);
  font-weight: 600;
  letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase;
  color: var(--color-fg-muted);
}

/* ── Buttons ────────────────────────────────────────────────────── */
.stButton button,
[data-testid="baseButton-primary"],
[data-testid="baseButton-secondary"] {
  font-family: var(--font-body);
  font-size: var(--text-sm);
  font-weight: 600;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-strong);
  background: var(--color-bg-surface);
  color: var(--color-fg-default);
  transition: background var(--motion-fast) ease, border-color var(--motion-fast) ease;
}
.stButton button:hover,
[data-testid="baseButton-secondary"]:hover {
  background: var(--color-bg-sunken);
  border-color: var(--color-border-strong);
  color: var(--color-fg-default);
}
.stButton button:active,
[data-testid="baseButton-secondary"]:active {
  background: var(--color-paper-300, #e6dcc8);
}

/* ── Inputs / select ────────────────────────────────────────────── */
[data-testid="stSelectbox"] > div > div,
[data-testid="stSelectbox"] [data-baseweb="select"] > div,
[data-testid="stTextInput"] > div > div > input,
[data-testid="stNumberInput"] > div > div > input {
  background: var(--color-bg-surface);
  border-color: var(--color-border-strong);
  border-radius: var(--radius-sm);
  color: var(--color-fg-default);
  font-family: var(--font-body);
}
[data-testid="stSelectbox"] div[role="button"] {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
}

/* ── Alerts (tinted paper + left rule, no icon balloons) ────────── */
[data-testid="stAlert"],
[data-testid="stSuccess"],
[data-testid="stError"],
[data-testid="stWarning"],
[data-testid="stInfo"] {
  background: var(--color-bg-surface);
  border: none;
  border-left: 3px solid var(--color-primary);
  border-radius: var(--radius-sm);
  color: var(--color-fg-default);
}
[data-testid="stAlert"] > div > div > svg,
[data-testid="stSuccess"] svg,
[data-testid="stError"] svg,
[data-testid="stWarning"] svg,
[data-testid="stInfo"] svg {
  display: none;
}
[data-testid="stAlert"] p,
[data-testid="stSuccess"] p,
[data-testid="stError"] p,
[data-testid="stWarning"] p,
[data-testid="stInfo"] p {
  color: inherit;
  font-size: var(--text-sm);
}
[data-testid="stSuccess"],
[data-testid="stAlert"][data-kind="success"] {
  border-left-color: var(--color-pass);
  background: var(--color-pass-tint);
}
[data-testid="stSuccess"] p,
[data-testid="stAlert"][data-kind="success"] p { color: var(--color-pass-ink); }
[data-testid="stError"],
[data-testid="stAlert"][data-kind="error"] {
  border-left-color: var(--color-danger);
  background: var(--color-danger-tint);
}
[data-testid="stError"] p,
[data-testid="stAlert"][data-kind="error"] p { color: var(--color-danger-ink); }
[data-testid="stWarning"],
[data-testid="stAlert"][data-kind="warning"] {
  border-left-color: var(--color-caution);
  background: var(--color-caution-tint);
}
[data-testid="stWarning"] p,
[data-testid="stAlert"][data-kind="warning"] p { color: var(--color-caution-ink); }
[data-testid="stInfo"],
[data-testid="stAlert"][data-kind="info"] {
  border-left-color: var(--color-border-strong);
  background: var(--color-bg-surface);
}

/* ── Metrics ────────────────────────────────────────────────────── */
[data-testid="stMetricLabel"] {
  font-family: var(--font-body);
  font-size: var(--text-2xs);
  font-weight: 600;
  letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase;
  color: var(--color-fg-muted);
}
[data-testid="stMetricValue"] {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-weight: 500;
  color: var(--color-fg-default);
}

/* ── Data table (mct-table) ───────────────────────────────────────
   The dataframe grid draws its cells on a canvas - there is no DOM to
   style, and stArrowTable no longer exists in any Streamlit 1.64
   bundle - so tables render as in-brand HTML via theme.data_table():
   sunken header, mono 13px cells, zebra paper-50, horizontal hairlines
   only, no rounded corners, no vertical rules (brand/BRAND.md). */
.mct-table {
  width: 100%;
  border: 1px solid var(--color-border);
  border-radius: 0;
  border-collapse: collapse;
}
.mct-table th {
  background: var(--color-bg-sunken);
  color: var(--color-fg-secondary);
  font-family: var(--font-body);
  font-size: var(--text-2xs);
  font-weight: 600;
  letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase;
  border-bottom: 1px solid var(--color-border-strong);
  padding: var(--space-2) var(--space-3);
  text-align: left;
}
.mct-table td {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  font-variant-numeric: tabular-nums;
  color: var(--color-fg-default);
  border-bottom: 1px solid var(--color-border);
  padding: var(--space-2) var(--space-3);
}
.mct-table tbody tr:nth-child(even) td {
  background: var(--paper-50);
}

/* ── Expander / divider / spinner ───────────────────────────────── */
[data-testid="stExpander"] details {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}
[data-testid="stExpander"] summary {
  font-family: var(--font-body);
  font-weight: 600;
  font-size: var(--text-sm);
  color: var(--color-fg-default);
}
[data-testid="stDivider"] hr,
.stApp hr {
  border: none;
  border-top: 1px solid var(--color-border);
}
.stSpinner div {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--color-fg-muted);
  letter-spacing: 0.08em;
}

/* ── Focus ──────────────────────────────────────────────────────── */
:where(a, button, input, select, textarea, [tabindex]):focus-visible {
  outline: 2px solid var(--color-focus);
  outline-offset: 2px;
}

/* ── Custom components (mct-*) ──────────────────────────────────── */
.mct-eyebrow {
  font-family: var(--font-body);
  font-size: var(--text-2xs);
  font-weight: 600;
  letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase;
  color: var(--color-fg-muted);
  margin: 0 0 var(--space-2) 0;
}
.mct-rule {
  border: none;
  border-top: 1px solid var(--color-border);
  margin: var(--space-1) 0 var(--space-3) 0;
}
.mct-section { margin-top: var(--space-6); }
.mct-section:first-child { margin-top: 0; }

.mct-title {
  font-family: var(--font-display);
  font-weight: 700;
  font-size: var(--text-3xl);
  color: var(--color-fg-default);
  letter-spacing: -0.015em;
  line-height: 1.15;
  margin: 0 0 var(--space-1) 0;
}
.mct-wordmark {
  font-family: var(--font-display);
  font-weight: 700;
  font-size: var(--text-lg);
  color: var(--color-fg-default);
  letter-spacing: -0.01em;
  margin: 0 0 2px 0;
}
.mct-tag {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--color-fg-muted);
  margin: 0 0 var(--space-4) 0;
  white-space: nowrap;
}

/* Stamp — signature component. Verdicts and coverage outcomes only. */
.mct-stamp {
  display: inline-block;
  font-family: var(--font-body);
  font-weight: 600;
  font-size: var(--text-xl);
  letter-spacing: var(--tracking-stamp);
  text-transform: uppercase;
  line-height: 1.2;
  padding: var(--space-2) var(--space-4);
  border: var(--border-stamp) solid currentColor;
  border-radius: 0;
  transform: rotate(-1.2deg);
  margin: var(--space-2) 0 var(--space-3) 0;
}
.mct-stamp--compact {
  font-size: var(--text-sm);
  padding: 4px var(--space-3);
  margin: 0 0 var(--space-2) 0;
}
.mct-stamp--pass { color: var(--color-pass); }
.mct-stamp--caution { color: var(--color-caution-ink); }
.mct-stamp--danger { color: var(--color-danger); }

/* Chip — risk levels, small status tags */
.mct-chip {
  display: inline-block;
  font-family: var(--font-body);
  font-size: var(--text-2xs);
  font-weight: 600;
  letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase;
  padding: 3px var(--space-2);
  border-radius: var(--radius-sm);
  border: 1px solid transparent;
  white-space: nowrap;
}
.mct-chip--pass {
  background: var(--color-pass-tint);
  color: var(--color-pass-ink);
  border-color: color-mix(in srgb, var(--color-pass) 30%, transparent);
}
.mct-chip--caution {
  background: var(--color-caution-tint);
  color: var(--color-caution-ink);
  border-color: color-mix(in srgb, var(--color-caution) 35%, transparent);
}
.mct-chip--danger {
  background: var(--color-danger-tint);
  color: var(--color-danger-ink);
  border-color: color-mix(in srgb, var(--color-danger) 30%, transparent);
}

/* Fact grid — label/value pairs, values in mono */
.mct-facts {
  display: grid;
  grid-template-columns: minmax(110px, max-content) 1fr;
  gap: var(--space-2) var(--space-5);
  margin: 0;
}
.mct-facts dt {
  font-family: var(--font-body);
  font-size: var(--text-2xs);
  font-weight: 600;
  letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase;
  color: var(--color-fg-muted);
  padding-top: 2px;
}
.mct-facts dd {
  margin: 0;
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  font-variant-numeric: tabular-nums;
  color: var(--color-fg-default);
}

/* Card */
.mct-card {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-paper);
  padding: var(--space-4);
}
.mct-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}
.mct-card__title {
  font-family: var(--font-body);
  font-size: var(--text-2xs);
  font-weight: 600;
  letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase;
  color: var(--color-fg-muted);
}
.mct-factors {
  margin: 0;
  padding: 0 0 0 var(--space-4);
  color: var(--color-fg-secondary);
  font-size: var(--text-sm);
  line-height: 1.55;
}
.mct-factors li { margin-bottom: var(--space-1); color: var(--color-fg-secondary); }
.mct-factors li::marker { color: var(--color-ink-300, #b5ab99); }
.mct-empty {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--color-fg-muted);
  margin: 0;
}

/* Inline values: money, dates and identifiers inside prose stay mono
   (brand book's mono rule) while the prose around them stays sans. */
.mct-val {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}

/* Case note — narrative / descriptions */
.mct-note {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border);
  border-left: 3px solid var(--color-primary);
  border-radius: var(--radius-sm);
  padding: var(--space-3) var(--space-4);
  font-family: var(--font-body);
  font-size: var(--text-md);
  line-height: 1.65;
  color: var(--color-fg-secondary);
}

/* Inline alert (HTML twin of st.info/error, kept in-brand) */
.mct-alert {
  border-radius: var(--radius-sm);
  border-left: 3px solid var(--color-border-strong);
  background: var(--color-bg-surface);
  padding: var(--space-3) var(--space-4);
  font-size: var(--text-sm);
  line-height: 1.55;
  color: var(--color-fg-default);
  margin-bottom: var(--space-2);
}
.mct-alert--pass {
  border-left-color: var(--color-pass);
  background: var(--color-pass-tint);
  color: var(--color-pass-ink);
}
.mct-alert--caution {
  border-left-color: var(--color-caution);
  background: var(--color-caution-tint);
  color: var(--color-caution-ink);
}
.mct-alert--danger {
  border-left-color: var(--color-danger);
  background: var(--color-danger-tint);
  color: var(--color-danger-ink);
}

/* ── Tighten Streamlit's default block rhythm ───────────────────── */
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] {
  row-gap: 0.4rem;
}
[data-testid="stSidebar"] .block-container > [data-testid="stVerticalBlock"] {
  row-gap: 0.75rem;
}
[data-testid="stMarkdownContainer"] p {
  margin: 0 0 0.5rem;
}
[data-testid="stMarkdownContainer"] p:last-child {
  margin-bottom: 0;
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    transition-duration: 0.01ms !important;
    animation-duration: 0.01ms !important;
  }
}
"""


def inject_theme() -> None:
    """Inject fonts + Dossier tokens + CSS. Call once, after set_page_config."""
    tokens = _TOKENS_CSS_PATH.read_text(encoding="utf-8")
    st.markdown(f"<style>{FONT_IMPORT}\n{tokens}\n{THEME_CSS}</style>", unsafe_allow_html=True)


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


# The brand book's mono rule (brand/BRAND.md, "the spine of the system"):
# values a handler reads back on a call — money, dates, identifiers — are mono
# wherever they appear, while prose itself is never mono. Prose surfaces wrap
# values individually at render time via inline_values().
_VALUE_RE = re.compile(
    r"AED \d{1,3}(?:,\d{3})*"  # money: AED 62,000
    r"|\b\d{4}-\d{2}-\d{2}\b"  # ISO dates: 2024-05-15
    r"|\b\d{1,2} [A-Z][a-z]{2} \d{4}\b"  # text dates: 15 May 2024
    r"|\b[A-Z]{3}-\d{4}-\d{3}\b"  # policy numbers: POL-2024-001
    r"|\b[A-Z]{1,3}-\d{3,6}\b"  # claim IDs / registrations: CLM-001, A-12345
)


def inline_values(text: object) -> str:
    """Escape text, then wrap each value occurrence in a mono ``.mct-val`` span."""
    escaped = _esc(text)
    return _VALUE_RE.sub(lambda m: f'<span class="mct-val">{m.group(0)}</span>', escaped)


# ── Formatting ────────────────────────────────────────────────────────


def aed(amount: float) -> str:
    return f"AED {amount:,.0f}"


def fmt_dt(value: datetime) -> str:
    return value.strftime("%d %b %Y, %H:%M")


# ── HTML helpers ──────────────────────────────────────────────────────


def page_header(title: str, subtitle: str | None = None) -> str:
    tag = f'<p class="mct-tag">{_esc(subtitle)}</p>' if subtitle else ""
    return f'<p class="mct-eyebrow">Case file</p><h1 class="mct-title">{_esc(title)}</h1>{tag}'


def wordmark(tagline: str = "CBUAE-aligned prototype") -> str:
    return f'<p class="mct-wordmark">Motor Claims Triage</p><p class="mct-tag">{_esc(tagline)}</p>'


def section_label(text: str) -> str:
    return f'<p class="mct-eyebrow">{_esc(text)}</p><hr class="mct-rule">'


def stamp(text: str, kind: Kind, compact: bool = False) -> str:
    compact_cls = " mct-stamp--compact" if compact else ""
    return f'<div><span class="mct-stamp mct-stamp--{kind}{compact_cls}">{_esc(text)}</span></div>'


def chip(text: str, kind: Kind) -> str:
    return f'<span class="mct-chip mct-chip--{kind}">{_esc(text)}</span>'


def fact_grid(items: list[tuple[str, str]]) -> str:
    rows = "".join(f"<dt>{_esc(label)}</dt><dd>{_esc(value)}</dd>" for label, value in items)
    return f'<dl class="mct-facts">{rows}</dl>'


def data_table(rows: list[dict[str, object]]) -> str:
    """In-brand data table: sunken header, mono cells, zebra, hairlines only.

    Rendered as HTML because the dataframe grid draws its cells on a canvas
    (no DOM to style), so st.dataframe cannot be brought to the brand. Cell
    contents are escaped; column order follows the first row's keys.
    """
    if not rows:
        return '<p class="mct-empty">No rows.</p>'
    headers = list(rows[0])
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{_esc(row.get(h, ''))}</td>" for h in headers) + "</tr>"
        for row in rows
    )
    return f'<table class="mct-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def note_block(text: str) -> str:
    return f'<div class="mct-note">{inline_values(text)}</div>'


def alert_html(text: str, kind: Kind = "info") -> str:
    cls = "" if kind == "info" else f" mct-alert--{kind}"
    return f'<div class="mct-alert{cls}">{inline_values(text)}</div>'


def risk_panel(title: str, level_label: str, kind: Kind, factors: list[str]) -> str:
    if factors:
        items = "".join(f"<li>{inline_values(f)}</li>" for f in factors)
        body = f'<ul class="mct-factors">{items}</ul>'
    else:
        body = '<p class="mct-empty">No factors recorded.</p>'
    return (
        '<div class="mct-card">'
        f'<div class="mct-card__head"><span class="mct-card__title">{_esc(title)}</span>'
        f"{chip(level_label, kind)}</div>"
        f"{body}</div>"
    )
