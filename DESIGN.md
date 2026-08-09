# Design system: Calm evidence workspace

## Creative north star

DeployGuard is a quiet operations desk: a neutral navigation rail beside a
large, paper-like work surface. The system borrows the spatial calm and clarity
of the supplied reference—not its brand—so dense operational evidence feels
approachable without losing precision.

## Scene and mode

This is an **Operate** interface used for long desktop sessions in ordinary
office light, often during a release or incident. Light mode is the primary
world. Dark mode remains supported as an accessibility and preference option,
using the same topology and contrast hierarchy.

## Palette

- `Canvas #f6f8fa`: viewport and quiet breathing room.
- `Rail gray #f6f8fa`: persistent navigation region.
- `Workspace #ffffff`: primary work surface.
- `Paper #ffffff`: focused records, forms, and responses.
- `Ink #1f2328`: conclusions and labels.
- `Muted #656d76`: metadata and supporting copy.
- `Rule #d0d7de`: structural separators.
- `Action blue #0969da`: selection, links, and primary focus.
- `Success #2f7d5c`, `attention #9a6b25`, `danger #b84b55`: semantic states only.

Color strategy is restrained: mist neutrals plus one action blue. Semantic color
is always paired with text or an icon.

## Typography

Use the native UI stack: `Segoe UI Variable`, `Segoe UI`, `Noto Sans Thai`, and
system sans-serif. Body text is 14px/1.55. Navigation and metadata are 12–13px.
Panel titles are 15–16px/600. Page titles are 22–28px/650 with restrained
tracking. Hashes, timestamps, and measurements alone use the mono stack.

## Topology

- Desktop: 216px navigation rail, 8px seam, and one flexible workspace frame.
- The workspace frame has a compact header, optional context strip, and a single
  scrollable content column capped at 1240px.
- Evidence-heavy views use one primary ledger with a secondary inspector; avoid
  unrelated card grids and nested cards.
- Tablet collapses the inspector below the ledger. Mobile turns the rail into a
  drawer and uses a single edge-to-edge work surface.

## Surfaces and depth

The outer app may use one soft ambient shadow to read as a contained desktop.
Working content stays flat: background changes and one-pixel rules establish
hierarchy. Paper records may use a 12–14px radius. Nested records share dividers
instead of receiving another border and shadow.

## Components

- Navigation rows: 36px desktop, 44px touch, 8px radius, icon + sentence-case
  label. Active state uses a slightly stronger blue fill and ink; no glow.
- Buttons: 34px desktop, 44px touch, 8px radius. Primary is action blue;
  secondary is paper with a rule border; tertiary is text-only.
- Inputs: visible label, paper fill, subtle rule, 8px radius, blue focus ring.
- Statuses: compact text labels with a small icon or dot; pills only for short
  machine states.
- Panels: one parent surface, 14px radius, 20–24px padding. Internal sections use
  whitespace and dividers rather than child cards.
- Tables and ledgers: quiet header, 44px minimum rows, selected row tint, sticky
  headers only when they materially aid scanning.

## Motion

Use a single 160ms exponential ease-out language for drawer, menu, row selection,
and content-state changes. Content is visible by default. Disable nonessential
motion under `prefers-reduced-motion`.

## Content and states

Every page provides clear loading, empty, unavailable, error, permission, and
success states. Errors name both the problem and recovery. Synthetic data is
labeled at the point of use. Destructive or governance actions state their
scope and never rely on color alone.

## Rules

- Preserve generous breathing room and one obvious reading order.
- Keep controls close to the record they affect.
- Use sentence case; reserve uppercase for DORA and externally defined codes.
- Do not use gradients, decorative glass, glow borders, ornamental charts,
  floating metric-card grids, or nested bordered cards.
- Do not copy logos, mascots, illustrations, or branded assets from the reference.
