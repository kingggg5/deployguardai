---
name: DeployGuard AI
description: A repository-native evidence workspace for change risk and incident investigation.
colors:
  canvas: "#f6f8fa"
  surface: "#ffffff"
  surface-subtle: "#f6f8fa"
  surface-hover: "#f3f4f6"
  text: "#1f2328"
  text-muted: "#636c76"
  border: "#d0d7de"
  border-strong: "#afb8c1"
  accent: "#0969da"
  accent-soft: "#ddf4ff"
  success: "#1a7f37"
  success-soft: "#dafbe1"
  attention: "#9a6700"
  attention-soft: "#fff8c5"
  danger: "#cf222e"
  danger-soft: "#ffebe9"
  header: "#25292f"
  header-deep: "#010409"
  header-border: "#3d444d"
  header-control: "#57606a"
  header-muted: "#8c959f"
  nav-indicator: "#fd8c73"
  accent-dark: "#58a6ff"
typography:
  headline:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans Thai', sans-serif"
    fontSize: "clamp(1.5rem, 3vw, 2rem)"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.02em"
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans Thai', sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
  body-small:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans Thai', sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.5
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans Thai', sans-serif"
    fontSize: "1rem"
    fontWeight: 600
    lineHeight: 1.5
  title-large:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans Thai', sans-serif"
    fontSize: "1.25rem"
    fontWeight: 600
    lineHeight: 1.4
  score:
    fontFamily: "'SFMono-Regular', 'Cascadia Code', Consolas, monospace"
    fontSize: "clamp(2rem, 4vw, 2.875rem)"
    fontWeight: 600
    lineHeight: 1
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans Thai', sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: 1.33
  measure:
    fontFamily: "'SFMono-Regular', 'Cascadia Code', Consolas, monospace"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.4
rounded:
  micro: "2px"
  tight: "4px"
  control: "6px"
  panel: "6px"
  overlay: "12px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"
components:
  button-primary:
    backgroundColor: "{colors.success}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "5px 16px"
    height: "32px"
  button-secondary:
    backgroundColor: "{colors.surface-subtle}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "5px 12px"
    height: "32px"
  panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.panel}"
    padding: "16px"
---

# Design System: DeployGuard AI

## Overview

**Creative North Star: "The Repository Evidence Room"**

DeployGuard should feel immediately familiar to engineers who work in repository hosting tools: repository context first, compact global controls, underlined section navigation, bordered ledgers, status labels, and evidence arranged like inspectable activity rather than marketing analytics. This is a GitHub/Primer-inspired interaction grammar, not a copy of GitHub branding or assets.

The interface is calm, dense, and operational. It prioritizes traceability over spectacle: users can always see which workspace, repository, data origin, change, and incident they are examining. Surfaces stay flat and structured; color appears only when it communicates selection, severity, confidence, or completion.

**Key Characteristics:**

- Repository-first hierarchy with workspace and data-origin context always visible.
- Compact, border-led surfaces designed for scanning under time pressure.
- One shared visual language across investigation, change risk, DORA, scenarios, operations, and setup.
- Evidence, counter-evidence, uncertainty, and human decisions remain visually distinct.
- Connected and synthetic data are never visually interchangeable.

## Colors

The light palette uses cool repository canvas neutrals; dark mode uses near-black code-hosting surfaces. Blue means navigation and inspection, green means a safe affirmative action or successful check, amber means attention, and red means risk or failure.

### Primary

- **Repository Blue**: Interactive links, focus, current navigation, selected records, and evidence connections.

### Secondary

- **Verified Green**: Successful checks and the main affirmative action when an operation is safe and user-controlled.
- **Attention Amber**: Incomplete data, waiting connectors, uncertainty, and non-blocking warnings.
- **Incident Red**: High risk, failed checks, destructive actions, and incident severity.

### Neutral

- **Repository Canvas**: Page background and empty workspace regions.
- **Evidence Surface**: Primary panels, dialogs, forms, and ledgers.
- **Carbon Text**: Primary labels and conclusions.
- **Muted Metadata**: Timestamps, provenance, IDs, and helper copy.
- **Rule Border**: The main structural device between rows, sections, and panels.

### Named Rules

**The Evidence Color Rule.** A semantic color is always paired with readable text, an icon, a border, or a state label; hue never carries meaning alone.

**The Connected Truth Rule.** Connected, synthetic, waiting, and unavailable states use explicit labels at the point where the user acts.

## Typography

**Display Font:** System UI with Segoe UI and Noto Sans Thai fallbacks

**Body Font:** System UI with Segoe UI and Noto Sans Thai fallbacks
**Label/Mono Font:** SFMono-Regular, Cascadia Code, Consolas, monospace

**Character:** Native, technical, and quiet. The system stack makes the product feel fast and familiar, while the measurement stack distinguishes hashes, timestamps, IDs, scores, and event payloads.

### Hierarchy

- **Headline** (600, fluid 24–32px, 1.25): Page and incident titles only.
- **Title** (600, 16px, 1.5): Panel headings and major ledger sections.
- **Body** (400, 14px, 1.5): Explanations, evidence statements, and form content; long copy stays below 72 characters per line where possible.
- **Label** (600, 12px, 1.33): Controls, navigation, status metadata, and table headings.
- **Measure** (400–600, 12–14px): Scores, hashes, event IDs, timestamps, and code-adjacent values.

**The Sentence Case Rule.** Use sentence case for controls and headings. Uppercase is reserved for short externally defined identifiers such as DORA or severity codes.

## Layout

The application uses three persistent horizontal layers: a compact global header, a repository-context row, and an underlined repository navigation row. Main content sits in a centered container up to 1280px with 24px desktop gutters. Evidence-heavy views may use the full container but must retain a single clear reading order.

Panels are not a card grid. Prefer issue-style rows, data tables, split inspectors, registered timelines, and bordered sections. Desktop can show a primary ledger beside a narrower inspector. Tablet collapses secondary inspectors below the ledger. Mobile becomes a single column, lets repository navigation scroll horizontally, and raises action targets to at least 44px.

## Elevation & Depth

Surfaces are flat by default. Borders and background contrast provide structure. Shadows are reserved for overlays, menus, drawers, and sticky chrome separation; working panels do not float above the page.

**The Flat Workspace Rule.** If a surface can be separated with one border or a canvas change, do not add a shadow.

## Shapes

Controls and panels use restrained 6px corners. Overlays may use 12px. Pills are limited to small statuses, counters, and branch-like metadata; content panels and buttons never become capsules.

## Components

### Buttons

- **Shape:** Compact rectangle with 6px corners; 32px desktop height and 44px minimum on touch layouts.
- **Primary:** Verified green for user-confirmed creation or save; repository blue is reserved for navigation, focus, and analysis selection.
- **Hover / Focus:** Tonal darkening on hover and a visible 2px blue focus ring with offset.
- **Secondary / Ghost:** Neutral raised canvas, explicit border, and carbon text; destructive actions use red text and border before confirmation.

### Chips

- **Style:** Small bordered labels for severity, confidence, data origin, lifecycle, and counts.
- **State:** Each state includes words or symbols and retains readable contrast in both themes.

### Cards / Containers

- **Corner Style:** Restrained 6px corners.
- **Background:** Evidence surface on repository canvas.
- **Shadow Strategy:** None at rest.
- **Border:** One rule border around a grouped region; internal rows share dividers instead of individual card outlines.
- **Internal Padding:** 16px standard, 8–12px for dense ledger rows.

### Inputs / Fields

- **Style:** Visible label above a 32–36px bordered input with 6px corners.
- **Focus:** Blue border plus 2px focus ring.
- **Error / Disabled:** Inline explanation and state border; disabled controls are never the only explanation.

### Navigation

Global actions stay in the top header. Repository areas use a horizontal underlined navigation with leading icons and optional counts. Settings-style subnavigation may use a labeled vertical list. Current state is expressed with `aria-current` and a strong underline or left inset, not a filled promotional tile.

### Evidence Ledger

Evidence rows expose provenance, time, service, support/counter status, and the claim they affect. Selecting a row opens details without changing the surrounding investigation context.

## Do's and Don'ts

### Do:

- **Do** keep workspace, repository, data origin, and connection health visible near the top of every primary workspace.
- **Do** use bordered ledgers, tables, timelines, and split inspectors for operational data.
- **Do** preserve typed API truth, empty states, loading states, permission states, and retry actions.
- **Do** support English and Thai copy without truncating labels or shrinking readable type.
- **Do** keep keyboard focus and responsive navigation visible.

### Don't:

- **Don't** copy GitHub logos, marks, illustrations, or branded assets.
- **Don't** create a dashboard of unrelated floating metric cards.
- **Don't** use gradients, glassmorphism, glowing panels, or ornamental motion in the working interface.
- **Don't** hide synthetic data, unavailable integrations, or uncertainty behind optimistic status color.
- **Don't** add autonomous deploy, rollback, remediation, or shell-execution controls.
