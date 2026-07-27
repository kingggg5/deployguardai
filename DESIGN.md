# DeployGuard AI Design System — Investigation Ledger

<!-- impeccable:design-system 3 -->

## Direction Contract

**THESIS:** DeployGuard is an operational investigation ledger where every conclusion can be opened, challenged, and traced. It refuses the generic observability grid of detached metric cards.

**OWN-WORLD:** Cool instrument-paper surfaces in light mode, obsidian glassmorphism with glowing accents in dark mode, carbon ink, blueprint cobalt, signal vermilion, ruled evidence rows, registered graph lines, square status marks, and compact laboratory annotations inspired by Magic UI design aesthetics.

**STORY:** Select a change, inspect its computed risk and dependency propagation, replay the incident, compare ranked hypotheses, then record a human verdict.

**FIRST VIEWPORT:** A narrow change rail anchors the left; the central registered topology is the dominant artifact; a risk ledger and evidence inspector share the right; the incident recorder spans the bottom.

**FORM:** Scientific hypothesis ledger with a surface/X-ray evidence reveal and Magic UI glowing node topography.

## Magic UI Aesthetic Enhancements

- **Glassmorphism & Radial Backdrops**: Translucent card panels (`backdrop-filter: blur(14px)`), ambient radial illumination, and sleek dark mode theme (`#0B0F17` obsidian background with `#161F30` glass surfaces).
- **Glowing Accent Borders**: Glowing focus indicators and animated risk status halos for critical services and topology nodes.
- **Micro-Interactions**: Dynamic hover lifts, animated progress meters, pulsed pulse-rings on critical nodes, and animated timeline scrubber.

- Mode: Operate.
- Scene: an on-call engineer investigating on a laptop or operations display in a mixed-light office.
- The interface uses a light, low-glare foundation so dense evidence remains legible during long sessions and print/PDF captures remain useful.

## Color Strategy

Restrained, with semantic color reserved for state.

- `--canvas`: `#e9ece8` — cool instrument-paper workspace.
- `--surface`: `#f8f9f6` — primary working surface.
- `--surface-strong`: `#ffffff` — selected and editable regions.
- `--ink`: `#17201f` — primary text and graph structure.
- `--muted`: `#5e6966` — secondary text.
- `--line`: `#cbd1cc` — rules and separators.
- `--cobalt`: `#1e5fbf` — current selection, links, and verified evidence.
- `--vermilion`: `#c8422d` — critical risk, contradiction, and destructive state.
- `--amber`: `#a96408` — warning and incomplete evidence.
- `--green`: `#24714d` — healthy, confirmed, and recovered.

State is always paired with a label, shape, or icon.

## Typography

- UI family: `"Segoe UI Variable", "Noto Sans Thai", "Leelawadee UI", sans-serif`.
- Measurement/code family: `"Cascadia Code", "SFMono-Regular", Consolas, monospace`.
- Headings remain compact (18–28px), with no decorative display face.
- Evidence IDs, timestamps, commit hashes, and measured values use the measurement family.
- Labels use sentence case; tracked all-caps is limited to compact physical-instrument tags.

## Composition and Surfaces

- Use a fixed application rail plus a registered evidence workspace.
- Prefer ruled sections, split panes, lists, and graph canvases over collections of same-sized cards.
- Borders carry structure; shadows are reserved for floating overlays only.
- Corner radius is 6–10px. Pills are limited to short statuses and filters.
- Dense content aligns to an 8px base rhythm with 4px substeps.
- Desktop keeps topology, risk, and evidence simultaneously visible; tablet stacks evidence below topology; mobile uses a single active workspace with a persistent context switcher.

## Signature Interaction

The global `Evidence X-ray` switch keeps the topology spatially fixed while changing node annotations from operational status to the exact evidence and score contribution behind each conclusion. Shared geometry must not jump between the two states.

## Components and States

- Change queue: selected, reviewed, high-risk, incomplete-data, and deployment states.
- Risk ledger: overall score plus weighted dimensions, each with its reason and data-quality marker.
- Topology node: service, database, queue, or external dependency; selected and impacted states use both shape and label.
- Hypothesis row: rank, confidence band, evidence count, counter-evidence count, and human verdict.
- Incident recorder: deploy, symptom, alert, mitigation, recovery, and feedback events.
- Every action supports default, hover, keyboard focus, active, disabled, loading, error, and empty states.
- Loading uses registered skeleton rows; errors state the failure and recovery action.

## Motion

- 160–220ms state transitions with exponential ease-out.
- The one authored motion is incident replay: a time cursor advances across the recorder while affected graph edges illuminate in causal order.
- All other motion communicates selection or state change.
- `prefers-reduced-motion` disables replay animation and reveals the final state immediately.

## Accessibility

- Minimum 4.5:1 text contrast and 3:1 large-text/UI contrast.
- Visible 2px focus outline with offset.
- Minimum 44px pointer targets for primary actions.
- SVG topology includes a text summary and keyboard-selectable services.
- Risk is never represented by hue alone.

## Content Integrity

- Seed data is labeled `Synthetic demo`.
- Never display invented customers, measured accuracy, or operational savings.
- Hypotheses use calibrated language: “likely”, “possible”, “unsupported”, and “contradicted”.
