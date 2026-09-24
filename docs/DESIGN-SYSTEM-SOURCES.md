<!--
  THE AUTHORITY LIST FOR THE DESIGN SYSTEM. Given by the owner on 2026-09-06 and kept here
  rather than on one machine, because a reference only one checkout can reach is not a
  reference. It is a REFERENCE, not a register: it records where the truth lives, never what
  work is outstanding. Outstanding work is `gh issue list` -- see CLAUDE.md.

  HOW IT IS MAINTAINED. Add a source when one is found to be authoritative; move a source to
  "Archived or Deprecated" when it stops being; correct a claim when it is measured wrong.
  Every edit says WHAT CHANGED AND WHY in its commit message, never in a note here.

  ITS COMPANION is docs/DESIGN-SYSTEM.md, which describes THIS product's system. This file
  describes the system that one is measured against. When they disagree, this file is the
  outside authority and DESIGN-SYSTEM.md is the thing under review.
-->

# Where the design system's rules come from

_Sources verified on September 6, 2026; pinned on September 24, 2026._

This is the product's source rule, not a reading list. The owner ruled it in #1040: **Supabase's design system governs everything it specifies, at commit `86c813ec`**, the one `design/supabase.NOTICE.txt` pins. That covers values and components: colours, component shapes and sizes, patterns, motion, focus geometry, icons and copy. It does not cover the implementation layer (React, Radix, Tailwind, a build step). What a Supabase value or class string says is transcribed into CSS. The basis moves only by a deliberate re-pin, never by following master. Where Supabase is silent, the [gap sources](#gap-sources-studied-not-adopted) are **studied, not adopted**, and nothing is deleted. The sources below are ordered by authority.

## Primary Sources of Truth

| Source | How to use it during review |
| --- | --- |
| [Supabase Design System](https://supabase.com/design-system), built from [`apps/design-system` at the pin](https://github.com/supabase/supabase/tree/86c813ec03e340ffbe4aeb97cd0c5bee7a0ead94/apps/design-system) | **Illustrative only.** The live site is built from master, so it shows what Supabase merged after the pin; cite the pinned source beside it. It includes foundations, UI patterns, fragment components, atom components, interactive examples, and implementation samples. |
| [Design System source](https://github.com/supabase/supabase/tree/86c813ec03e340ffbe4aeb97cd0c5bee7a0ead94/apps/design-system) | Source for the Design System website, documentation, demonstrations, and registry. Its README explains that component implementations live in `packages/ui` and `packages/ui-patterns`. |
| [Documentation source](https://github.com/supabase/supabase/tree/86c813ec03e340ffbe4aeb97cd0c5bee7a0ead94/apps/design-system/content/docs) | Original documentation files. Use them to extract review rules that can be traced to an exact source. |
| [Examples and registry](https://github.com/supabase/supabase/tree/86c813ec03e340ffbe4aeb97cd0c5bee7a0ead94/apps/design-system/registry) | Examples, variants, states, fragments, and chart blocks used by the documentation. Use them for behavioral and visual comparison. |
| [Atom component implementations](https://github.com/supabase/supabase/tree/86c813ec03e340ffbe4aeb97cd0c5bee7a0ead94/packages/ui) | Actual implementation of shared primitives such as buttons, inputs, dialogs, tables, and other controls. The package is built on Radix UI and shadcn/ui and styled with Tailwind CSS and semantic tokens. |
| [Composite UI patterns](https://github.com/supabase/supabase/tree/86c813ec03e340ffbe4aeb97cd0c5bee7a0ead94/packages/ui-patterns) | Implementations of higher-level and composite components, including page structures, forms, confirmations, chat interfaces, filters, and other shared patterns. |
| [Supabase icons](https://github.com/supabase/supabase/tree/86c813ec03e340ffbe4aeb97cd0c5bee7a0ead94/packages/icons) | Custom icon source, SVG rules, naming conventions, sizing, and integration with Lucide icons. |
| [Supabase Studio](https://github.com/supabase/supabase/tree/86c813ec03e340ffbe4aeb97cd0c5bee7a0ead94/apps/studio) | Production reference showing how components and patterns are composed in realistic interfaces, including loading, error, empty, responsive, and permission-dependent states. |

## Official Design Foundations

The following official references define the foundations that every review should cover:

- [Accessibility](https://supabase.com/design-system/docs/accessibility) · [`accessibility.mdx`](https://github.com/supabase/supabase/blob/86c813ec03e340ffbe4aeb97cd0c5bee7a0ead94/apps/design-system/content/docs/accessibility.mdx): keyboard access, focus management, screen-reader support, labeling, imagery, landmarks, and interactive controls.
- [Color Usage](https://supabase.com/design-system/docs/color-usage) · [`color-usage.mdx`](https://github.com/supabase/supabase/blob/86c813ec03e340ffbe4aeb97cd0c5bee7a0ead94/apps/design-system/content/docs/color-usage.mdx): semantic colors, backgrounds, surfaces, borders, overlays, and warning, destructive, and brand states.
- [Tailwind Classes](https://supabase.com/design-system/docs/tailwind-classes) · [`tailwind-classes.mdx`](https://github.com/supabase/supabase/blob/86c813ec03e340ffbe4aeb97cd0c5bee7a0ead94/apps/design-system/content/docs/tailwind-classes.mdx): the mapping between Tailwind utilities and CSS custom properties, including semantic shorthand classes.
- [Theming](https://supabase.com/design-system/docs/theming) · [`theming.mdx`](https://github.com/supabase/supabase/blob/86c813ec03e340ffbe4aeb97cd0c5bee7a0ead94/apps/design-system/content/docs/theming.mdx): light, dark, deep-dark, and system themes.
- [Typography](https://supabase.com/design-system/docs/typography) · [`typography.mdx`](https://github.com/supabase/supabase/blob/86c813ec03e340ffbe4aeb97cd0c5bee7a0ead94/apps/design-system/content/docs/typography.mdx): supported typography variables and reusable text styles.
- [Icons](https://supabase.com/design-system/docs/icons) · [`icons.mdx`](https://github.com/supabase/supabase/blob/86c813ec03e340ffbe4aeb97cd0c5bee7a0ead94/apps/design-system/content/docs/icons.mdx): use of Lucide, custom Supabase icons, icon meaning, tinting, SVG construction, and naming.
- [Copywriting](https://supabase.com/design-system/docs/copywriting) · [`copywriting.mdx`](https://github.com/supabase/supabase/blob/86c813ec03e340ffbe4aeb97cd0c5bee7a0ead94/apps/design-system/content/docs/copywriting.mdx): voice and tone, action labels, headings, form descriptions, error messages, loading states, confirmations, and terminology.

## Component Architecture

Supabase organizes its interface system into three layers:

### UI Patterns

[UI Patterns](https://supabase.com/design-system/docs/ui-patterns/introduction) ([`ui-patterns/introduction.mdx`](https://github.com/supabase/supabase/blob/86c813ec03e340ffbe4aeb97cd0c5bee7a0ead94/apps/design-system/content/docs/ui-patterns/introduction.mdx) at the pin) provide higher-level guidance for composing complete interface sections. The catalog covers:

- Charts
- Connect interstitials
- Empty states
- Forms
- Layout
- Markdown
- Modality
- Navigation
- Tables

Review page-level composition, hierarchy, spacing, content width, navigation placement, form structure, modal selection, data presentation, loading states, errors, empty states, and responsive behavior against the applicable pattern.

### Fragment Components

[Fragment Components](https://supabase.com/design-system/docs/fragments/introduction) ([`fragments/introduction.mdx`](https://github.com/supabase/supabase/blob/86c813ec03e340ffbe4aeb97cd0c5bee7a0ead94/apps/design-system/content/docs/fragments/introduction.mdx) at the pin) are reusable composite components assembled from atom components. They provide standardized solutions for forms, navigation, dialogs, empty states, data display, status communication, and page structure.

Use the complete fragment catalog at the pin, [`content/docs/fragments/`](https://github.com/supabase/supabase/tree/86c813ec03e340ffbe4aeb97cd0c5bee7a0ead94/apps/design-system/content/docs/fragments), when checking whether a project has recreated a pattern that already exists in Supabase.

### Atom Components

[Atom Components](https://supabase.com/design-system/docs/components/introduction) ([`components/introduction.mdx`](https://github.com/supabase/supabase/blob/86c813ec03e340ffbe4aeb97cd0c5bee7a0ead94/apps/design-system/content/docs/components/introduction.mdx) at the pin) are the smallest reusable building blocks. They are primarily based on shadcn/ui and implemented in `packages/ui`.

For each applicable atom, compare:

- Anatomy and DOM semantics
- Variants and sizes
- Default, hover, focus-visible, active, selected, disabled, loading, invalid, and destructive states
- Keyboard behavior and focus management
- Accessible names and descriptions
- Spacing, radius, borders, colors, icons, and typography
- Responsive and touch behavior
- Light and dark theme rendering

## Tokens and Visual Implementation

Use the CSS sources at the pin, never archived token repositories:

- [Semantic CSS](https://github.com/supabase/supabase/blob/86c813ec03e340ffbe4aeb97cd0c5bee7a0ead94/packages/ui/build/css/source/semantic.css)
- [CSS source directory](https://github.com/supabase/supabase/tree/86c813ec03e340ffbe4aeb97cd0c5bee7a0ead94/packages/ui/build/css/source)
- [UI component source](https://github.com/supabase/supabase/tree/86c813ec03e340ffbe4aeb97cd0c5bee7a0ead94/packages/ui/src/components)

**Tailwind's values, stated once so they never read as a second source.** Some Supabase atoms name a Tailwind utility that Supabase's own CSS does not override: `shadow-*`, `leading-*`, the spacing multiple, the radius ramp, `ease-out`, `animate-pulse`. There, the value is the one that atom renders at the pin, from tailwindcss 4.2.4 (`pnpm-lock.yaml@86c813ec:2618-2620` resolves it for `packages/ui`). None of the 29 CSS files at the pin under `apps/design-system`, `packages/config`, `packages/ui` and `packages/ui-patterns` declares `--shadow-*` or `--leading-*`. Where Supabase does declare a value (the `--spacing-*` set, `--spacing-content`, `--radius-panel`, the mono size ramp, the `--animate-*` ramp), Supabase's declaration governs. Tailwind is never cited for a value in its own right.

Compare semantic roles and their values. Review background, foreground, card, muted, border, field, control, warning, destructive, and brand roles and verify that the project does not scatter hardcoded visual values across components.

Also review:

- Color hierarchy and contrast
- Theme token coverage
- Spacing rhythm
- Component density
- Border radius and border hierarchy
- Shadows and overlays
- Typography scale and hierarchy
- Icon size and stroke consistency
- Motion duration and restraint
- State-token consistency

## Code Organization, Naming, Reuse, and DRY

These official repository sources rank fifth in the [precedence order](#source-conflict-resolution-order), below the documentation they defer to. What one says about a pattern, a component or copy is Supabase speaking. What one says about the implementation layer (React, testing, review tooling) is context, because #1040 excludes that layer. At the pin the repository instructions are `.claude/CLAUDE.md` and `apps/studio/CLAUDE.md`; master renamed them `AGENTS.md` and `apps/studio/AGENTS.md` after the pin.

- [Supabase repository instructions](https://github.com/supabase/supabase/blob/86c813ec03e340ffbe4aeb97cd0c5bee7a0ead94/.claude/CLAUDE.md): repository structure, conventions, the U.S. English rule, and which skill governs which task. **Its U.S. English rule does not change ScrapeX copy:** Supabase is inconsistent (its design-system docs write British `organisation` and `colour`), so under rule 2 nothing is changed (#1040).
- [Supabase Studio instructions](https://github.com/supabase/supabase/blob/86c813ec03e340ffbe4aeb97cd0c5bee7a0ead94/apps/studio/CLAUDE.md): naming, responsibility boundaries, reuse-first guidance, co-location, and the skills each Studio task requires.

- [Studio UI Patterns skill](https://github.com/supabase/supabase/blob/86c813ec03e340ffbe4aeb97cd0c5bee7a0ead94/.claude/skills/studio-ui-patterns/SKILL.md): Supabase-specific guidance for pages, forms, tables, charts, sheets, empty states, and navigation.
- [Studio testing strategy](https://github.com/supabase/supabase/blob/86c813ec03e340ffbe4aeb97cd0c5bee7a0ead94/.claude/skills/studio-testing/SKILL.md): extracting logic from React components, testing pure utilities, interaction testing, edge-case coverage, and end-to-end test selection.
- [Copywriting review rule](https://github.com/supabase/supabase/blob/86c813ec03e340ffbe4aeb97cd0c5bee7a0ead94/.claude/skills/copywriting/SKILL.md): requires the official copywriting guidance to be applied whenever user-facing text is written or reviewed.
- [CodeRabbit configuration](https://github.com/supabase/supabase/blob/86c813ec03e340ffbe4aeb97cd0c5bee7a0ead94/.coderabbit.yaml): a practical example of applying Supabase rules and skills to automated review while excluding generated files.

The review should examine whether:

- Files, components, hooks, and functions have a single coherent responsibility.
- Names clearly communicate domain purpose and follow consistent conventions.
- Related subcomponents are colocated with their parent when appropriate.
- Existing components, hooks, patterns, and utilities are reused before new ones are introduced.
- Meaningful duplication is removed without forcing unrelated features into a shared abstraction.
- Shared abstractions reduce real maintenance cost and preserve clear ownership.
- Public APIs and component props remain predictable and composable.
- Dead code, obsolete files, redundant exports, and unnecessary indirection are removed safely.
- Business logic is separated from rendering when doing so improves clarity and testability.
- Refactoring does not create excessive fragmentation or vague catch-all modules such as `utils`, `helpers`, `common`, or `misc`.

## Supabase Library

[Supabase Library](https://supabase.com/library) is an official collection of Supabase-connected blocks and developer tools. It includes authentication, Storage, Realtime, OAuth, and platform-oriented flows. The library uses a shadcn-compatible registry model and is useful for reviewing complete product flows.

Use it as a supplementary source for integrated blocks, not as a replacement for the core Design System. See the [official launch article](https://supabase.com/blog/supabase-ui-library) for its purpose and architecture.

## Supporting Upstream Standards

Background for a reviewer, not rules. Radix, shadcn/ui and Tailwind are the implementation layer #1040 excludes, and where Supabase is silent the [gap table](#gap-sources-studied-not-adopted) names the source to study, not this list:

- [shadcn/ui components](https://ui.shadcn.com/docs/components)
- [Radix Primitives accessibility](https://www.radix-ui.com/primitives/docs/overview/accessibility)
- [WAI-ARIA Authoring Practices](https://www.w3.org/WAI/ARIA/apg/patterns/)
- [WCAG 2.2](https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/)
- [Tailwind CSS documentation](https://tailwindcss.com/docs)
- [Lucide documentation](https://lucide.dev/guide/packages/lucide-react)

They can help a reviewer read semantics, ARIA usage, keyboard models and focus trapping. They never override what the Design System documents or implements at the pin.

## Design Philosophy and Process

[How design works at Supabase](https://supabase.com/blog/how-design-works-at-supabase) explains the broader design philosophy and process. Relevant principles include:

- Iterative, principle-led design
- A deliberately small design-system library
- Reuse based on demonstrated need
- Design iteration continuing in production code
- Restrained animation
- Synchronization of Figma variables with CSS custom properties and Tailwind utilities

This source provides context, but the Design System documentation and code at the pin take precedence when judging an implementation.

## Figma Availability

No current official public Supabase Figma library was found that can be treated as a source of truth. Supabase's design-process article describes internally organized Figma libraries, and an older public discussion also refers to the Figma system as internal.

- [How design works at Supabase](https://supabase.com/blog/how-design-works-at-supabase)
- [Historical Supabase design-system discussion](https://github.com/orgs/supabase/discussions/195)

Do not treat community Figma kits, screenshots, or reverse-engineered themes as authoritative unless Supabase explicitly publishes or endorses them.

## Archived or Deprecated Sources

Do not use the following as current sources of truth:

- [supabase/ui](https://github.com/supabase/ui): archived and deprecated; the active implementation moved to the main monorepo.
- [supabase/design-tokens](https://github.com/supabase/design-tokens): archived; useful only for historical investigation.
- [supabase-ui-web](https://github.com/supabase/supabase-ui-web): deprecated and superseded by work in the main Supabase monorepo.
- Unofficial Figma kits, cloned dashboards, reverse-engineered themes, and third-party articles.

Historical sources may explain old decisions, but they must not override the documentation, code, or production composition at the pin.

## Source-Conflict Resolution Order

When sources disagree, use this precedence order:

1. The Supabase Design System documentation at the pinned commit, `apps/design-system/content/docs`. The live site illustrates it and follows master, so it is never the citation.
2. The Design System registry at the pinned commit.
3. The implementations in `packages/ui` and `packages/ui-patterns` at the pinned commit.
4. The production composition in `apps/studio` at the pinned commit.
5. Supabase's repository instructions and official skills at the pinned commit.
6. Only where Supabase is silent: the source the [gap table](#gap-sources-studied-not-adopted) names for that gap, adopted as that section says. A [mandate](#mandates)'s source outranks items 1–5, for its one request only.
7. Official Supabase articles for philosophy and historical context.
8. Archived sources only for historical investigation.

**A prior decision in this repository never ranks above a Supabase specification.** That includes a ruling in `docs/archive/`, an issue, and a comment in the code. Where one allowed a difference, the difference is corrected (#1040).

If documentation and implementation conflict, record the conflict explicitly with links, file paths, commit dates, and observed behavior. Do not silently choose whichever source is easier to follow.

## Gap sources: studied, not adopted

A conflict exists only where Supabase **specifies** something different. Where it is silent, nothing is deleted. The gap is studied against the official sources named here, and **none is adopted** until the study lands on its issue and he reviews it. The exceptions are two he has already settled: #1040 adopted Noto Sans Arabic (#1048 ships it), and Google's branding guidelines already govern the sign-in button through its test. A Supabase value that fails a WCAG criterion still ships for now; a second source enters only through a mandate.

| Where Supabase is silent | Official sources to study | Studied in |
| --- | --- | --- |
| Arabic data in English chrome: the bidi contract, and the Arabic face | HTML `dir` and `<bdi>`; Unicode UAX #9; CSS Writing Modes 3; CSS Logical Properties 1; ECMA-402 with CLDR collation. The face, Noto Sans Arabic (OFL-1.1), is already adopted | #1073; the face, #1048 |
| `forced-colors` | CSS Color Adjustment Module 1 | #724 |
| `prefers-contrast` | Media Queries 5; WCAG 2.2 SC 1.4.6 and 1.4.11 | #724, #406 |
| Reduced motion outside the animations Supabase guards itself (`packages/config/css/utilities.css@86c813ec:176-182` guards `.shimmer`) | WCAG 2.2 SC 2.3.3; Media Queries 5 | #701 |
| Status messages, and progress past a declared total | WCAG 2.2 SC 4.1.3; WAI-ARIA 1.2 `status`, `alert` and `progressbar` | #1066, #1036 |
| Keyboard models Supabase leaves to Radix: menu button, listbox, tabs | WAI-ARIA APG Menu Button, Listbox and Tabs. Radix itself is the implementation layer | #1058 |
| Touch-target size outside action cells | WCAG 2.2 SC 2.5.8 | #1051 |
| Landmarks on surfaces without header and sidebar chrome | WCAG 2.2 SC 2.4.1 and 1.3.1 | #749 |
| Order among overlays on one layer | CSS 2.2 Appendix E; the HTML `dialog` top layer | #410 |
| The Google sign-in button | Google Identity branding guidelines | `tests/test_the_google_button_follows_googles_rules.py` |
| The panel below 480px | WCAG 2.2 SC 1.4.10; the Chrome `sidePanel` API | #1070 |
| Grid row count, reorder, pinning, sticky header | WAI-ARIA 1.2 `aria-rowcount`; APG Grid | #1075 |
| Job-state words the copywriting page is silent on | The Carbon status indicator, for vocabulary only | #1074 |

## Mandates

A source other than Supabase governs something Supabase covers only by a mandate. He grants a mandate for one specific change he asks for, and it stays as narrow as that request. Each mandate is one row: **request · source · scope · issue**.

_None._

**Barred:** Carbon, Material 3, Polaris, Atlassian, GOV.UK and Office cannot govern anything Supabase covers. Carbon's single row above is for vocabulary, in a gap.

## Recommended Review Evidence

Every confirmed finding should contain:

- Review area and affected component or screen
- Severity and user impact
- Current project behavior
- Expected Supabase behavior
- Link to the relevant Supabase documentation
- Link or path to the relevant Supabase implementation
- Link or path to the affected project implementation
- Screenshot or interaction recording where visual or behavioral evidence is relevant
- Reproduction steps
- Recommended correction
- Acceptance criteria
- Required regression tests

A milestone should not be closed based only on visual similarity. It should also pass behavioral, responsive, accessibility, theme, content, code-quality, naming, reuse, and regression review.

## Licensing and Trademark Boundary

The main Supabase repository is distributed under the [Apache License 2.0](https://github.com/supabase/supabase/blob/86c813ec03e340ffbe4aeb97cd0c5bee7a0ead94/LICENSE). Reuse and derivative work must comply with its notice, attribution, and modification requirements. The license does not grant permission to use Supabase trade names, trademarks, service marks, or product names except for customary attribution.

The [Supabase Brand Assets](https://supabase.com/brand-assets) page also states that Supabase trademarks, logos, and brand elements must not be modified or used for purposes other than representing Supabase.

Therefore, a project may adapt design patterns or appropriately licensed code, but it should use its own product name, logo, wordmark, and brand identity unless it is genuinely representing Supabase and complies with the applicable brand rules.

