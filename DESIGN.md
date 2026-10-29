# ClearSwath design

The app answers one question: can this field be sprayed, and where? The answer comes with the label sentence behind
it. The design follows from that. The decision is the largest thing on the screen, the label's own words are the
one distinctive element, and everything else stays quiet.

## Identity

The pesticide label is the source of truth, so the label's look is the visual idea. Pesticide labels are dense,
condensed, black-on-white documents with page numbers. Every reason the app gives is set as an excerpt clipped
from the label: condensed type, a hairline rule, the page number. Nothing else on the screen uses that treatment,
so a judge can tell at a glance which words came from the label and which from the app.

## Colour

| Token | Hex | Use |
|---|---|---|
| `--ink` | `#1E2B24` | Text, primary buttons, the label-excerpt rule |
| `--muted` | `#5B6760` | Secondary text (contrast 5.9:1 on white) |
| `--rule` | `#D6DBD6` | Dividers, input borders |
| `--page` | `#F2F4F1` | Page background behind the panel and map |
| `--panel` | `#FFFFFF` | The side panel |
| `--clear` | `#2E7D32` | No conflicts in checked rules |
| `--adjust` | `#9A6200` | Adjust (5.1:1 on white, so it can carry text) |
| `--stop` | `#B42318` | Do not spray, errors, missing record fields |
| `--spray` | `#C4127A` | Cells the weed map sprays. Magenta never occurs in a field, so it can't blend into crop, rangeland or soil |
| `--held` | `#37474F` | Weed cells held back by a buffer |
| `--water` | `#2B83BA` | Water |

The status colours appear only as a small square beside the decision and on the map. They are never used for
decoration, and never for whole blocks.

## Type

- **IBM Plex Sans** (400, 500, 600) for everything. It's an industrial, technical face that fits a document read in a
  truck cab, with tabular figures for acres and distances.
- **IBM Plex Sans Condensed** (400) only for label excerpts.
- Scale: 13 / 15 / 18 / 28 px. The decision word is 28 px semibold. Headings are 15 px semibold in sentence case:
  no all-caps or letter-spaced labels.
- Numbers use `font-variant-numeric: tabular-nums` so acres line up.

## Layout

```
┌───────────────────────────── header: ClearSwath · Plan a spray | Check a photo ─┐
├──────────────────────┬──────────────────────────────────────────────────────────┤
│ Field and label  ▾   │                                                          │
│ Adjust               │                                                          │
│ 23.6 of 24.1 ac can  │                        map                               │
│ be sprayed           │                                                          │
│ Not checked: …       │                                              ┌────────┐ │
│ Check before spraying│                                              │ legend │ │
│ Why  (label excerpts)│                                              └────────┘ │
│ Spray map            │                                                          │
│ Files for the sprayer│                                                          │
│ Application record   │                                                          │
└──────────────────────┴──────────────────────────────────────────────────────────┘
```

- A 400 px panel on the left, the map filling the rest. Below 800 px the map sits on top at 55% of the screen
  height, with the panel under it.
- Everything is left-aligned. Sections are divided by space and one hairline, not by boxes. The only box is
  "Check before spraying", which has an amber left rule, because it's the one thing the applicator must not miss.
- The setup form folds away once a plan is shown, and reopens from its heading.
- One corner radius (4 px) on inputs and buttons. No shadows except the map legend's, which sits over imagery.

## Map

- Sprayable zone: a green outline with an 8% fill, so the imagery stays readable.
- No-spray area: red outline, 25% fill.
- Spot spray: magenta cells at 55%. Held back: slate at 60%. Water: blue.
- A legend names every layer in plain words and toggles it. The map library's default layer control is not used.

## Motion

The decision fades in once (200 ms) when a plan arrives. Nothing else moves on its own, and
`prefers-reduced-motion` turns that fade off.

## Words

- Outcomes: **No conflicts in checked rules**, **Adjust**, **Do not spray**. Never "legal", "compliant" or "safe".
- Buttons say what happens: "Plan the spray", "Try the demo", "Find weeds", "Fill the record".
- Under every decision: "Not checked: weather and inversions, runoff points, your licence, field conditions."
- Errors say what went wrong and what to do, without apologising.

## Build

Components are Astryx, themed from these tokens in `web-app/src/theme.ts`. Our own styles use StyleX, with the same
palette in `web-app/src/tokens.stylex.ts`.
