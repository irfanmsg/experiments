# Blueprint Studio

Blueprint Studio turns a reviewed PDF or image floor plan into a metre-based OpenUSD scene. It has a guided browser editor for buyers and planners: upload a drawing, mark one known distance, review or trace spaces and openings, choose finishes, generate USD, and open a live RTX/WebRTC view on another screen.

The app accepts drawings of homes, factories, offices, showrooms, and other structures. A buyer can upload a PDF or image, mark one printed dimension, and outline the perimeter or rooms with simple clicks. Image-assisted room suggestions are deliberately reviewable; scans with folds, small labels, or incomplete wall lines still need a person to confirm the geometry. The finish picker offers home, factory, office, and showroom presets. Presets preserve the traced layout and change PBR finishes, glazing, and lighting.

## Start on this laptop

This project is published in the `blueprint-usd-studio` folder of
[`irfanmsg/experiments`](https://github.com/irfanmsg/experiments). For a fresh
checkout:

```bash
git clone https://github.com/irfanmsg/experiments.git
cd experiments/blueprint-usd-studio
./omni_setup/setup.sh runtime
./run.sh
```

The existing development checkout on this laptop can also be started directly:

```bash
cd /localhome/local-mirfan/Repos/GitHub/experiments/blueprint-usd-studio
./run.sh --port 8001
```

The dependencies are already installed on this laptop; port 8000 is occupied by another app, so Studio uses `http://127.0.0.1:8001`. On a fresh machine, run `./omni_setup/setup.sh runtime` first. For the dimensioned flat example, click **Open the B1-1502 flat example**, or open `http://127.0.0.1:8001/?example=b1-1502`. The editor can be made available to other machines on the local network with `./run.sh --lan --port 8001`; it has no login yet, so use that option only on a network you trust. The RTX browser view launched from the app binds to the laptop's LAN address and streams with WebRTC. The quality picker offers 720p (default), 1080p, 1440p and 4K (3840×2160); the viewer fits the workspace without stretching and offers an original-size mode. The API retains 640×360 only for backward compatibility. The first shader build may take several minutes. **Simulate physics** is optional in the live view; authored static colliders remain fixed, while dynamic objects can move.

Asset downloads are optional for basic USD export. `./omni_setup/fetch_simready.sh` retrieves NVIDIA's Furniture & Misc pack outside this Git repository. This laptop has FurnitureMisc01 and its RTX-compatible overlay installed under `/localhome/local-mirfan/Repos/OmniverseAssets`: the gallery offers 11 home/office objects, and the sample B1 layout contains 15 placements. Warehouse 01 is an optional separate download via `./omni_setup/fetch_simready_warehouse.sh`. Gallery availability depends on installed packs.

Placements convert source units and up-axis to the metre-based, Z-up building, preserve source materials and anchor each geometry bottom to its placement height. Furniture keeps its physical size; it is not resized to fit rooms. The app selects authored collision variants where available and builds a bounds collider where needed. Select **Movable in simulation**, set a starting height, and enable **Simulate physics** to see an object move. Referenced assets need the local pack and overlay when the authored USD is moved to another machine. [omni_setup/README.md](omni_setup/README.md) describes the asset setup.

For Internet viewing, the current LAN stream needs HTTPS, authentication, network routing, and an appropriate TURN server. Set `OVSTREAM_ICE_SERVERS` for an existing STUN/TURN service as described in [streaming/README.md](streaming/README.md). Do not expose the unauthenticated local editor or signaling port directly to the public Internet.

## B1-1502 deliverables

The B1-1502 example uses **one USD unit = one meter**. Its agreement v3 layout
uses printed metric clear spans and the balconies' printed span/average depth.
For example, the kitchen is 2.75 × 4.12 m and the outer upper bedroom is
3.96 × 3.40 m. Walls are placed outside the clear spaces, shared wall solids
are deduplicated, and door openings are cut through those solids. Export
validation rejects a dimensioned room whose vertices disagree with its labels.

`data/b1_1502/trace.py` preserves the old pixel trace as `raster_trace.json`,
then rebuilds `plan.json` through the dimension-driven layout. Changing the
60.4 pixels/meter raster calibration no longer changes the reconstructed room
sizes. Unedited raster and v1 B1 examples migrate to agreement v3 geometry when loaded, moving furniture with its room without changing object size. Existing v2 projects remain preserved and show an older-reconstruction notice; open the updated example separately. Edited older geometry is rejected without changing its saved project;
open the updated example separately to use the corrected reconstruction.

**Reconstruction review** in the editor and live viewer compares printed room
dimensions with current geometry, records door connections and separates source
evidence from assumptions. **Download reconstruction trace** exports the source
references, estimated parameters, scale audit and asset import measurements as
JSON. USD exports also retain this metadata.

The primary layout is **Miami PWC House Documents.pdf, page 35, Annexure G**:
the registered metric plan specifically demarcates B1-1502. It includes the
powder room and the direct bedroom-to-toilet connection omitted or changed in
the approved typical-floor sheet. **Page 28, Annexure F** supplies the finish
schedule. The **B1-1502 specified finishes** preset (`home_specification`) uses
wood in the master bedroom, vitrified tiles in other dry rooms and matte tiles
in wet spaces, with ceramic bathroom dado up to 2.1336 m. Colours, the selected
tile-size option and fixture models remain illustrative.

All nine supplied files, checksums, relevant pages and roles are catalogued in
[`reference_manifest.json`](data/b1_1502/reference_manifest.json), using portable
filenames; the local originals are under `~/Documents/PWC_B1_1502`.
`B1-Building-3.pdf`, page 1 / sheet 63/69, is the approved floor-15 comparison.
`B1-Building-1.pdf`, page 1 / sheet 60/69, supplies the RERA area schedule;
`B1-Building-5.pdf` is its exact duplicate. The second-floor and refuge sheets
are excluded from apartment geometry; `A6-A7-B1_Layout_Plan.pdf` gives site context.
`Layout.jpeg` and brochure pages 32–33 guide furniture and fixture placement.
Their feet/inches labels are converted with 0.3048 m/ft and 0.0254 m/in and kept
separate from geometry in
[`source_comparison.json`](data/b1_1502/source_comparison.json). Brochure pages
34–35 depict the first floor and refuge floors 8/13/18, rather than floor 15.
The supplied files establish differing documented layouts; their supersession
and the actual built layout remain unverified.

Wall thickness (0.15 m), height (2.8 m) and orthogonal alignment remain
assumptions. Balcony profiles use the traced drawing contours, adapted to the
inferred facade and printed span/average depth; their registration and exact
curves remain provisional. The approved 207.77 m² RERA area total remains separate source
metadata. The published area schedule and room/average-depth labels do not
establish a single exact surveyed perimeter; we do not globally shrink rooms
to force these different measurements to agree.

Regenerate the ready-to-open binary USD and home style variants:

```bash
.venv/bin/python build_b1_1502.py
```

The results are `output/b1-1502/B1-1502.usd` and `output/b1-1502/B1-1502-style-pack.zip`. With the SimReady pack installed, the script also exports `output/b1-1502/B1-1502-furnished.usd` as an illustrative 12-object layout. The ZIP includes `all_styles.usda` with an `architecturalStyle` variant set and its referenced style files. [data/b1_1502/README.md](data/b1_1502/README.md) describes the source pages, dimensions, and confidence in more detail.

## Libraries and checks

The authoring path uses NVIDIA [usd-exchange](https://github.com/NVIDIA-Omniverse/usd-exchange) to create a metre-based OpenUSD stage. The optional live runtime composes [ovstage](https://github.com/NVIDIA-Omniverse/ovstage), [ovrtx](https://github.com/NVIDIA-Omniverse/ovrtx), [ovstream](https://github.com/NVIDIA-Omniverse/ovstream), and [ovphysx](https://github.com/NVIDIA-Omniverse/PhysX/tree/main/ovphysx). Official reference repositories are cloned as siblings of this app, with no modifications to those clones. SimReady assets come from NVIDIA's [downloadable packs](https://docs.omniverse.nvidia.com/usd/latest/usd_content_samples/downloadable_packs.html) and have separate [NVIDIA terms](https://docs.omniverse.nvidia.com/usd/latest/common/NVIDIA_Omniverse_License_Agreement.html).

Run `.venv/bin/pytest -q` for plan, unit-scale, USD, style-variant, and opening checks. `node --check app/static/app.js` verifies browser script syntax. The RTX/WebRTC path was tested with a generated B1-1502 scene on this laptop's GPU and a local Chrome browser; another physical machine has not yet been tested.

### Live viewer acceptance checks

Run `.venv/bin/python tests/check_live_view.py` against the running HD stream
on this laptop (requires `pip install playwright` and local Google Chrome).
It checks real WebRTC playback, desktop/mobile sizing, drawing comparison, room
cameras, mouse rotation and zoom, and full screen. Screenshots are written to
`output/qa/`. Geometry and camera regression checks run with
`.venv/bin/python -m pytest -q`.

The scene follows source room dimensions, door connections and specified finish
categories, while exact materials, lighting, door swing details and furniture
placements remain illustrative. It does not yet provide a construction-verified
or finished photorealistic interior, ceilings or fully
detailed kitchen/bathroom fit-out. Room camera movement
does not yet stop at walls. Room spans are constrained; exact wall construction, relative offsets and balcony profiles still need field confirmation.

The eleven JPEGs in `Under_Construction` were individually reviewed: eight construction exteriors and three builder sales-office site-model photos. Their hashes and roles are included in the reference manifest. Several show floor 15, but tower/unit identity and metric calibration are not established. They guide qualitative exterior review and do not override apartment dimensions or specified finishes. See [construction-photo-review.md](docs/construction-photo-review.md).

The supplied Instagram reel/profile and three primary designer projects were inspected for decor inspiration. Observed details and proposed applications are recorded in [interior-references.md](docs/interior-references.md). Current cards are finish presets; they do not claim to deliver complete regional interior designs.
