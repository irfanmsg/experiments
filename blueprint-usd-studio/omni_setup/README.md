# Omniverse setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run
`./omni_setup/setup.sh` once to create a project-local `.venv` with the web
app, blueprint/PDF processing, and OpenUSD authoring libraries. This path does
not require an RTX GPU or download any asset packs. Run
`./omni_setup/setup.sh runtime` when RTX rendering, WebRTC streaming, and PhysX
are needed. The runtime is optional so the blueprint-to-USD editor remains
usable while GPU components download or initialize. Both commands use Python
3.10–3.13; this laptop's Python 3.12 is suitable. Set
`BLUEPRINT_STUDIO_PYTHON=3.12` to let uv select that version.

Dependencies live in `pyproject.toml` and exact resolved versions and hashes in
`uv.lock`; the old requirements files have been replaced. Setup uses
`uv sync --locked --inexact`, adding `--extra runtime` for GPU components.
The inexact sync retains an existing runtime when core setup is rerun. Stop the
service before changing its environment. `./run.sh` and the installed systemd
service start the prepared environment directly, without installing packages.

For tests, run `uv sync --locked --inexact --group test`; add `--group browser`
for Playwright checks (Google Chrome must also be installed). Use
`uv run --no-sync python -m pytest -q` to run the prepared environment. Verify
dependency edits with `uv lock --check`; deliberately update with `uv lock`
and commit both project and lock files. All current Python packages, including
the optional NVIDIA wheels, resolve from public PyPI; no inference token is
needed for installation.

The core dependency is NVIDIA's `usd-exchange` 3.0.0. It supplies the `pxr`
modules used to author USD and must not share an environment with `usd-core`.
The optional runtime installs `ovrtx` (RTX renderer), `ovstream` (WebRTC/NVENC),
`ovphysx` (PhysX), which pulls its matching `ovstage` scene runtime, and Warp
for CUDA-frame handoff. These
are currently pre-release NVIDIA libraries. Their public reference repositories
are checked out beside this app under `/home/ovqa/Repos/GitHub/`:

- `usd-exchange` — OpenUSD authoring helpers and examples
- `usd-exchange-samples` — stage, mesh, material, reference, and physics examples
- `ovrtx` — RTX rendering examples
- `ovstage` — shared in-memory USD scene runtime
- `ovstream` — WebRTC server and browser client examples
- `PhysX/ovphysx` — physics API and schemas

The [ovrtx + ovstream Python example](https://github.com/NVIDIA-Omniverse/ovstream/blob/main/examples/python/ovrtx_stream/README.md)
is the reference for passing RTX CUDA frames to WebRTC. Runtime simulation
must register the PhysX schema root with `ovstage.population` before loading
any USD scene, then populate both rendering and physics domains.

NVIDIA's [SimReady Furniture & Misc pack](https://docs.omniverse.nvidia.com/usd/latest/usd_content_samples/downloadable_packs.html)
is stored separately at `/home/ovqa/Repos/OmniverseAssets/` so its large assets
stay out of Git. Keep the extracted directory tree intact. Reference the
top-level `{asset_name}.usd` file for an item from a separate prim in an app
scene; USD will compose its geometry, materials, and physics variants from the
pack's sibling files. The app should expose assets through a gallery instead
of asking users to type file paths.
`./omni_setup/fetch_simready.sh` downloads the pack with resume support, checks
its expected size, SHA-256 (recorded from the official archive downloaded on
2026-09-26), and every ZIP CRC, rejects unsafe paths, then extracts it.
It takes roughly 9 GiB to download; the app starts without it.
The pack's `SimPBR.mdl` imports a sibling `baking_annotations.mdl` that this
archive does not contain. After installing the optional runtime, run
`.venv/bin/python omni_setup/prepare_simready_overlay.py`. This creates an
adjacent, lightweight view at
`/home/ovqa/Repos/OmniverseAssets/SimReady_Furniture_Misc_01_overlay`:
`common_assets`, `common_tools`, and other pack content are relative symlinks;
the four pack MDL files are separate copies; and the missing 1.5 KB MDL module
is copied from the installed `ovrtx` wheel. Neither the archive nor its
extracted directory is modified. The script is idempotent and rejects any
conflicting existing files. Set `BLUEPRINT_STUDIO_ASSET_ROOT` to change the
shared parent of the extracted pack and overlay, or pass `--source` and
`--overlay` explicitly.
An RTX one-frame stream smoke test on this laptop loaded a sofa through the
overlay without MDL import or material errors.

For the furniture gallery, run
`.venv/bin/python omni_setup/build_simready_catalog.py --asset-root /home/ovqa/Repos/OmniverseAssets/SimReady_Furniture_Misc_01_overlay`
to refresh `data/simready_catalog.json`. It records paths relative to the
overlay root and measured X/Y/Z bounds in meters; no models are copied into
the app repository. The overlay depends on the original extracted pack being
present. Generated USD scenes with SimReady references also depend on that
asset library; include/repath those dependencies when moving scenes to a
different machine.

The 2023 source pack opens with USD warnings about an absent thumbnail-rig
`studio_lights.usd` and older crate-file versions. The selected models' default
prims compose with valid geometry and bounds; their source files remain
untouched. A future upgrade can convert copies of those layers if newer OpenUSD
readers stop accepting them.

NVIDIA says Omniverse is freely available for development and production under
its [software license and product terms](https://docs.omniverse.nvidia.com/usd/latest/common/NVIDIA_Omniverse_License_Agreement.html).
`usd-exchange` source is Apache-2.0; the prebuilt RTX/streaming/physics wheels
have NVIDIA-specific terms. Preserve the source asset pack and its notices when
using any models.

For factory and warehouse scenes, NVIDIA's
[SimReady Warehouse 01 pack](https://docs.omniverse.nvidia.com/usd/latest/usd_content_samples/downloadable_packs.html)
adds 139 simulation-ready props (racks, shelving, dock boards, ramps, pallets,
and access equipment). The 14.17 GB archive is kept outside Git beside the
furniture pack. Its 5,019 ZIP entries require about 20.18 GB after extraction.
Run `./omni_setup/fetch_simready_warehouse.sh` to download, verify the pinned
SHA-256 and every ZIP CRC, and extract it. Then make the same non-destructive
MDL overlay and build a measured 14-item factory catalog:

```bash
.venv/bin/python omni_setup/prepare_simready_overlay.py \
  --source /home/ovqa/Repos/OmniverseAssets/SimReady_Warehouse_01 \
  --overlay /home/ovqa/Repos/OmniverseAssets/SimReady_Warehouse_01_overlay \
  --sample-asset Assets/simready_content/common_assets/props/recycledwoodpallet_a01/recycledwoodpallet_a01.usd
.venv/bin/python omni_setup/build_simready_warehouse_catalog.py
```

The warehouse archive has the same missing `baking_annotations.mdl` sibling
dependency as the furniture archive. The overlay fixes this without changing
NVIDIA's extracted files. The app reads
`data/simready_warehouse_catalog.json` for factory and showroom asset
suggestions. The gallery paths depend on the overlay and its adjacent extracted
pack being present at runtime. An RTX one-frame smoke test rendered a storage
rack and long ramp through the overlay without MDL import or material errors.
