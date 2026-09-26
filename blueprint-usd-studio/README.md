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

The dependencies are already installed on this laptop. On a fresh machine, run `./omni_setup/setup.sh runtime` first. Open `http://127.0.0.1:8000`. For the measured flat example, click **Open the B1-1502 flat example**, or open `http://127.0.0.1:8000/?example=b1-1502`. The editor can be made available to other machines on the local network with `./run.sh --lan`; it has no login yet, so use that option only on a network you trust. The RTX browser view launched from the app binds to the laptop's LAN address and streams with WebRTC. HD (1280×720) is the default; the viewer fits the workspace without stretching and offers an original-size mode. Standard quality (640×360) remains available for lower bandwidth. The first shader build may take several minutes. **Simulate physics** is optional in the live view; authored static colliders remain fixed, while dynamic objects can move.

Asset downloads are optional for basic USD export. `./omni_setup/fetch_simready.sh` retrieves NVIDIA's Furniture & Misc pack, and `./omni_setup/fetch_simready_warehouse.sh` retrieves Warehouse 01, both outside this Git repository. This laptop has both extracted packs and lightweight RTX-compatible overlays. The **Add SimReady objects** gallery offers 11 home/office furnishings and 14 factory/warehouse items, with measured model bounds. Placements keep NVIDIA's source materials; the app selects authored collision variants where available and builds a bounds collider where needed. Select **Movable in simulation**, set a starting height, and enable **Simulate physics** to see an object move. Referenced assets need the local pack and overlay when the authored USD is moved to another machine. [omni_setup/README.md](omni_setup/README.md) describes the asset setup.

For Internet viewing, the current LAN stream needs HTTPS, authentication, network routing, and an appropriate TURN server. Set `OVSTREAM_ICE_SERVERS` for an existing STUN/TURN service as described in [streaming/README.md](streaming/README.md). Do not expose the unauthenticated local editor or signaling port directly to the public Internet.

## B1-1502 deliverables

**Known issue: room geometry does not yet enforce the printed dimensions.**
The USD uses `metersPerUnit = 1.0` (one scene unit is one meter), but the scan
was traced using a single calibration of 60.4 pixels per meter. Printed room
dimensions are metadata, not geometric constraints. For example, the kitchen's
traced polygon averages approximately 2.674 × 3.999 m across opposite edges,
versus the printed 2.75 × 4.12 m; the outer upper bedroom averages
3.944 × 3.163 m, versus 3.96 × 3.40 m. These are polygon measurements, not
verified clear distances between finished wall faces. Dimension-driven
reconstruction remains outstanding; changing the USD unit setting alone will
not fix these discrepancies. Existing tests verify units and selected source
labels, not dimensional agreement of every modeled room.

`data/b1_1502/plan.json` is a trace of the 15th-floor B1 unit 02. The approved architectural sheet labels the rooms, the registered agreement marks this unit's perimeter, and the area schedule prints 172.00 m² carpet, 32.72 m² balcony, and 3.05 m² dry balcony: 207.77 m² total. The raster-traced perimeter measures 207.96 m², a 0.19 m² difference. Printed room dimensions are retained exactly as text metadata in USD. Traced vertices have approximately 0.15–0.25 m uncertainty because the source is a scanned sheet; the 2.8 m wall height and wall thicknesses are visualization assumptions that the app lets you change.

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

The scene is a traced architectural visualization with illustrative furnishings,
not a finished photorealistic interior or a construction-verified model. It has
no ceilings or fully detailed kitchen/bathroom fit-out. Room camera movement
does not yet stop at walls. The scanned-plan uncertainty remains 0.15–0.25 m.
