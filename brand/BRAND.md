# Motor Claims Triage — Brand Book

**Codename: Dossier.** v1.0.

A claims triage copilot for UAE motor insurance. The people using it are handlers
and SIU investigators under time pressure, making decisions a regulator can
audit later. The interface must feel like a case file on a desk: warm, orderly,
and serious — not like a SaaS dashboard trying to impress a demo audience.

---

## 1. Essence

**A working document, not an app.**

The visual metaphor is a physical claims dossier: warm paper stock, black ink,
oxblood rubber stamps, typewriter figures for anything a handler would read
aloud in a meeting. Every screen should look like it could be printed, signed,
and filed.

Three words to test every decision against: **plain, exact, accountable.**

## 2. Voice & tone

| Principle | Do | Don't |
|---|---|---|
| State the reason | "Investigate — policy held 18 days at loss date, claim is 14× excess" | "High risk detected!" |
| No hype | "Coverage clear" | "Great news! You're covered 🎉" |
| Numbers exact | "AED 62,400" | "AED 62k" |
| Dates unambiguous | "18 Jan 2026, 14:32" | "01/18/26" |
| Hedging honest | "Rule skipped — policy record not supplied" | Silently guessing (this caused a real bug; see README) |
| Verbs first in labels | "Review", "Escalate", "Open file" | "File Review Options" |

UI copy is written for someone who will paste it into a handler note later.
If a sentence would embarrass the writer in a compliance review, rewrite it.

## 3. Color

Full token tables live in `brand/tokens.json` and `brand/tokens.css`.
Summary of the load-bearing choices:

| Role | Hex | Notes |
|---|---|---|
| App background | `#F7F1E6` | Warm paper. Never `#FFFFFF`, never cool grey |
| Surface | `#FDFAF4` | Cards sit *on* the paper |
| Ink | `#1F1B16` | Warm near-black. Never `#000000` |
| Primary (archival green) | `#2C4F43` | Buttons, links, pass-state ink |
| Investigate (oxblood) | `#8C2F39` | Rubber-stamp red. Reserve for verdicts and hard fails |
| Standard review (ochre) | `#9A7B3F` | Text on tints uses `#7A5E2A` for contrast |
| Border hairline | `#E3D8C4` | One weight, everywhere |

Rules:

- **Status colors are semantic, never decorative.** Oxblood appears on a screen
  only when something is actually wrong. No red hover states, no red accents.
- **Three verdicts, three inks, fixed forever:** green = pass/fast-track,
  ochre = standard review, oxblood = investigate. Handlers learn this in a day;
  never reassign.
- **Tints over solids** for badges and alerts: `*-tint` background, `*-ink` text.
- Contrast floor: 4.5:1 body text, 3:1 large text and UI borders. Ochre `600`
  fails body text on paper — that is why `ochre-700` exists. Use it.

## 4. Typography

Three families, three jobs, no exceptions:

| Job | Family | Rules |
|---|---|---|
| Headings, wordmark, editorial | **Source Serif 4** (600/700) | Sentence case. Never all-caps display type outside stamps |
| UI body | **IBM Plex Sans** (400/500/600) | 15px default. 13px secondary |
| Data | **IBM Plex Mono** (400/500) | Claim IDs, policy numbers, registrations, AED amounts, dates, scores, ages |

**The mono rule is the spine of the system.** If a handler would read a value
back on a call — money, identifiers, dates — it is mono with tabular figures.
Prose is never mono. IDs are never sans.

Scale (dense dashboard, 4px grid): 11 / 12 / 13 / 15 / 17 / 21 / 28 / 36.
Section labels are 11–12px small-caps with `0.14em` tracking, always followed
by a hairline rule.

## 5. Geometry & spacing

- **4px spacing grid.** Steps: 4, 8, 12, 16, 24, 32, 48, 64.
- **Radius ceiling: 3px.** Structure is square-ish. Chips and inputs 2px.
  Nothing is a pill. Nothing has a 12px corner.
- **Borders do the separating**, not shadows. The only permitted shadow is
  `--shadow-paper` (warm, 1–2px). No elevation stacks, no colored glows.
- Tables have no rounded corners and no vertical rules — horizontal hairlines
  and a sunken header only.

## 6. The Stamp (signature component)

The one element people will remember. Reserved exclusively for:

1. The triage verdict (`FAST-TRACK` / `STANDARD REVIEW` / `INVESTIGATE`)
2. Hard coverage outcomes (`COVERED` / `EXCLUSION TRIGGERED`)

Spec (`component.stamp` in tokens.json):

- Square corners (radius 0), `1.75px` solid border in the status ink
- Uppercase, `0.16em` tracking, IBM Plex Sans 600, 21px (15–17px when compact)
- Rotated **−1.2deg** — enough to read as hand-stamped, not enough to read as broken
- Status ink for text and border; background transparent on paper, tint on cards
- One stamp per region. Never stack two stamps. Never stamp a decorative label.

If a new screen wants a stamp for emphasis — it doesn't get one. Verdicts and
coverage only.

## 7. Components (quick specs)

| Component | Spec |
|---|---|
| Button (primary) | Archival fill, warm-white text, 3px radius, 16×8 padding, hover `archival-500`, 120ms |
| Button (secondary) | Paper surface, hairline border, ink text; hover sunken paper |
| Chip (risk level) | Tinted bg + matching `*-ink` text, 11px small-caps tracked, 2px radius |
| Alert / note | Tinted paper bg, 3px left rule in status ink, no icon balloons, 12×16 padding |
| Card | Surface bg, hairline border, 3px radius, `--shadow-paper` |
| Input / select | Surface bg, `paper-300` border, 2px radius; focus ring 2px archival |
| Table | Sunken header, mono cells at 13px, zebra `paper-50`, horizontal hairlines only |
| Fact row (label/value) | Label: 11px small-caps tracked, muted ink. Value: mono 13–15px ink |

## 8. Motion

Restrained on purpose — this is a decision tool, not a landing page.

- State changes only: 120–180ms, `ease`. Color and opacity, never movement
  that shifts layout.
- No scroll reveals, no staggered entrances, no parallax, no spinners that
  perform. A loading state is a muted mono line: `triaging…`
- `prefers-reduced-motion: reduce` disables even the 120ms transitions.

## 9. Accessibility

- Focus rings visible, 2px archival, 2px offset — on every interactive element.
- Status is never color-alone: verdicts are words in stamps, risk levels are
  words in chips. Color reinforces; it never carries meaning by itself.
- Body text ≥ 4.5:1; borders and large text ≥ 3:1.
- Touch targets ≥ 44px even where the glyph is smaller.
- Full keyboard operability; Streamlit's default order is preserved, not broken
  by custom HTML (custom HTML here is display-only — no interactive elements
  hidden inside `unsafe_allow_html` blocks).

## 10. Anti-patterns (the anti-slop list)

Hard bans. A PR containing any of these fails review:

1. **Gradients.** Any. Especially purple/blue/indigo. No exceptions for heroes.
2. **Pure `#000000` or `#FFFFFF`.** Warm ink and warm paper only.
3. **Inter, Roboto, Segoe UI, default system sans for headings.** Headings are
   Source Serif 4. Body is IBM Plex Sans. That's the list.
4. **Emoji as icons or status.** 🚨 ✅ ⚠️ 🎉 are banned in UI chrome. The app
   favicon is an SVG mark, not a car emoji.
5. **Neon or traffic-light status colors.** No `#22C55E`, no `#EF4444`, no
   `#F59E0B`. The status inks are archival, ochre, oxblood.
6. **Glassmorphism, blur, translucent floating panels.** Paper is opaque.
7. **Border-radius > 3px.** No pills, no soft cards, no "friendly" rounding.
8. **Drop shadows with cool/colored tint, or multi-layer elevation.**
   `--shadow-paper` is the only shadow.
9. **Raw hex or raw font names in app code.** Tokens only. If a value isn't in
   `tokens.css`, add it there first.
10. **Marketing language.** No "smart", "powerful", "AI-driven", "seamless",
    "unlock". The README already calls the thresholds unvalidated guesses;
    the UI must not sound more certain than the engine is.
11. **Stock illustration, 3D blobs, characters, abstract hero art.** The
    interface's own data — stamps, tables, figures — is the imagery.
12. **Dark mode, for now.** Dossier is a paper system. A dark theme is a
    different brand book, not a palette swap. Deferred until there is a real
    night-shift use case.

## 11. Assets

- **Wordmark:** "Motor Claims Triage" set in Source Serif 4 Semibold, ink.
  Companion tag in IBM Plex Mono 11px tracked: `CBUAE-ALIGNED PROTOTYPE`.
  No lockup graphics, no swooshes.
- **Mark:** `brand/mark.svg` — oxblood stamp square with serif M. Used as
  favicon and empty-state mark only. Not placed next to every heading.
- **Fonts:** loaded from Google Fonts in `app/theme.py`:
  `Source Serif 4` (600, 700 + italic 600), `IBM Plex Sans` (400, 500, 600),
  `IBM Plex Mono` (400, 500).

## 12. File map

```
brand/
├── BRAND.md      # this book
├── tokens.json   # three-layer tokens (source of truth)
├── tokens.css    # CSS variables (generated from / kept in sync with tokens.json)
└── mark.svg      # stamp mark
```

Consumed by `app/theme.py` (Streamlit CSS + component helpers) and
`.streamlit/config.toml` (base theme). Changes to color or type go into the
token files first, then flow to the app — never the reverse.
