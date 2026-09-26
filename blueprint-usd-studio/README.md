# Blueprint Studio

Blueprint Studio turns a reviewed PDF or image floor plan into a metre-based OpenUSD scene. It has a guided browser editor for buyers and planners: upload a drawing, mark one known distance, review or trace spaces and openings, choose a style, generate USD, and open a live RTX/WebRTC view on another screen.

The app accepts drawings of homes, factories, offices, showrooms, and other structures. A buyer can upload a PDF or image, mark one printed dimension, and outline the perimeter or rooms with simple clicks. Image-assisted room suggestions are deliberately reviewable; scans with folds, small labels, or incomplete wall lines still need a person to confirm the geometry. The style picker offers home, factory, office, and showroom presets. Styles preserve the traced layout and change PBR finishes, glazing, and lighting.

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
cd /home/ovqa/Repos/GitHub/blueprint-usd-studio
./run.sh
```

The dependencies are already installed on this laptop. On a fresh machine, run `./omni_setup/setup.sh runtime` first. Open `http://127.0.0.1:8000`. For the dimensioned flat example, click **Open the B1-1502 flat example**, or open `http://127.0.0.1:8000/?example=b1-1502`. The editor can be made available to other machines on the local network with `./run.sh --lan`; it has no login yet, so use that option only on a network you trust. The RTX browser view launched from the app binds to the laptop's LAN address and streams with WebRTC. HD (1280×720) is the default; the viewer fits the workspace without stretching and offers an original-size mode. Standard quality (640×360) remains available for lower bandwidth. The first shader build may take several minutes. **Simulate physics** is optional in the live view; authored static colliders remain fixed, while dynamic objects can move.

Asset downloads are optional for basic USD export. `./omni_setup/fetch_simready.sh` retrieves NVIDIA's Furniture & Misc pack, and `./omni_setup/fetch_simready_warehouse.sh` retrieves Warehouse 01, both outside this Git repository. This laptop has both extracted packs and lightweight RTX-compatible overlays. The **Add SimReady objects** gallery offers 11 home/office furnishings and 14 factory/warehouse items, with measured model bounds. Placements keep NVIDIA's source materials; the app selects authored collision variants where available and builds a bounds collider where needed. Select **Movable in simulation**, set a starting height, and enable **Simulate physics** to see an object move. Referenced assets need the local pack and overlay when the authored USD is moved to another machine. [omni_setup/README.md](omni_setup/README.md) describes the asset setup.

For Internet viewing, the current LAN stream needs HTTPS, authentication, network routing, and an appropriate TURN server. Set `OVSTREAM_ICE_SERVERS` for an existing STUN/TURN service as described in [streaming/README.md](streaming/README.md). Do not expose the unauthenticated local editor or signaling port directly to the public Internet.

## B1-1502 deliverables

The B1-1502 example uses **one USD unit = one meter**. Printed dimensions
now drive its geometry: 18 rectangular spaces have exact clear floor spans,
and the two irregular balconies enforce their printed span and average depth.
For example, the kitchen is 2.75 × 4.12 m and the outer upper bedroom is
3.96 × 3.40 m. Walls are placed outside the clear spaces, shared wall solids
are deduplicated, and door openings are cut through those solids. Export
validation rejects a dimensioned room whose vertices disagree with its labels.

`data/b1_1502/trace.py` preserves the old pixel trace as `raster_trace.json`,
then rebuilds `plan.json` through the dimension-driven layout. Changing the
60.4 pixels/meter raster calibration no longer changes the reconstructed room
sizes. Existing unedited B1 example projects migrate when loaded; geometry
edits are preserved and require opening the updated example instead.

The approved metric plan remains the dimensional source. Pages 32–35 of
`Sales Presenter Mergred Web.pdf` were reviewed: page 32 is the detailed 02/05
unit, page 33 the typical floor, page 34 the first floor, and page 35 refuge
floors 8/13/18. Brochure feet/inches are converted with 0.3048 m/ft and
0.0254 m/in. Differences from the approved drawing are recorded in
[`source_comparison.json`](data/b1_1502/source_comparison.json).

Wall thickness (0.15 m), height (2.8 m), orthogonal alignment and detailed
balcony curves remain assumptions. Printed average balcony depths do not
uniquely determine the curved boundary. The modeled gross slab is approximately
222.45 m²; the approved 207.77 m² net-area schedule remains separate source
metadata. The published area schedule and room/average-depth labels do not
establish a single exact surveyed perimeter; we do not globally shrink rooms
to force these different measurements to agree.

Regenerate the ready-to-open binary USD and five home style variants:

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

The scene is a dimension-driven architectural visualization with illustrative furnishings,
not a finished photorealistic interior or a construction-verified model. It has
no ceilings or fully detailed kitchen/bathroom fit-out. Room camera movement
does not yet stop at walls. Room spans are constrained; exact wall construction, relative offsets and balcony profiles still need field confirmation.
