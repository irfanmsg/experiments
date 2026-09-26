# Live RTX/WebRTC view

`run.py` opens a generated USD scene, adds an automatically framed camera and
render product in a temporary wrapper layer, and streams the result from this
laptop through NVIDIA `ovstage`, `ovrtx`, and `ovstream`. The original USD is
never edited. The scene-preparation step runs in a separate Python process so
the classic `pxr` authoring bindings do not share a process with the OV runtime.

Install the optional runtime into the application's shared environment:

```bash
./omni_setup/setup.sh runtime
```

Start a stream from the project root:

```bash
.venv/bin/python streaming/run.py --usd output/<project-id>/<style>.usda
```

The command emits JSON status lines (`loading`, `rendering_first_frame`,
`ready`, `client_connected`, `running`, `stopped`, or `error`) alongside library
diagnostics. The first RTX frame may spend several minutes compiling shaders.
`status=ready` includes `local_url`, `lan_url`, the TCP signaling port, and the
UDP media port. Open the
`lan_url` from a Chromium browser on the same network. The viewer connects
automatically and plays silently so browser autoplay restrictions do not block
the picture. The **Live** indicator appears when video playback starts. If a
connection fails, use **Connect** to retry.
The browser page fills in the laptop hostname automatically. The overview stays
still until you drag it. Scroll to zoom, use **Top view** to match the drawing's
orientation, or select a room and choose **Eye level**. **Reset view** returns to
the whole building. Eye-level scroll moves the camera and does not enforce wall
collisions. **Drawing + walls** overlays the traced wall segments on the original
scan when calibration is available. **Original size** and **Full screen** control
the display size; the default fits the available workspace without stretching.
The app defaults to 1280×720 HD. Stop the process with Ctrl+C.

Useful options:

```bash
.venv/bin/python streaming/run.py --usd output/<project-id>/<style>.usda \
  --signal-port 49100 --media-port 47998 --http-port 8088 \
  --width 1280 --height 720 --fps 30
```

`--prepare-only` validates USD geometry and camera framing without loading the
GPU. `--max-frames 5` starts the renderer and WebRTC server, renders five frames,
and exits for a local smoke test. TCP `49100` handles signaling, UDP `47998`
handles media, and TCP `8088` serves the browser page; the host firewall must
allow them for a separate machine. WebRTC can use additional dynamic UDP ports.
For wider network topologies, `OVSTREAM_ICE_SERVERS` accepts entries in NVIDIA's
documented `stun:host:port|turn:host:port,user,pass` form. Run the page behind
authenticated HTTPS and provide a suitable STUN/TURN service for Internet
access; these are deployment choices, not configured by this local launcher.

Physics is opt-in. Add `--physics` to populate rendering and collision data in
the shared `ovstage` scene, step NVIDIA `ovphysx`, and publish simulated rigid
body transforms back to the rendered stage each frame. Add
`--physics-pause-without-client` to keep the simulation paused until a WebRTC
viewer connects. The generated flat has a physics scene and static colliders;
those are useful for collision but will remain still unless the USD also
contains dynamic rigid bodies. Without `--physics`, the live view renders the
USD without advancing its physics scene.

Each SimReady entry in `asset_placements` accepts `physics_mode`: `static`
(default), `dynamic`, or `none`. Static and dynamic placements select the
asset's `PhysicsVariant=RigidBody`, which supplies its authored collision
shapes. An asset without authored collision geometry receives a hidden bounds
proxy; the curated desk is one such asset. Static placements keep the collider
but disable the asset's rigid body. Dynamic placements enable it; an optional
positive `mass_kg` sets the mass when known. The placement's `position[2]` is
its starting height in metres. For example:

```json
{"id":"movable_sofa","asset_path":"/path/under/OmniverseAssets/sofa.usd","position":[2.0,3.0,1.5],"physics_mode":"dynamic","mass_kg":35.0}
```

The SimReady asset path must be an installed asset under the configured asset
root. `physics_mode=none` leaves its default `PhysicsVariant=None` untouched.
These settings author physics in USD; live movement also requires `--physics`
when starting the stream. Furniture friction and restitution are indicative,
not measured properties of the purchased objects.

This viewer uses the whole GPU. It does not enable or require MIG.

## Validation status

Scene preparation passed with all five generated B1-1502 style USD files.
On this RTX 5090 laptop, the contemporary B1-1502 stage rendered and streamed
successfully through `ovrtx` and `ovstream`. A local headless Chrome client
connected to the bundled page, reported a live WebRTC track, and decoded
640×360 video frames of the flat. Delivery to a separate machine on the LAN
has not yet been tested.

With `--physics`, NVIDIA's falling-box sample rendered through the same WebRTC
path and `ovphysx` published 15 simulation attributes across five frames.
The B1-1502 stage with an overlay-backed SimReady sofa also streamed to local
Chrome with `--physics`; its static scene emitted no moving-body attributes,
as expected. The overlay-backed sofa produced no MDL compilation errors.
For a dynamic furniture check, PhysX dropped a SimReady serving bowl onto the
generated static desk bounds collider and it settled at the 0.78 m desk top.
In a separate unobstructed WebRTC test, local Chrome decoded a SimReady sofa
falling from 1.5 m onto the floor while a static chair stayed put. This checks
the visible PhysX-to-RTX handoff as well as the authored collision metadata.
The source pack's older USD crate files emit deprecation warnings. No
separate-machine physics session has been tested.

The browser client in `client/` is adapted from NVIDIA's
[`ovstream/examples/webrtc_client`](https://github.com/NVIDIA-Omniverse/ovstream/tree/main/examples/webrtc_client)
at commit `af7f1f9006d1037a3cc7b8eca73f39a6469b69c2`. The HTML retains
NVIDIA's license header; the bundled JavaScript is accompanied by the upstream
license and third-party notices. Both are subject to
[`PRODUCT_TERMS_OMNIVERSE`](https://github.com/NVIDIA-Omniverse/ovstream/blob/main/PRODUCT_TERMS_OMNIVERSE).
The frame path follows NVIDIA's
[`ovrtx_stream`](https://github.com/NVIDIA-Omniverse/ovstream/tree/main/examples/python/ovrtx_stream)
example, updated for the shared `ovstage` scene model in current `ovrtx`.
