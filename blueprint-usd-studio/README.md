# Blueprint Studio

Blueprint Studio is a workflow for turning blueprints and supporting source material into measured, editable **OpenUSD 3D scenes**, with optional **RTX ray-traced rendering** streamed to a browser. The aim is to reconstruct the space accurately, furnish it with physically scaled assets, compare interior designs, and keep every inferred decision open to review.

B1-1502 is the first worked example and regression fixture. It helped establish the measurement, source-review and rendering workflow; the product is intended for other homes, offices, factories and showrooms.

## Workflow

```text
Blueprint + measurements + supporting evidence
                  ↓
Review sources, resolve conflicts, establish scale
                  ↓
Trace and review rooms, walls, doors and windows
                  ↓
Author a metre-based, Z-up OpenUSD scene
                  ↓
Place editable SimReady assets and choose a design
                  ↓
Inspect the ray-traced 3D view → revise → regenerate/export
```

1. **Collect the sources.** Start with a dimensioned floor plan. Use elevations, sections, finish schedules, survey measurements, construction photos and furniture references to fill specific gaps. Record which building, floor, unit and revision each source describes.
2. **Establish scale and source authority.** Prefer relevant documented measurements over apparent image size. Identify the source that governs each decision; keep conflicting dimensions or revisions visible instead of averaging them together. Convert feet and inches explicitly: `metres = feet × 0.3048 + inches × 0.0254`.
3. **Review the reconstruction.** Check room spans, wall boundaries, opening widths, door connections and circulation. Record any inferred height, wall thickness, missing connection or uncertain contour with its source, reason and review status.
4. **Furnish and design.** Place individual referenced assets at their physical size. Use interior references to choose materials, textiles, furniture, art and lighting without silently changing the measured shell.
5. **Render, inspect and iterate.** Generate OpenUSD, explore the RTX view, then edit the saved layout and regenerate. Export the scene and its reconstruction trace so measurements and assumptions remain reviewable.

Supporting evidence has different roles. A finish schedule can establish a floor material; a construction photo can show an opening or unfinished surface; an interior video can suggest a furniture composition. An uncalibrated photo or style reference does not establish room dimensions. Supplied documents also need to be checked for the correct floor and revision.

## What works today, and what is next

| Capability | Current implementation |
| --- | --- |
| Bring your own blueprint | Upload one PDF or image per project; select a PDF page. PNG, JPEG, WebP and TIFF are supported, up to 200 MB. |
| Set scale and trace a plan | Mark one known distance in metres; trace room rectangles/polygons, perimeter, balconies, doors and windows. Image-assisted room suggestions require review. |
| Generate OpenUSD | Author building geometry, openings, PBR finishes, lighting and referenced assets in metres with Z up; export a scene or style variants. |
| Furnish a layout | Add, move, rotate and remove individual objects from the installed SimReady gallery. X/Y controls use metres; rotation uses degrees. |
| Explore the model | Optional RTX/WebRTC viewer with orbit, zoom, top and room views; 720p, 1080p, 1440p and 4K output. |
| Review supporting evidence | The B1-1502 example has a curated multi-file manifest, conflicting-source comparisons, dimension constraints and assumption trace. These are currently example-specific. |
| Apply complete interior schemes | The coordinated schemes and fitted room details currently use the B1-1502 room model. Other uploaded plans have category-based finish presets. |

The next step is to make the demonstrated evidence workflow reusable for arbitrary projects: attach multiple sources, assign their roles and precedence, extract and reconcile dimensions, review proposed geometry and missing details, and apply room-aware schemes to different layouts. **Automatic multi-source reconstruction and arbitrary-layout furnishing are not yet implemented.** The generic upload path currently relies on calibration and reviewed tracing; it does not automatically enforce every printed dimension as the worked example does.

## Editable assets and SimReady

An editable furnishing is a separate object in the layout, rather than furniture baked into a single building mesh. Add an asset from the gallery, click its location on the plan, then use its **X**, **Y** and **Rotation** fields in the placement list to reposition it. **Remove** deletes that placement. Each placement is saved independently and authored as an OpenUSD reference with its own transform. Regenerate the scene to render the changed arrangement.

The importer converts source units and up-axis to the building's metre-based, Z-up coordinates and anchors the geometry bottom to its placement height. Furniture retains its physical size; the importer does not shrink it to fit a room. Original asset files stay unchanged. Scheme-specific upholstery changes are authored in the generated scene.

**Layout editing and physics movement are separate controls.** An object can be positioned in a design while remaining static during simulation. **Dynamic physics**, a starting height and **Simulate physics** enable dynamic behaviour in the live view. Authored collision variants are used where available; otherwise the app can use a bounds collider. Using a SimReady source asset does not certify the entire generated building or every procedural furnishing as simulation-ready for every application.

The placement controls currently edit imported gallery assets. Generated cabinetry, beds, curtains, rugs and other procedural scheme details are not yet individually editable through those controls. Converting that generated furnishing layer into separately editable placements is part of the generic workflow roadmap.

The browser editor operates on the saved plan; regenerate and reopen the live view to inspect edits. Direct asset manipulation inside the streamed 3D view is not implemented. Source packs and material dependencies must remain available when a referenced USD scene is moved to another machine.

## Interior styles

A **finish preset** changes surface materials and lighting. An **interior scheme** coordinates those finishes with textiles, decor, furniture treatment and lighting fixtures. The current example offers:

- **Linen & light timber** — cream upholstery, pale timber, sheer curtains and a neutral rug.
- **Warm evening lounge** — beige/olive upholstery, graphic art and pools of warm lamp light.
- **Botanical cane & terracotta** — cane details, woven shades, planting and terracotta accents.
- **Contemporary Indian** — geometric textile borders, crafted timber lattice, brass pendant shades and ochre/indigo accents.
- **Bohemian** — layered patterned rugs, knotted textile wall decor, woven shades and mixed indigo/terracotta textiles.

Contemporary Indian is a named interpretation informed by a documented Indian design project, not a claim to represent every Indian tradition. Regional directions from the supplied reel remain separate references for future schemes. Bohemian adds modeled textile layers and woven decor. The reviewed references, observed features and proposed additions are recorded separately in [the interior reference ledger](docs/interior-references.md).

For supported layouts, select a scheme, choose **Create 3D scene**, then open the live RTX view. A scheme card receives an actual rendered preview after its stream initializes; editing the plan invalidates outdated previews. Exact products, decorative dimensions, colours and lighting are design assumptions, not measurements recovered from reference images.

## Run locally

Python 3.10–3.13 is required. The core editor and USD exporter do not require an RTX GPU or asset downloads.

```bash
git clone https://github.com/irfanmsg/experiments.git
cd experiments/blueprint-usd-studio
./omni_setup/setup.sh
./run.sh --port 8001
```

Open [http://127.0.0.1:8001](http://127.0.0.1:8001). Port 8001 is used on the development machine because another app occupies port 8000. For optional GPU rendering, WebRTC streaming and PhysX, install the runtime and restart Studio:

```bash
./omni_setup/setup.sh runtime
./run.sh --port 8001
```

The live renderer requires a compatible NVIDIA GPU/driver and the runtime dependencies. The first shader build may take several minutes. [Omniverse setup](omni_setup/README.md) describes dependencies and asset preparation; [streaming setup](streaming/README.md) covers the renderer and network configuration.

To make the editor reachable on a trusted local network, use `./run.sh --lan --port 8001`. The app has no login yet. Internet use requires HTTPS, authentication, routing and an appropriate STUN/TURN service; do not expose the local editor or signaling port directly. The live view opens through the address supplied by Studio.

### Optional SimReady library

Keep downloaded assets outside Git. Set a shared asset location explicitly, since some download helpers retain a machine-specific default:

```bash
export BLUEPRINT_STUDIO_ASSET_ROOT="$HOME/Repos/OmniverseAssets"
./omni_setup/fetch_simready.sh
.venv/bin/python omni_setup/prepare_simready_overlay.py
./run.sh --port 8001
```

The furniture pack download is about 9 GiB. Overlay preparation requires the installed RTX runtime and preserves the original pack. The gallery shows installed, catalogued assets; basic USD export works without them. An optional warehouse pack and catalog-refresh instructions are documented in [omni_setup/README.md](omni_setup/README.md). NVIDIA's asset and runtime terms apply separately to those downloads.

## Use your own blueprint

1. Upload a PDF or image and choose the relevant page.
2. Enter a printed distance **in metres**, then mark its two endpoints. Convert feet/inches before entering the value; the current field does not parse imperial notation.
3. Trace the spaces, perimeter and openings. Review any suggested rooms and set opening widths and wall height. A distorted scan may need more than one measurement to validate the result.
4. Choose the building category, add available furnishings, and choose a finish preset.
5. Generate the scene, download USD or open the live view at the desired resolution. Review scale, access and placement before refining the layout.

A ray-traced view is a way to inspect the authored scene, not proof that its source geometry is complete or construction-verified. Camera navigation currently does not stop at walls. Exact wall construction, heights and other undocumented details require confirmation.

## Worked example: B1-1502

Use **Open the B1-1502 flat example** in Studio, or visit [the example link](http://127.0.0.1:8001/?example=b1-1502). This fixture demonstrates agreement-based room dimensions, doors and shared walls, source comparisons, fitted details, physical furniture scale and traceable interior schemes.

The agreement's unit plan governs this example; finish specifications, approved comparison drawings, the furnished brochure and construction photos have distinct recorded roles. Its assumptions and source conflicts remain visible in **Review reconstruction assumptions** and **Download reconstruction trace**. See [the example notes](data/b1_1502/README.md), [source manifest](data/b1_1502/reference_manifest.json), [dimension comparisons](data/b1_1502/source_comparison.json) and [construction-photo review](docs/construction-photo-review.md).

To regenerate the standalone example and its style pack:

```bash
.venv/bin/python build_b1_1502.py
```

Outputs go under `output/b1-1502/`, including `B1-1502.usd` and `B1-1502-style-pack.zip`. The pack contains an `architecturalStyle` variant set and referenced style files. These scripts and fixture-specific geometry are a starting point for generalization, not requirements for a new uploaded project.

## Implementation and verification

The authoring path uses NVIDIA [usd-exchange](https://github.com/NVIDIA-Omniverse/usd-exchange). The optional renderer combines [ovstage](https://github.com/NVIDIA-Omniverse/ovstage), [ovrtx](https://github.com/NVIDIA-Omniverse/ovrtx), [ovstream](https://github.com/NVIDIA-Omniverse/ovstream) and [ovphysx](https://github.com/NVIDIA-Omniverse/PhysX/tree/main/ovphysx). Core and runtime dependencies are pinned separately under `omni_setup/`; do not install `usd-core` into the same environment as `usd-exchange`.

```bash
.venv/bin/python -m pytest -q
node --check app/static/app.js
node tests/check_stream_link.js
```

The live checks need Playwright, local Google Chrome and a running stream. They inspect actual WebRTC frames and write screenshots to `output/qa/`:

```bash
.venv/bin/python tests/check_live_view.py --width 3840 --height 2160
.venv/bin/python tests/check_interior_scheme_cards.py --project PROJECT_ID
.venv/bin/python tests/check_asset_editing.py
```

The first command expects a 4K stream; omit the size arguments for the default HD check. The second checks rendered scheme cards after at least one scheme has been streamed. The third creates a scratch project and verifies adding, moving, rotating and removing an installed asset through the editor and exported USD, without resizing it. The detailed reconstruction assertions currently use the B1-1502 fixture. Local GPU/browser testing does not establish compatibility with every GPU or remote client.
