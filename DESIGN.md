# DeployGuard AI Design System — Investigation Ledger

<!-- impeccable:design-system 3 -->

## Direction Contract

**THESIS:** DeployGuard is an operational investigation ledger where every conclusion can be opened, challenged, and traced. It refuses the generic observability grid of detached metric cards.

**OWN-WORLD:** Cool instrument-paper surfaces in light mode, obsidian glassmorphism with glowing accents in dark mode, carbon ink, blueprint cobalt, signal vermilion, ruled evidence rows, registered graph lines, square status marks, and compact laboratory annotations inspired by Magic UI design aesthetics.

**STORY:** Select a change, inspect its computed risk and dependency propagation, replay the incident, compare ranked hypotheses, then record a human verdict.

**FIRST VIEWPORT:** A narrow change rail anchors the left; the central registered topology is the dominant artifact; a risk ledger and evidence inspector share the right; the incident recorder spans the bottom.

**FORM:** Scientific hypothesis ledger with a surface/X-ray evidence reveal and Magic UI glowing node topography.

## Magic UI Aesthetic Enhancements

- **Purposeful glass**: `backdrop-filter: blur(18px) saturate(145%)` is reserved for the fixed command rail and sticky command bar. Working panels stay opaque for evidence readability.
- **Instrument illumination**: Selected graph nodes, focus rings, and active paths receive restrained cobalt illumination; state surfaces use solid semantic tints rather than neon halos.
- **Micro-interactions**: 160–220ms control and selection transitions use exponential ease-out. Incident replay is the only continuous authored motion.

- Mode: Operate.
- Scene: an on-call engineer investigating on a laptop or operations display in a mixed-light office.
- The app follows the user’s saved or system theme. Obsidian mode supports mixed-light on-call work; the cool low-glare light mode preserves dense evidence legibility and useful captures.

## Color Strategy

Restrained, with semantic color reserved for state.

Light mode:

- `--canvas`: `#eef2f7`; `--surface`: `#ffffff`; `--surface-subtle`: `#f4f7fb`.
- `--ink`: `#111827`; `--ink-strong`: `#07101e`; `--muted`: `#5b687a`.
- `--line`: `#dbe2ea`; `--line-strong`: `#bfc9d6`.
- `--cobalt`: `#155eef`; `--vermilion`: `#c9362b`; `--amber`: `#9a5b00`; `--green`: `#087f5b`.

Dark mode:

- `--canvas`: `#07101e`; `--surface`: `#0d192b`; `--surface-subtle`: `#111f33`.
- `--ink`: `#edf4ff`; `--muted`: `#98a8bd`; `--line`: `#203049`.
- `--cobalt`: `#6d9cff`; `--vermilion`: `#ff766c`; `--amber`: `#f2bb5d`; `--green`: `#47d6a0`.

State is always paired with a label, shape, or icon.

### Token architecture

The system uses a strict three-layer token model:

1. **Primitive tokens** are fixed palette, type, spacing, radius, and motion values. Feature styles never consume primitives directly.
2. **Semantic tokens** describe purpose, such as `--color-surface`, `--color-text-muted`, `--color-danger`, and `--color-on-danger`. Theme switching happens only at this layer.
3. **Component tokens** define shared geometry and interaction, such as `--component-control-min-height`, `--component-control-radius`, and `--component-focus-width`.

Legacy short names such as `--surface`, `--cobalt`, and `--radius-sm` are compatibility aliases only. New work uses semantic or component tokens, and migrations remove aliases only after every consumer has moved.

Every filled semantic state has a matching theme-aware foreground token: `--color-on-accent`, `--color-on-success`, `--color-on-warning`, and `--color-on-danger`. Never hard-code white or near-black text on a semantic background.

## Typography

- UI family: `"Segoe UI Variable", "Noto Sans Thai", "Leelawadee UI", Tahoma, sans-serif`.
- Measurement/code family: `"Cascadia Code", "SFMono-Regular", Consolas, monospace`.
- The stable compact scale is `--type-2xs` (12px metadata), `--type-xs` (13px secondary copy), `--type-sm` (14px body), `--type-md` (16px), and `--type-lg` (20px).
- User-facing text never drops below 12px. Use 12px only for terse instrument metadata; explanatory copy starts at 13px.
- Headings remain compact (18–28px), with no decorative display face.
- Evidence IDs, timestamps, commit hashes, and measured values use the measurement family.
- Labels use sentence case; tracked all-caps is limited to compact physical-instrument tags.

## Composition and Surfaces

- Use a fixed 232px command rail plus a sticky 72px command bar and registered evidence workspace. Below 900px the rail becomes an off-canvas drawer.
- Prefer ruled sections, split panes, ledgers, and graph canvases over collections of same-sized cards.
- Borders carry structure; shadows are reserved for the mobile drawer, raised analysis form, and sticky chrome.
- Panel radius is 12px; control radius is 8px. Pills are limited to short statuses.
- Dense content aligns to an 8px base rhythm with 4px substeps.
- Interactive controls use a 44px minimum height and width where the entire surface is actionable. Compact visual treatments must not reduce the hit area.
- Desktop keeps topology, risk, and evidence simultaneously visible; tablet stacks evidence below topology; mobile uses a single active workspace with a persistent context switcher.

## Signature Interaction

The global `Evidence X-ray` switch keeps the topology spatially fixed while changing node annotations from operational status to the exact evidence and score contribution behind each conclusion. Shared geometry must not jump between the two states.

## Components and States

- Workspace scope switcher: exposes the current synthetic repository and scenario from typed API data; repository search and switching stay inside this focused component.
- Workspace activation: a four-step operating ledger for development identity, tenant creation, repository fixture connection, and team invitation. Every substitute is labelled at the point of action.
- Command center: `Ctrl/Cmd + K` opens actual navigation, repository switching, X-ray, and deep-link actions. It never lists unavailable integration or collaboration actions.
- Change queue: selected, reviewed, high-risk, incomplete-data, and deployment states.
- Risk ledger: overall score plus weighted dimensions, each with its reason and data-quality marker.
- Topology node: service, database, queue, or external dependency; selected and impacted states use both shape and label.
- Hypothesis row: rank, confidence band, evidence count, counter-evidence count, and human verdict.
- Incident recorder: deploy, symptom, alert, mitigation, recovery, and feedback events.
- Every action supports default, hover, keyboard focus, active, disabled, loading, error, and empty states.
- Loading uses registered skeleton rows; errors state the failure and recovery action.

### Component styling contract

- Global CSS owns tokens, reset, document base, and primitives only. New feature/layout components colocate their styles with the Angular component.
- Each element gets one stable semantic class. State uses `aria-*`, `data-state`, or a component-level CSS custom property instead of stacked `.is-*` classes.
- Feature selectors must stay flat: no selector may depend on more than one DOM relationship, and new components should not require descendant selectors for state.
- Shared primitives expose `data-variant` and `data-size` instead of multiplying BEM modifier classes. Existing modifier classes are migration aliases, not the target API.
- Feature styles consume semantic and component tokens only. Literal color, typography, control-height, radius, focus, and transition values are not accepted in new component CSS.
- React Bits is an interaction reference, not a dependency. Stepper, Animated List, and Spotlight ideas may be translated to Angular/CSS, but React is not added as a second runtime.

### Stylesheet ownership and migration

- `frontend/src/styles.scss` is the source of truth for tokens, reset, document defaults, accessibility primitives, and shared controls.
- `frontend/src/app/app.scss` owns application shell layout and chrome.
- Feature component styles own their workspace layout and local presentation.
- The current global investigation and change-risk rules are legacy migration debt. Move them feature by feature; do not add new feature selectors to the global stylesheet.

## Motion

- 160–220ms state transitions with exponential ease-out; do not animate layout dimensions.
- The one authored motion is incident replay: a time cursor advances across the recorder while affected graph edges illuminate in causal order.
- Command search uses a single short list-insertion sequence inspired by React Bits Animated List; all other motion communicates selection or state change.
- `prefers-reduced-motion` disables replay animation and reveals the final state immediately.
- Reduced motion is selective: stop continuous spinner, shimmer, and edge-flow animation; retain an 80ms state-change transition so focus and selection feedback do not disappear. Never use a blanket `0.01ms` override.

## Accessibility

- Minimum 4.5:1 text contrast and 3:1 large-text/UI contrast.
- Visible 2px focus outline with offset.
- Minimum 44px pointer targets for every action on coarse-pointer and mobile layouts.
- Filled semantic surfaces always use their `--color-on-*` foreground token and are verified in both themes.
- Dialogs and off-canvas navigation trap focus, close with Escape, restore focus to the trigger, and keep background content inert while open.
- Composite widgets implement their declared keyboard model. Do not add `listbox`, `option`, or `listitem` roles to native buttons unless the complete interaction pattern exists.
- Forms expose visible validation copy, `aria-invalid`, and `aria-describedby`; a disabled submit button is not the only error signal.
- SVG topology includes a text summary and keyboard-selectable services.
- Risk is never represented by hue alone.

## Content Integrity

- Seed data is labeled `Synthetic demo`.
- Never display invented customers, measured accuracy, or operational savings.
- Hypotheses use calibrated language: “likely”, “possible”, “unsupported”, and “contradicted”.
