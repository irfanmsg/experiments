"""Stream an OpenUSD scene from this GPU to a browser over WebRTC.

Based on the ovstage + ovrtx rendering example and the ovstream
``ovrtx_stream`` CUDA handoff. Run with the project's ``.venv/bin/python``.
"""

from __future__ import annotations

import argparse
import functools
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from camera import CameraController

try:
    import warp as wp
except ImportError:
    wp = None


HERE = Path(__file__).resolve().parent
CLIENT_DIR = HERE / "client"


if wp is not None:
    @wp.kernel
    def _rgba_to_bgra(buffer: wp.array3d(dtype=wp.uint8)):
        x, y = wp.tid()
        red = buffer[y, x, 0]
        blue = buffer[y, x, 2]
        buffer[y, x, 0] = blue
        buffer[y, x, 2] = red


def _status(state: str, **fields: object) -> None:
    print(json.dumps({"status": state, **fields}, separators=(",", ":")), flush=True)


class _ClientHandler(SimpleHTTPRequestHandler):
    def _json(self, body, status=200):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if urlparse(self.path).path == '/api/scene':
            prepared = self.server.prepared
            self._json({key: prepared.get(key) for key in
                        ('name', 'rooms', 'footprint', 'walls', 'width', 'height',
                         'geometry_note', 'asset_count', 'calibration', 'up_axis',
                         'reconstruction_decisions', 'scale_audit', 'openings', 'assets',
                         'presentation_decisions', 'reference_manifest')} |
                       {'camera': self.server.controller.state(),
                        'has_source': bool(prepared.get('source_image'))})
            return
        if urlparse(self.path).path == '/api/source-plan':
            source = self.server.prepared.get('source_image')
            if not source:
                self._json({'error':'No source image'}, 404)
                return
            data = Path(source).read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'image/png' if source.endswith('.png') else 'image/jpeg')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        super().do_GET()

    def do_POST(self):
        if self.path != '/api/camera':
            self._json({'error': 'Not found'}, 404)
            return
        origin = self.headers.get('Origin')
        if origin and urlparse(origin).netloc != self.headers.get('Host'):
            self._json({'error': 'Use the viewer on this host'}, 403)
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 1024 or self.headers.get_content_type() != 'application/json':
                raise ValueError('Expected a camera command')
            command = json.loads(self.rfile.read(length))
            controller = self.server.controller
            if 'zoom' in command:
                value = float(command['zoom'])
                if not math.isfinite(value) or abs(value) > 10:
                    raise ValueError('Invalid zoom')
                controller.zoom(value)
            else:
                controller.set_view(command.get('view'), command.get('room'))
            self._json(controller.state())
        except (ValueError, TypeError, AttributeError):
            self._json({'error': 'Invalid camera command or room'}, 400)

    def log_message(self, fmt: str, *args: object) -> None:
        print("HTTP " + fmt % args, file=sys.stderr)


def _http_server(host: str, port: int, controller, prepared) -> ThreadingHTTPServer:
    if not (CLIENT_DIR / "index.html").exists():
        raise RuntimeError("The bundled WebRTC browser client is missing")
    handler = functools.partial(_ClientHandler, directory=str(CLIENT_DIR))
    server = ThreadingHTTPServer((host, port), handler)
    server.controller = controller
    server.prepared = prepared
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _lan_address() -> str:
    # A UDP connect selects the outbound interface without sending a packet.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 80))
            return probe.getsockname()[0]
    except OSError:
        return socket.gethostname()


def _ice_servers(ovstream) -> list:
    # Matches NVIDIA's ovstream example. Values, including TURN credentials,
    # are neither printed nor written to disk.
    raw = os.environ.get("OVSTREAM_ICE_SERVERS", "")
    servers = []
    for entry in filter(None, raw.split("|")):
        fields = entry.split(",", 2)
        servers.append(ovstream.WebRTCIceServer(
            urls=fields[0],
            username=fields[1] if len(fields) > 1 else "",
            credential=fields[2] if len(fields) > 2 else "",
        ))
    return servers


def _save_rendered_preview(prepared: dict, frame) -> None:
    if not prepared.get('preview_path') or not prepared.get('plan_fingerprint'):
        return
    from PIL import Image
    destination = Path(prepared['preview_path'])
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix('.tmp')
    Image.fromarray(frame).convert('RGB').save(temporary, format='PNG')
    temporary.replace(destination)
    metadata = destination.parent / 'manifest.json'
    try:
        saved = json.loads(metadata.read_text())
    except (OSError, json.JSONDecodeError):
        saved = {}
    styles = saved.get('styles', []) if saved.get('plan_sha256') == prepared['plan_fingerprint'] else []
    saved = {'plan_sha256': prepared['plan_fingerprint'], 'styles': sorted(set(styles + [destination.stem]))}
    temporary = metadata.with_suffix('.tmp')
    temporary.write_text(json.dumps(saved))
    temporary.replace(metadata)


def _set_ceiling_visibility(stage, ceiling_paths: list[str], visible: bool, ordinal: int) -> None:
    if not ceiling_paths:
        return
    import numpy as np
    import ovstage
    # RTX consumes the populated world visibility column; authored USD
    # visibility writes do not recompute it in this native runtime.
    with ovstage.PathDictionary(stage) as paths:
        with paths.create_path_list_from_strings(ceiling_paths) as prims:
            with stage.query_from_path_list(prims) as query:
                stage.write_attribute(query, '_worldVisibility', ordinal=ordinal,
                                      tensors=np.full(len(ceiling_paths), visible, dtype=np.bool_),
                                      is_array=False).wait()


def _render(prepared: dict, args: argparse.Namespace) -> None:
    if wp is None:
        raise RuntimeError("warp-lang is missing; run ./omni_setup/setup.sh runtime")
    try:
        import ovrtx
        import ovstage
        import ovstream
    except ImportError as exc:
        raise RuntimeError("Omniverse runtime is missing; run ./omni_setup/setup.sh runtime") from exc
    if args.physics:
        try:
            import ovphysx
            from ovphysx import PhysX
            from ovphysx.utils import step_and_write_to_ovstage
        except ImportError as exc:
            raise RuntimeError("ovphysx is missing; run ./omni_setup/setup.sh runtime") from exc

    wp.init()
    gpu_name = f"cuda:{args.gpu}"
    wp_device = wp.get_device(gpu_name)
    renderer = None
    stage = None
    physx = None
    server = None
    http = None
    ovstream_started = False
    server_started = False
    renderer_attached = False
    physx_attached = False
    controller = CameraController(prepared["target"], prepared["radius"],
                                  prepared["up_axis"], prepared.get("rooms", []),
                                  prepared.get("plan_radius"))
    connected = threading.Event()
    shutting_down = threading.Event()
    ordinal = 1
    try:
        _status("loading")
        if args.physics:
            # ovstage assembles its USD schema registry on first population.
            ovstage.population.register_usd_schemas(
                [str(ovphysx.codeless_schema_root())])
        renderer = ovrtx.Renderer()
        stage = ovstage.Stage("blueprint-usd-studio.stream")
        renderer.attach_ovstage(stage)
        renderer_attached = True
        ovstage.population.open_usd(
            stage, prepared["scene"], ordinal=ordinal,
            domains=(ovstage.PopulationDomain.ALL if args.physics
                     else ovstage.PopulationDomain.RENDERING))
        stage.advance_write_floor(ordinal, ovstage.Scope.ALL).wait()
        ceiling_paths = prepared.get('ceiling_paths', [])
        ceilings_visible = False
        ordinal += 1
        _set_ceiling_visibility(stage, ceiling_paths, ceilings_visible, ordinal)
        stage.advance_write_floor(ordinal, ovstage.Scope.ALL).wait()
        if args.physics:
            physx = PhysX()
            physx.attach_ovstage(stage, read_ordinal=ordinal)
            physx_attached = True
        _status("rendering_first_frame")

        product_path = prepared["render_product"]
        variable_path = prepared["render_var"]
        # The first render compiles/cache shaders and reveals the actual output
        # dimensions. It can take several minutes on first run.
        first = renderer.step(
            render_products={product_path}, delta_time=1.0 / args.fps,
            ordinal=ordinal)
        first_frame = first[product_path].frames[0]
        with first_frame.render_vars[variable_path].map(
                device=ovrtx.Device.CUDA) as mapping:
            pixels = wp.from_dlpack(mapping)
            if pixels.ndim != 3 or pixels.shape[2] != 4 or pixels.dtype != wp.uint8:
                raise RuntimeError("ovrtx LdrColor must be H×W×4 RGBA8")
            height, width = int(pixels.shape[0]), int(pixels.shape[1])
            try:
                if prepared.get('preview_path'):
                    _save_rendered_preview(prepared, pixels.numpy())
            except (OSError, ValueError) as exc:
                _status('preview_unavailable', error=type(exc).__name__)
            del pixels
        if (width, height) != (args.width, args.height):
            raise RuntimeError("ovrtx output resolution does not match render product")
        del mapping, first_frame, first

        stream_buffer = wp.zeros((height, width, 4), dtype=wp.uint8,
                                 device=gpu_name)
        draw_stream = wp.get_stream(gpu_name)
        draw_event = wp.Event(device=gpu_name)
        ovstream.initialize(log_fn=lambda level, channel, message, ts:
                            print(f"[{level.name}][{channel}] {message}",
                                  file=sys.stderr),
                            log_min_severity=ovstream.LogLevel.INFO)
        ovstream_started = True
        server = ovstream.Server(ovstream.ServerType.WEBRTC)

        def on_connection(is_connected: bool) -> None:
            if shutting_down.is_set():
                return
            (connected.set if is_connected else connected.clear)()
            _status("client_connected" if is_connected else "client_disconnected")

        server.on_connection = on_connection
        server.on_input = lambda event: controller.on_input(event, ovstream)
        ice = _ice_servers(ovstream)
        if ice:
            server.set_webrtc_ice_servers(ice)
        config = ovstream.ServerConfig(
            width=width, height=height,
            cuda_device=args.gpu,
            cuda_context=int(wp_device.context),
        )
        config.webrtc_signal_port = args.signal_port
        config.stream_port = args.media_port
        server.start(config)
        server_started = True
        http = _http_server(args.http_host, args.http_port, controller, prepared)
        _status("ready", local_url=(
            f"http://127.0.0.1:{args.http_port}/?signal_port={args.signal_port}"),
            lan_url=(f"http://{_lan_address()}:{args.http_port}/?signal_port={args.signal_port}"),
            signal_port=args.signal_port, media_port=args.media_port,
            width=width, height=height, physics_enabled=args.physics)

        start = time.monotonic()
        frame_count = 0
        failed_connected_frames = 0
        physics_attributes_written = 0
        with ovstage.PathDictionary(stage) as paths:
            path_list = paths.create_path_list_from_strings([prepared["camera"]])
            try:
                transform = paths.intern_token("omni:xform")
                with stage.query_from_path_list(path_list) as camera_query:
                    while args.max_frames == 0 or frame_count < args.max_frames:
                        frame_start = time.monotonic()
                        ordinal += 1
                        show_ceilings = controller.state()['view'] == 'interior'
                        if show_ceilings != ceilings_visible:
                            _set_ceiling_visibility(stage, ceiling_paths, show_ceilings, ordinal)
                            ceilings_visible = show_ceilings
                        camera_matrix = controller.matrix(frame_start - start)
                        tensor = ovstage.make_dltensor(
                            camera_matrix.ravel(),
                            dtype=ovstage.numpy_to_dldatatype(
                                camera_matrix.dtype, lanes=16),
                            shape=[1], ndim=1)
                        stage.write_attribute(
                            camera_query, transform, ordinal=ordinal,
                            tensors=tensor, is_array=False,
                            semantic=ovstage.AttributeSemantic.MATRIX,
                        ).wait()
                        if args.physics and (not args.physics_pause_without_client
                                             or connected.is_set()):
                            physics_attributes_written += step_and_write_to_ovstage(
                                physx, dt=1.0 / args.fps,
                                output_ordinal=ordinal)
                        else:
                            stage.advance_write_floor(
                                ordinal, ovstage.Scope.ALL).wait()
                        rendered = renderer.step(
                            render_products={product_path},
                            delta_time=1.0 / args.fps,
                            ordinal=ordinal)
                        frame = rendered[product_path].frames[0]
                        with frame.render_vars[variable_path].map(
                                device=ovrtx.Device.CUDA) as mapping:
                            mapping.wait()
                            pixels = wp.from_dlpack(mapping)
                            wp.copy(stream_buffer, pixels, stream=draw_stream)
                            wp.synchronize_stream(draw_stream)
                            del pixels
                        del mapping
                        wp.launch(_rgba_to_bgra, dim=(width, height),
                                  inputs=[stream_buffer], device=gpu_name,
                                  stream=draw_stream)
                        draw_stream.record_event(draw_event)
                        video = ovstream.VideoFrame.from_cuda_array(
                            stream_buffer,
                            sync=ovstream.CudaSync(
                                stream=draw_stream.cuda_stream,
                                wait_event=draw_event.cuda_event),
                        )
                        try:
                            server.stream_video(video)
                            failed_connected_frames = 0
                        except ovstream.OvstreamError as exc:
                            if connected.is_set():
                                failed_connected_frames += 1
                                if failed_connected_frames >= 20:
                                    raise RuntimeError(
                                        "WebRTC connected but video encoding failed"
                                    ) from exc
                        del video, frame, rendered
                        frame_count += 1
                        if frame_count % max(1, args.fps * 10) == 0:
                            progress = {"frames": frame_count,
                                        "client_connected": connected.is_set()}
                            if args.physics:
                                progress["physics_attributes_written"] = (
                                    physics_attributes_written)
                            _status("running", **progress)
                        remaining = 1.0 / args.fps - (time.monotonic() - frame_start)
                        if remaining > 0:
                            time.sleep(remaining)
            finally:
                paths.destroy_path_list(path_list)
        stopped = {"frames": frame_count}
        if args.physics:
            stopped["physics_attributes_written"] = physics_attributes_written
        shutting_down.set()
        _status("stopped", **stopped)
    finally:
        shutting_down.set()
        if http is not None:
            http.shutdown()
            http.server_close()
        if server is not None:
            try:
                if server_started:
                    server.stop()
            finally:
                server.close()
        if ovstream_started:
            ovstream.shutdown()
        if renderer is not None:
            if renderer_attached:
                renderer.detach_ovstage()
            renderer.destroy()
        if physx is not None:
            if physx_attached:
                physx.detach_ovstage()
            physx.destroy()
        if stage is not None:
            stage.destroy()


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usd", required=True, type=Path,
                        help="Generated OpenUSD scene to stream")
    parser.add_argument("--signal-port", type=int, default=49100)
    parser.add_argument("--media-port", type=int, default=47998)
    parser.add_argument("--http-port", type=int, default=8088)
    parser.add_argument("--http-host", default="0.0.0.0")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--gpu", type=int, default=0)
    parser.add_argument("--max-frames", type=int, default=0,
                        help="Stop after N rendered frames (smoke test)")
    parser.add_argument("--physics", action="store_true",
                        help="Step ovphysx and publish simulated transforms into the rendered stage")
    parser.add_argument("--physics-pause-without-client", action="store_true",
                        help="Pause optional physics steps until a WebRTC client connects")
    parser.add_argument("--prepare-only", action="store_true",
                        help="Validate and frame the USD without loading RTX")
    args = parser.parse_args()
    for name in ("signal_port", "media_port", "http_port"):
        if not 0 < getattr(args, name) < 65536:
            parser.error(f"{name} must be in 1..65535")
    for name in ("width", "height", "fps"):
        if getattr(args, name) <= 0:
            parser.error(f"{name} must be positive")
    if args.gpu < 0 or args.max_frames < 0:
        parser.error("gpu and max_frames must be nonnegative")
    if args.physics_pause_without_client and not args.physics:
        parser.error("--physics-pause-without-client requires --physics")
    return args


def main() -> int:
    args = _arguments()
    try:
        restricted = Path("/home/ovqa/Repos/Credentials")
        source_path = args.usd.expanduser().resolve(strict=False)
        if source_path == restricted or restricted in source_path.parents:
            raise ValueError("This source location is unavailable to the application")
        with tempfile.TemporaryDirectory(prefix="blueprint-usd-stream-") as temp:
            destination = Path(temp) / "stream_ready.usda"
            command = [
                sys.executable, str(HERE / "prepare_scene.py"),
                "--usd", str(args.usd), "--output", str(destination),
                "--width", str(args.width), "--height", str(args.height),
            ]
            prepared = json.loads(subprocess.check_output(command, text=True))
            if args.prepare_only:
                _status("prepared", bounds_min=prepared["bounds_min"],
                        bounds_max=prepared["bounds_max"],
                        up_axis=prepared["up_axis"],
                        meters_per_unit=prepared["meters_per_unit"])
                return 0
            _render(prepared, args)
    except KeyboardInterrupt:
        _status("stopped")
    except Exception as exc:
        _status("error", message=str(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
