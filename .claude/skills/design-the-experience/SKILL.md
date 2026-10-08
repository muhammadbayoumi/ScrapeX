---
name: design-the-experience
description: How anything he sees or does is designed, before it is built — a page, a control, a state, a sentence, the steps of a task. Supabase at the pin is the base; every element is mapped to it, every departure is shown to him side by side, the proposal passes a critical review, and only then is it built and opened as a PR. Use before changing any page of the panel, the extension or the web UI, before writing interface copy, and whenever a design or UI review is asked for.
---

# Designing what he sees and does

One question, answered before any code: **what will he see, what will he do, and what does
each part of it rest on?** A screen built from taste ships taste, and the next session
cannot tell a decision from an accident. A screen built through this skill carries its
reasons with it.

It covers the whole experience, not only the look:

- **the interface**: pages, components, colours, sizes, icons;
- **the work**: where a task starts, how many steps it takes, what each press does;
- **the words**: titles, labels, buttons, errors, empty states;
- **the states**: loading, empty, failed, engine down, long text, his Arabic data.

## The base, and the only three ways off it

**Supabase's design system at the pin is the base**: the commit `design/supabase.NOTICE.txt`
names, read in the order `docs/DESIGN-SYSTEM-SOURCES.md` ranks its sources:
1. the documentation;
2. the registry;
3. `packages/ui` and `packages/ui-patterns`;
4. Studio's production code.

An element leaves it for one of three reasons only, and the reason is written beside the
element:

| reason | when |
|---|---|
| **gap** | Supabase does not cover the point, or does not cover it well enough |
| **his preference** | he is not comfortable with a Supabase detail and wants another source to handle it |
| **study-backed proposal** | this session proposes a different answer, from a study it can show |

**Every departure is shown to him before it is built**: Supabase's version and the
alternative side by side, as an image or an HTML page, with the measurements that decide
it (contrast, width, count of steps). He chooses from the picture, not from a description.
A departure he approves becomes a row in `docs/DESIGN-SYSTEM-SOURCES.md`: a gap row or a
mandate row, with its reason.

The comparison is drawn the way the mock-up is: the whole panel, rail included, at the three
widths side by side, one image per option. A cropped strip of rows hides what the option
does to the page. Where an option shortens text, a second image shows where the full text
appears: the tooltip open, the log expanded. He must be able to read every word before he
picks.

Nothing is final. When the pin moves, or Supabase changes a rule, every departure that rested
on the old rule is re-opened and shown to him again.

## The stages

Each stage closes before the next opens. The record of each lives on the page's study issue
(milestone 47 for the panel's pages); nothing is recorded in a repository file but the
sources table and the skill itself.

### 1 · Intake

- Name the page or flow, and read its study issue and every issue it links.
- List the open PRs that touch its files. A page someone else is changing is not started.
- Read the code that draws it today, with `file:line`.

**Closes when** no open PR collides, and the current behaviour is written down.

### 2 · The reference map

Check out Supabase at the pin, and search it, rather than recalling it:

```
python tools/checkout_supabase_pin.py          # prints the directory; re-runs are cheap
```

For **every element** of the proposal, write one row: element · reference · class.

- **S**: a clause in the documentation, an atom in `packages/ui`, or Studio's own code at the
  pin. Cite it as `path@86c813ec:line`. Studio is often the best reference: a job list, a
  log, a settings page, a destructive menu item. Search `apps/studio/components` for the
  same problem before inventing an answer.
- **G**: Supabase is silent, and the gap table already names a source.
- **N**: Supabase is silent, and no source is recorded yet.

The class is honest or it is useless. If only three of seven statuses come from Studio,
the row says three of seven.

**Closes when** every element has a row.

### 3 · Closing the gaps

Every **N**, and every departure, is resolved before the mock-up is shown:

- **A gap** gets a widely followed official source: W3C (WCAG, WAI-ARIA, APG, CSS),
  ECMA-402, the Chrome extension APIs, or a published design system for vocabulary only.
  The PR that builds it adds the gap-table row.
- **His preference, or a study-backed proposal**, gets the side-by-side comparison described
  above. The PR that builds it adds the mandate row.
- A Supabase value that fails a WCAG criterion is **not** quietly replaced. First look for a
  composition that keeps Supabase's values and passes; only then offer a departure.

  The worked example, decided on 2026-10-08: warning text. `warning-600` fails 4.5:1 as
  12 px text on white (≈3.05:1). So the colour goes on the icon, which needs only 3:1, and
  the words take the foreground colour. Every value stays Supabase's.

**Closes when** no **N** is left, and he has chosen every departure from its picture.

### 4 · The mock-up

Built in the real harness, from the real parts. A mock-up that approximates approves a
screen that will not exist.

- **Render it** through `tools/panel_harness.py` (the panel) or `tools/tabpage_harness.py`
  (the extension's own pages), so the rail, fonts, tokens and theme are the shipped ones.
- **Use the shared components** in `extension/components.css` and their tokens. No height,
  radius or colour typed into the mock's own CSS.
- **Widths: 320, 400 and 480 px**, his choice. 320 is the WCAG reflow floor, and 480 is
  Supabase's smallest breakpoint.
- **Both themes**, light and dark.
- **Real data:** his sources' names (Arabic among them) and the engine's own strings, never
  prettier copy. A sentence the engine does not produce is not shown.
- **Every state**:
  - the normal list;
  - filtered;
  - a menu open;
  - a dialog;
  - loading;
  - refresh in progress;
  - a failed read;
  - empty;
  - engine down;
  - the longest real text;
  - each transitional status;
  - the limit or paging case.
- **Numbered markers** on the elements, and **one reference sheet**: marker · element ·
  reference · class. Each image shows the three widths side by side.
- Send the images to him, and post the sheet on the study issue.

**Closes when** every state is rendered at every width in both themes.

### 5 · The critical review

The session that drew the mock-up does not review it alone. An independent reviewer (a
subagent given only the mock-up, the sheet and this list) attacks it on every axis. It
reports each finding as *must fix*, *should fix* or *optional*, the way the `review` skill
does:

1. **References.** Is each class true? Is anything claimed as S that is really the
   proposal's own idea?
2. **Values.** Do sizes, colours, radii and type come from the shared components and
   Supabase's tokens, or were they typed?
3. **Accessibility, measured.**
   - Contrast computed from the drawn colours: 4.5:1 for text, 3:1 for icons and borders.
   - Keyboard path and focus order.
   - Menu and dialog keyboard models.
   - Live regions for changes.
   - Touch targets.
4. **States.** Is any state from stage 4 missing?
5. **Honesty of the data.** Does every sentence and number exist in the engine's payload?
   Does a state claim a cause it cannot know?
6. **The repo's rules.** No control without its capability, and no control drawn for a route
   that 404s. One feature in one place. No silent failure. A plan is not an approval.
7. **Words.** Every string against `copywriting.mdx@86c813ec`.
8. **Narrow width and Arabic.** Nothing that identifies a row is cut at 320 px. Bidi holds.
9. **Cost.** Requests added to the engine, polling, and anything that needs an engine change
   or a `VERSION` bump.
10. **Collisions.** Open PRs and issues on the same files or the same decision.

Every *must fix* and *should fix* returns the proposal to the stage it came from.

**Closes when** a review returns none.

### 6 · His confirmation

He sees:
- the images;
- the reference sheet;
- the departures with their comparisons;
- the review's result.

His answer is recorded on the study issue. **Nothing is built before it.** An interface
question is not handed to him to answer; the study answers it from the sources, and he
reviews the answer.

### 7 · Building it

- Tests first, which fail on today's code:
  - DOM tests through the same harness, at the three widths;
  - the contrast of every state colour;
  - each control's route.
- Then the change, using the shared components. Then break the fix on purpose and watch the
  tests fail.
- The gap and mandate rows from stage 3 land in `docs/DESIGN-SYSTEM-SOURCES.md` in the same
  PR.

### 8 · The PR

The body carries:
- the reference table;
- before and after images at the three widths;
- the departures, each with its picture;
- the review's result.

It merges through the `review` skill's gate, like any other change.

### 9 · Teaching this skill

Each run ends by asking **what this skill missed**: a state nobody listed, an axis the review
did not have, a source that should have been searched first. The answer is edited into this
file in the same PR. The workflow is meant to grow with each page it is used on.
