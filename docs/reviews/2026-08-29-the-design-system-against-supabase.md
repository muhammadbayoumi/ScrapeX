# The design system, measured against Supabase's — 2026-08-29

**Snapshot at `ef86a19`.** Every citation below was checked against that commit, not
against `HEAD`. Supabase's side was read from `github.com/supabase/supabase` at `master`,
sparse-checked-out to `apps/design-system`, `packages/ui` and `packages/ui-patterns` — the
source, not the website, because the website publishes token names without values and the
source publishes both.

He asked for it as [REQ-49](../REQUESTS.md#req-49--review-the-design-system-against-supabases),
and approved six of the twenty-six axes the scoping pass produced. This reports those six.

| axis | what it measured |
|---|---|
| A1 | token vocabulary, values, provenance |
| A2 | non-colour scales, and the literals that bypass them |
| A3 | the theming cascade, in a browser, across all eight shipped states |
| B1 | component coverage, atoms and fragments |
| E3 | what the guards actually measure |
| E4 | what the registers claim versus what is true |

**Approach (C6):** measurement first, adversarial verification second. Every axis was
measured, then handed to a second pass whose instruction was to *refute* it and whose
default on an unreproducible number was REFUTED. **Twenty-one findings did not survive**,
including three the first pass had led with. That list is section 5, and it is the most
useful section here.

---

## The verdict

**`R-74` holds in the built product, and is enforced by almost nothing.**

Measured in Chromium 149 across 8 shipped states by 118 root custom properties: 62
properties move and every one is a colour. But that conformance rests on one unasserted
statement — the allowlist loop at `design/appearance.js:347` — whose only guard is the
substring assertion at `tests/test_vendor.py:289`, and **`clearTheme` at
`design/appearance.js:310` satisfies that substring on its own.** Mutation testing on a
byte-verified mirror put `--fs`, `--font-body` and `--lh` into a palette and 11 of the 13
forbidden families into a surface stylesheet, and **91 static guards and 218 browser tests
stayed green.** The architecture `R-74` abolished is reachable today.

**The colour mathematics is excellent and the bookkeeping around it is not.** Fifteen
values are byte-exact against Supabase's published literals, nineteen more reproduce their
OKLCH expressions, and the 102-assertion contrast gate has no Supabase counterpart at all.
Against that: sixteen comments and documents argue from something untrue, twelve
declarations reference properties nothing declares, and one of the four colour choices
`R-74` names by name does not reach the user in half its states.

**The largest product-level gap is not a token.** On a warehouse admin tool the table is
the one component the shared layer does not touch: `design/components.css` contributes a
single table rule, a sibling margin at `design/components.css:1351`, against Supabase's
nine sub-parts.

---

## 1 · Defects

**D-01 · "Device colours" paints Supabase's own accent in dark mode.**
`design/tokens.css:302` wraps the device block in `@supports (color: AccentColor)`, which
contributes no specificity. The selector is therefore `(0,2,0)` — the same as the two dark
blocks that come *after* it and redeclare all seven of its properties. Source order
decides, and the dark blocks win. A user on a dark OS who picks Device colours gets
`#3ecf8e` for every accent, focus ring, button and switch track, while the panel's status
text reports the choice it is not painting. Proven by counterfactual, not inferred.
**One of `R-74`'s four named colour choices, unreachable in half its states.** Filed as
`OP-101`.

**D-02 · `R-74` is guarded by a substring that a different function satisfies.** Above.
Filed as `OP-102`.

**D-03 · `--sticky-tabs` is read nine times and declared nowhere.** Nine references across
four stylesheets, every one inside `calc()` and none with a fallback, so the whole
declaration is invalid at computed-value time and `top` falls back to `auto`. **The
settings sidebar and the exports sidebar are `position: sticky` and never stick.** Two
data-workspace popovers lose their offset with them. Filed as `OP-103`.

**D-04 · A palette can ship text at 1.00:1 with every test green.** The contrast
parametrize derives its *palette* list from the registry but its *token pairs* are still
hand-written. Setting `brand`'s `chip`, `surfaceSubtle` and `surfaceRaised` each to that
palette's own `--text` passes 91 static guards and all 218 browser tests. A quarter of what
a palette controls carries text and is never measured. Filed as `OP-104`.

**D-05 / D-06 · Three more undeclared properties, all silent.** `--control-active`
(`design/components.css:1530`) so a pressed split-button option paints no background;
`--fg` in the extension, a typo for `--text`, so a hover changes nothing but the underline;
`--green` in the console, so a completed build step loses its colour. `background` and
`border-*-color` are not inherited, so these compute to nothing rather than erroring.
Filed with D-03 as `OP-103`.

**D-07 · Three surface tokens are Supabase alpha tokens flattened against the wrong
plate.** `--surface-subtle`, `--chip` and `--line` are exact over `--background` and wrong
over `--card` and `--popover` — by 2/255 in light and (5,6,6) per channel in dark. That is
where borders and chips actually sit. This is OD-05, not a defect to fix in passing.

**D-08 · The operating system's Increase-contrast setting reaches one of the four colour
choices.** `apply()` writes the 36 theme properties as **inline style**, which outranks the
stylesheet rule implementing `prefers-contrast: more`. Silent in both directions: the OS
setting is on, the rule is present, and no test reads it. Filed as `OP-105`.

**D-09 · `.banner` has no neutral default.** `design/components.css:365` paints
`--amber-weak`, so an untyped banner reads as a warning. Supabase's untyped `Alert` is
neutral. Five untyped sites exist; four are not warnings, and one is the gallery's own
example labelled "a statement of fact". Filed as `OP-106`.

**D-10 · `device` has zero contrast coverage.** The parametrize iterates registered
palettes and `device` is removed as a palette entirely, so it can never appear. Run by
hand, device-light fails two of the seventeen assertions at 4.21:1. Filed with D-04 as
`OP-104`.

**D-11 · The catalogue's sprite check is a gate, not an assertion.** Renaming one comment
marker disables it, and the regeneration tool then reports the catalogue current forever.
`docs/UI-KIT.md` calls the gallery "the catalogue that cannot go stale". Filed as `OP-107`.

**D-12 · A colour baked into a shipped SVG is invisible to every guard.** The
colour-literal guard's suffix filter has no `.svg`. An edit made at source and synced to
both copies — the way anyone would actually introduce one — passes everything. Filed with
D-11 as `OP-107`.

**D-13 · No Supabase attribution anywhere.** Their root is Apache-2.0 (`Copyright 2024
Supabase`) and `packages/ui`, the package the values came from, declares MIT. `design/`
carries no notice of either. The same repository discharges the identical obligation three
times over for a smaller borrowing from Google. Filed as `OP-108`.

**D-14 · The two documents that govern the design system are guarded by nothing.** Neither
`docs/DESIGN-SYSTEM.md` nor `docs/UI-KIT.md` is in the citation guard's `DOCUMENTS`, and
adding them today would change no verdict, because neither contains a citation of the shape
the guard can see. Four live stale facts in them survived because of it. Filed as `OP-109`.

**D-15 · The side rail and `--z-modal` are both 30.** Recorded in a comment, resolved
nowhere; a modal and a persistent nav rail share a stacking band and source order decides.
The wider shape, comments stripped: **38 bare numeric `z-index` declarations against 6
tokenised**, values sprawling from 0 to 10020, and **29 of the 38 sitting below the scale's
floor** of `--z-sticky: 10` — which is itself dead. Those 29 are local stacking, not
bypasses. Filed as `OP-110`.

**D-16 · `.code` renders three properties differently on the two surfaces** under one class
name, with no override intent declared. Recorded here; not filed.

**D-17 · The device tonal bases have no guard, and one has already drifted.** The comment
claimed `tests/test_vendor.py` compares them against `:root`; it compares nine token
*names* and two substrings and no literal at all. Measured: the light `--control-hover`
base is `#f3f3f3` (`--chip`) where `:root` declares `var(--surface-subtle)` = `#f6f6f6`.
**The drift the comment claimed to prevent is present in the file the comment is in.**
The comment is corrected in this pull request; the drift is filed as `OP-109`.

---

## 2 · Divergences that should STAND

Supabase publishes nothing on any of these. They are additions above the baseline, and
they need a recorded rationale rather than a fix.

- **Contrast.** No numeric target exists anywhere in their 101 authored `.mdx` files —
  three qualitative claims only. This repository runs a real gate over every registered
  palette and both schemes, and overrode four Supabase values to meet it.
- **Accessibility.** `aria-live` / `role=status` 89 here against 3 there; reduced-motion
  blocks 14 against 3; a `forced-colors` block here against none there; a
  `prefers-contrast` accommodation against none.
- **Bidirectionality.** 200 logical directional declarations against 21 physical here — a
  9.5:1 ratio. Theirs is 279 physical against 6 logical, the inverse, and their system
  carries an explicit LTR lock. **This repository renders Arabic data inside English
  chrome, so this is the axis where it must diverge, and it already has.** The 21
  remaining physical declarations are the finish line, and five of them are defensible.
- **Checkboxes and radios follow the palette** through one declaration,
  `design/components.css:22`. `R-74` conformance achieved more cheaply than Supabase
  achieves it — not a gap.
- **Control heights** do not intersect their scale at all, because the panel runs a 48px
  Android touch floor. Deliberate; sanction it rather than close it (OD-09).

Two that should stand but be recorded as **ours rather than theirs**: the two easing curves
(neither appears in their source) and the `md` type rung, which shifts every name above it
one place below theirs — a trap for any port, and not worth renumbering across 19
stylesheets.

---

## 3 · Absences

Table primitive · floating-panel primitive (popover / dropdown / tooltip / menu) · a usable
empty state · the four status-border tokens · border-width tokens · fourteen of their 34
semantic roles, of which `--info`, `--field` and `--control-raised` are load-bearing · a
loading vocabulary · `font-synthesis-weight: none` and the mono-context weight reset · a
breakpoint vocabulary, noting that they publish none either.

Component coverage, counted from their source rather than their website: **12 of 28 atoms
present in any form, 4 first-class, 0 at full parity; 3 of 23 fragments.** Sixteen atoms
have no ScrapeX selector of any kind.

---

## 4 · False premises

The most dangerous category, because the next session will argue from them.

**Corrected in this pull request**, all in `design/tokens.css`, all comments — **no value
moved**:

1. `--amber` — the comment said hue and chroma held and lightness moved. The opposite:
   lightness held, the target was 27.6% outside sRGB, and the shipped hex is a naive clip
   that lost 9.5 degrees of hue and 16.7% of chroma.
2. `--line-strong` — "1.57:1 on their own `--card`" measured the `--background` composite
   against `--card`. And the replacement is not derived: `#8f8f8f` is their own
   `gray-light-900`. Sixteen values are PUBLISHED, not thirteen.
3. "`shadow-none` appears in more of their files than `shadow-md`" — 7 files against 11.
4. "SEVEN of the eight steps agreed" listed six numbers, and was silently untrue of the
   name-to-value mapping.
5. "There is NO BOLD anywhere in their system" — true of their component library, false of
   their repository, which carries 11 `font-bold` and 2 `font-extrabold`.
6. "Their vocabulary is 100/150/200/250/300ms and exactly TWO curves" — `duration-250` is
   used zero times, their most-used duration (200ms, 14 uses) has no token here, and
   neither curve is theirs.
7. The device block's claim that a test compares its bases against `:root`. See D-17.

**Corrected in the registers by this pull request:** `docs/STATE.md`'s "no PR yet" and its
"playwright is not installed on this machine"; `docs/LESSONS.md`'s citation of a guard that
has never existed and of an inverted test name; `docs/REQUESTS.md`'s two-palette test name;
`docs/DESIGN-SYSTEM.md`'s licence path, `.source-row` and icon markup; `docs/BACKLOG.md`'s
"9 non-generated stylesheets", which is 19.

**Left standing deliberately:** the docstring at
`tests/test_a_palette_may_change_nothing_but_colour.py:10` says `themeFor` dashes every key
into a custom property, so a `radius` key becomes a real `--radius`. **Measured false** —
`apply()` writes only the 36 allowlisted names and drops the rest. The docstring justifies
the shape rule with a mechanism the allowlist already prevents. Correcting it is entangled
with `OP-102`'s fix and belongs in the same change.

---

## 5 · What did not survive verification

Twenty-one findings were refuted. The ones that matter:

- **Checkboxes and radios DO follow the palette.** The claim that native checked controls
  ignore it — filed by the first pass as an `R-74` violation — is false.
  `design/components.css:22` sets `accent-color`, which is why no `appearance: none` was
  needed. Browser-proven twice, independently.
- **"Zero non-colour properties move" is wrong as stated:** four shadow composites change
  blur and offset between light and dark. The `R-74` conclusion survives because the change
  is palette-invariant within a scheme and is a declared scheme decision.
- **`.code` is monospace on both surfaces.** CSS overrides per declaration and the second
  sheet never declares `font-family`.
- **The device cascade fix is not free.** Priced as a block move; measured, device-dark goes
  from 0/17 to 5/17 failing contrast assertions, because the mix runs toward near-white in
  dark. **The fix does not create the illegibility, it reveals it.**
- **Four censuses were contaminated by the generated byte copies** — proven by reproducing
  the wrong number with the copies included. `var(--ease)` is 55 not 77; `--ease-travel` is
  **1 not 3**, a single declaration tripled by the copies.
- **One census swallowed the Sign-in-with-Google region**, which is excluded by ruling. The
  six-families share is 47.4%, not 48.5%.
- **`OP-97`'s 138 and this review's 140 are different quantities**, not a restatement.
  `OP-97`'s figure is the buckets it deliberately left; the new one is exact duplicates. The
  scope gap is real: **93 of the 140 live in ten stylesheets the census never opened.**
- **The 117-row component matrix was hand-authored, not derived**, and omitted four members
  of its own stated universe — including Supabase's own `Button` wrapper.
- **`PINNED` has 66 rows, not 26.** The finding that rests on it — zero rows for either
  design document — survives; the number did not.

**Why this section exists.** Six of the nine above would have shipped as findings without
the verify pass, and two of them would have accused the code of violating a ruling it
obeys. A review without an adversarial stage is a list of plausible claims.

---

## 6 · Twelve decisions, and none of them is a reviewer's

Recorded in full as `REQ-49`'s open questions. The four that gate the rest:

| | question | the number | recommendation |
|---|---|---|---|
| OD-01 | adopt their numeric ramps 200-600? | 15 tokens across 3 blocks = 45 declarations minimum; `THEME_PROPERTIES` 36 to 51 | **no** to the ramps, **yes** to the four status-border tokens — a quarter of the cost, 14 call sites behind it |
| OD-02 | is `--amber` the intended colour, or the accident of a clip? | 9.5 degrees off their warning hue; the hue-holding value is `#8d5e00` | switch, **or** rule "clip accepted" — either way the comment is now true |
| OD-03 | five more contrast pairs, and a `device` state? | 102 to 132 assertions, **zero new tokens** | **yes**, measured before landing rather than landed red |
| OD-04 | fix the device cascade? | a seven-declaration block move — and 5 of 17 newly failing | **yes**, but land it with OD-03, not before |

---

## 7 · What this pull request did not do

It changed **no value, no selector and no component rule.** Seven comments, six documents,
the registers, and one review. The twelve decisions are open and every defect above is
filed rather than fixed, per **C1**: diagnose, confirm, then fix.
