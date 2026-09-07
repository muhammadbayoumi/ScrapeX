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

# Supabase Design System Review Sources

_Research verified on September 6, 2026._

This document collects the official and supporting sources that should be used when auditing a design system against the current Supabase Design System. Sources are ordered by authority and practical value.

## Primary Sources of Truth

| Source | How to use it during review |
| --- | --- |
| [Supabase Design System](https://supabase.com/design-system) | The primary visual and behavioral reference. It includes foundations, UI patterns, fragment components, atom components, interactive examples, and implementation samples. |
| [Design System source](https://github.com/supabase/supabase/tree/master/apps/design-system) | Source for the Design System website, documentation, demonstrations, and registry. Its README explains that component implementations live in `packages/ui` and `packages/ui-patterns`. |
| [Documentation source](https://github.com/supabase/supabase/tree/master/apps/design-system/content/docs) | Original documentation files. Use them to extract review rules that can be traced to an exact source. |
| [Examples and registry](https://github.com/supabase/supabase/tree/master/apps/design-system/registry) | Examples, variants, states, fragments, and chart blocks used by the documentation. Use them for behavioral and visual comparison. |
| [Atom component implementations](https://github.com/supabase/supabase/tree/master/packages/ui) | Actual implementation of shared primitives such as buttons, inputs, dialogs, tables, and other controls. The package is built on Radix UI and shadcn/ui and styled with Tailwind CSS and semantic tokens. |
| [Composite UI patterns](https://github.com/supabase/supabase/tree/master/packages/ui-patterns) | Implementations of higher-level and composite components, including page structures, forms, confirmations, chat interfaces, filters, and other shared patterns. |
| [Supabase icons](https://github.com/supabase/supabase/tree/master/packages/icons) | Custom icon source, SVG rules, naming conventions, sizing, and integration with Lucide icons. |
| [Supabase Studio](https://github.com/supabase/supabase/tree/master/apps/studio) | Production reference showing how components and patterns are composed in realistic interfaces, including loading, error, empty, responsive, and permission-dependent states. |

## Official Design Foundations

The following official references define the foundations that every review should cover:

- [Accessibility](https://supabase.com/design-system/docs/accessibility): keyboard access, focus management, screen-reader support, labeling, imagery, landmarks, and interactive controls.
- [Color Usage](https://supabase.com/design-system/docs/color-usage): semantic colors, backgrounds, surfaces, borders, overlays, and warning, destructive, and brand states.
- [Tailwind Classes](https://supabase.com/design-system/docs/tailwind-classes): the mapping between Tailwind utilities and CSS custom properties, including semantic shorthand classes.
- [Theming](https://supabase.com/design-system/docs/theming): light, dark, deep-dark, and system themes.
- [Typography](https://supabase.com/design-system/docs/typography): supported typography variables and reusable text styles.
- [Icons](https://supabase.com/design-system/docs/icons): use of Lucide, custom Supabase icons, icon meaning, tinting, SVG construction, and naming.
- [Copywriting](https://supabase.com/design-system/docs/copywriting): voice and tone, action labels, headings, form descriptions, error messages, loading states, confirmations, and terminology.

## Component Architecture

Supabase organizes its interface system into three layers:

### UI Patterns

[UI Patterns](https://supabase.com/design-system/docs/ui-patterns/introduction) provide higher-level guidance for composing complete interface sections. The catalog covers:

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

[Fragment Components](https://supabase.com/design-system/docs/fragments/introduction) are reusable composite components assembled from atom components. They provide standardized solutions for forms, navigation, dialogs, empty states, data display, status communication, and page structure.

Use the complete fragment catalog on the Design System website when checking whether a project has recreated a pattern that already exists in Supabase.

### Atom Components

[Atom Components](https://supabase.com/design-system/docs/components/introduction) are the smallest reusable building blocks. They are primarily based on shadcn/ui and implemented in `packages/ui`.

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

Use the current CSS sources rather than archived token repositories:

- [Semantic CSS](https://github.com/supabase/supabase/blob/master/packages/ui/build/css/source/semantic.css)
- [CSS source directory](https://github.com/supabase/supabase/tree/master/packages/ui/build/css/source)
- [UI component source](https://github.com/supabase/supabase/tree/master/packages/ui/src/components)

The audit should compare semantic roles rather than isolated color values. Review background, foreground, card, muted, border, field, control, warning, destructive, and brand roles and verify that the project does not scatter hardcoded visual values across components.

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

These official repository sources reveal the engineering conventions used alongside the visual system:

- [Supabase repository instructions](https://github.com/supabase/supabase/blob/master/AGENTS.md): repository structure, component ownership, semantic styling, imports, exports, checks, and shared-package boundaries.
- [Supabase Studio instructions](https://github.com/supabase/supabase/blob/master/apps/studio/AGENTS.md): naming, responsibility boundaries, reuse-first guidance, component extraction, co-location, testing, direct imports, and avoidance of unnecessary barrel files and compatibility shims.
- [Studio UI Patterns skill](https://github.com/supabase/supabase/blob/master/.claude/skills/studio-ui-patterns/SKILL.md): Supabase-specific guidance for pages, forms, tables, charts, sheets, empty states, and navigation.
- [Studio testing strategy](https://github.com/supabase/supabase/blob/master/.claude/skills/studio-testing/SKILL.md): extracting logic from React components, testing pure utilities, interaction testing, edge-case coverage, and end-to-end test selection.
- [Copywriting review rule](https://github.com/supabase/supabase/blob/master/.claude/skills/copywriting/SKILL.md): requires the official copywriting guidance to be applied whenever user-facing text is written or reviewed.
- [CodeRabbit configuration](https://github.com/supabase/supabase/blob/master/.coderabbit.yaml): a practical example of applying Supabase rules and skills to automated review while excluding generated files.

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

Use these primary upstream sources when Supabase documentation does not fully specify behavior:

- [shadcn/ui components](https://ui.shadcn.com/docs/components)
- [Radix Primitives accessibility](https://www.radix-ui.com/primitives/docs/overview/accessibility)
- [WAI-ARIA Authoring Practices](https://www.w3.org/WAI/ARIA/apg/patterns/)
- [WCAG 2.2](https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/)
- [Tailwind CSS documentation](https://tailwindcss.com/docs)
- [Lucide documentation](https://lucide.dev/guide/packages/lucide-react)

These sources should validate semantics, ARIA usage, keyboard models, focus trapping, responsive utilities, and primitive behavior. They should not override Supabase-specific visual decisions documented or implemented in the current Design System.

## Design Philosophy and Process

[How design works at Supabase](https://supabase.com/blog/how-design-works-at-supabase) explains the broader design philosophy and process. Relevant principles include:

- Iterative, principle-led design
- A deliberately small design-system library
- Reuse based on demonstrated need
- Design iteration continuing in production code
- Restrained animation
- Synchronization of Figma variables with CSS custom properties and Tailwind utilities

This source provides context, but current Design System documentation and code should take precedence when judging an implementation.

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

Historical sources may explain old decisions, but they must not override current documentation, code, or production behavior.

## Source-Conflict Resolution Order

When sources disagree, use this precedence order:

1. Current Supabase Design System documentation and interactive demonstrations.
2. `apps/design-system/content/docs` and the Design System registry.
3. Current implementations in `packages/ui` and `packages/ui-patterns`.
4. Current production composition in `apps/studio`.
5. Repository instructions and official Supabase skills.
6. Radix UI, shadcn/ui, WAI-ARIA, and WCAG for behavior and accessibility.
7. Official Supabase articles for philosophy and historical context.
8. Archived sources only for historical investigation.

If documentation and implementation conflict, record the conflict explicitly with links, file paths, commit dates, and observed behavior. Do not silently choose whichever source is easier to follow.

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

The main Supabase repository is distributed under the [Apache License 2.0](https://github.com/supabase/supabase/blob/master/LICENSE). Reuse and derivative work must comply with its notice, attribution, and modification requirements. The license does not grant permission to use Supabase trade names, trademarks, service marks, or product names except for customary attribution.

The [Supabase Brand Assets](https://supabase.com/brand-assets) page also states that Supabase trademarks, logos, and brand elements must not be modified or used for purposes other than representing Supabase.

Therefore, a project may adapt design patterns or appropriately licensed code, but it should use its own product name, logo, wordmark, and brand identity unless it is genuinely representing Supabase and complies with the applicable brand rules.

