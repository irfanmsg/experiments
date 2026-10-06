# Source-grounded B1-1502 implementation plan

> For agentic workers: use subagent-driven development; keep file ownership separate.

**Goal:** Reconstruct the demarcated B1-1502 agreement layout in metres, with specified finishes, recognizable furnishings, and reviewable evidence.

**Architecture:** Reuse the dimensioned plan builder, USD authoring helpers and native review panels. Keep source dimensions, alternative revisions, furnishing assumptions and physical asset measurements separate in the trace.

**Tech stack:** Python, Shapely, OpenUSD, existing SimReady assets, RTX/WebRTC, native browser controls and Playwright.

**Spec:** Supplied drawings in `/localhome/local-mirfan/Documents/PWC_B1_1502`; agreement PDF pages 35 (unit layout) and 28 (Annexure F); user requests in this session.

## Constraints and review focus

- One USD unit is one metre; preserve imported physical sizes and original source layers.
- Agreement metric dimensions govern this reconstruction. Keep approved-plan differences visible.
- Printed dimensions must agree with polygons; actual door jambs must contact walls and toilets must be accessible.
- Finish specifications are evidence; unprinted sizes, offsets, heights and furniture forms remain explicit assumptions.
- Preserve existing user projects and assets; test editor placement and the physics-enabled 4K render.

## Tasks

- [x] Geometry agent: verify all agreement labels, rebuild v3 rooms and doors, check dimensions, contact and physical connectivity.
- [x] Presentation agent: add the specified-finish preset, room-specific surfaces, kitchen and bathroom fixtures, beds and wardrobes; verify physical fit.
- [x] Reference agent: record all supplied files, hashes, applicability, dimension conflicts and finish specifications; update usage documentation.
- [x] Root: integrate reference review/trace, make the preset labels honest, align real SimReady furniture to the illustrated layout, and preserve older projects.
- [x] Root: run focused and full checks, use Playwright for editor placement and 4K playback, inspect rendered rooms, and leave the corrected app running.

The user requested intermittent checkpoint commits on 5 October 2026. Commit verified chunks with Irfan's configured author identity.
