"""Installed metadata and a source-grounded API map, with explicit observations.

This module never imports the GPU runtime or pxr. The stream process must keep
classic pxr isolated in its scene-preparation subprocess.
"""

from datetime import datetime, timezone
import hashlib
from importlib import metadata
from pathlib import Path
import sys


_BUNDLE = Path(__file__).resolve().parents[1] / 'streaming/client/omniverse-webrtc-streaming-library.js'
_PACKAGES = (
    ('usd_exchange', 'USD Exchange', 'usd-exchange', False),
    ('ovstage', 'Omniverse stage population', 'ovstage', True),
    ('ovrtx', 'Omniverse RTX rendering', 'ovrtx', True),
    ('ovstream', 'Omniverse WebRTC server', 'ovstream', True),
    ('ovphysx', 'Omniverse PhysX', 'ovphysx', True),
    ('warp', 'Warp CUDA frame transfer', 'warp-lang', True),
)

# These are source mappings, not evidence of execution. Observations are added
# only after the corresponding operation returns successfully.
_ACTIONS = (
    ('usd_authoring', 'Build or regenerate the USD scene', ['usd_exchange', 'openusd'],
     ['usdex.core.createStage', 'UsdGeom.Mesh.Define', 'UsdGeom.Cube.Define'],
     'app/usd_builder.py:build_usd', None),
    ('asset_import', 'Reference and place a USD asset', ['openusd'],
     ['Usd.Stage.Open', 'Usd.References.AddReference', 'UsdGeom.Xformable.AddScaleOp', 'UsdGeom.BBoxCache.ComputeRelativeBound'],
     'app/usd_builder.py:build_usd', 'A scene contains imported USD assets.'),
    ('scene_preparation', 'Prepare the render camera and product', ['openusd'],
     ['Usd.Stage.Open', 'UsdGeom.Camera.Define', 'UsdRender.Product.Define', 'UsdRender.Var.Define'],
     'streaming/prepare_scene.py:prepare_scene', 'A streaming scene is prepared.'),
    ('stage_population', 'Populate the native rendering stage', ['ovstage', 'ovrtx'],
     ['ovstage.Stage', 'ovstage.population.open_usd', 'ovrtx.Renderer.attach_ovstage', 'ovstage.Stage.advance_write_floor'],
     'streaming/run.py:_render', 'An RTX session starts successfully.'),
    ('camera_update', 'Apply the interactive camera transform', ['ovstage'],
     ['ovstage.make_dltensor', 'ovstage.Stage.write_attribute'],
     'streaming/run.py:_render', 'A streaming render-loop iteration updates the camera.'),
    ('rtx_render', 'Render and map an RTX frame on CUDA', ['ovrtx', 'warp'],
     ['ovrtx.Renderer.step', 'render_var.map(device=ovrtx.Device.CUDA)', 'warp.from_dlpack'],
     'streaming/run.py:_render', 'An RTX render completes and its frame is mapped.'),
    ('webrtc_stream', 'Submit a CUDA frame to the WebRTC server', ['ovstream', 'warp'],
     ['warp.copy', 'warp.launch', 'ovstream.VideoFrame.from_cuda_array', 'ovstream.CudaSync', 'ovstream.Server.stream_video'],
     'streaming/run.py:_render', 'Frame submission succeeds; this does not prove browser playback.'),
    ('physics_step', 'Step optional PhysX simulation', ['ovphysx', 'ovstage'],
     ['ovphysx.PhysX.attach_ovstage', 'ovphysx.utils.step_and_write_to_ovstage'],
     'streaming/run.py:_render', 'Physics is enabled, and any pause-without-client condition permits stepping.'),
    ('browser_connect', 'Connect the browser to the live stream', ['webrtc_browser'],
     ['AppStreamer.connect', 'StreamType.DIRECT'],
     'streaming/client/index.html:connect', 'The browser reports a successful stream-start callback.'),
)


def runtime_trace(*, executed=(), physics_enabled=False, openusd_version=None):
    """Return JSON-safe metadata without initializing native GPU libraries.

    ``executed`` is for trusted call sites after successful work, never inferred
    from package presence. OpenUSD's version can cross the subprocess boundary
    from ``Usd.GetVersion()``; otherwise only an already-loaded Usd is inspected.
    """
    libraries = []
    for identifier, name, distribution, optional in _PACKAGES:
        try:
            version = metadata.version(distribution)
        except metadata.PackageNotFoundError:
            version = None
        libraries.append({'id': identifier, 'name': name, 'distribution': distribution,
                          'version': version, 'installed': version is not None,
                          'version_source': 'importlib.metadata' if version else 'not installed',
                          'optional': optional})
    usd = sys.modules.get('pxr.Usd')
    if openusd_version is None and usd is not None:
        openusd_version = '.'.join(map(str, usd.GetVersion()))
    libraries.append({'id': 'openusd', 'name': 'OpenUSD (pxr)',
                      'version': openusd_version,
                      'installed': True if openusd_version else None,
                      'version_source': 'pxr.Usd.GetVersion' if openusd_version else
                      'unknown; pxr has not been loaded in the safe authoring process',
                      'optional': False})
    # This vendored bundle was patched from ES exports to a browser global. No
    # package manifest establishes its version; record the exact bytes instead
    # of incorrectly borrowing the unrelated Python ovstream package version.
    try:
        digest = hashlib.sha256(_BUNDLE.read_bytes()).hexdigest()
    except OSError:
        digest = None
    libraries.append({'id': 'webrtc_browser', 'name': 'Omniverse WebRTC browser library',
                      'version': None, 'installed': digest is not None,
                      'version_source': 'unknown; no verified bundle version manifest',
                      'sha256': digest, 'optional': False})
    actions = [{'id': identifier, 'label': label, 'libraries': packages, 'apis': apis,
                'source': source, 'condition': condition, 'observed_calls': 0,
                'status': 'conditional' if condition else 'not_observed'}
               for identifier, label, packages, apis, source, condition in _ACTIONS]
    trace = {'schema_version': 1, 'kind': 'library_action_map',
             'generated_at': datetime.now(timezone.utc).isoformat(),
             'physics_enabled': bool(physics_enabled), 'libraries': libraries,
             'actions': actions,
             'note': 'Installed versions and source mappings are not an execution log. '
                     'Observed calls count successful instrumented operations in this session; '
                     'they do not prove browser playback or validate a design.'}
    for action in executed:
        record_execution(trace, action)
    return trace


def record_execution(trace, action_id):
    """Count a completed instrumented action; do not record payloads or paths."""
    action = next(action for action in trace['actions'] if action['id'] == action_id)
    action['observed_calls'] += 1
    action['status'] = 'executed'
