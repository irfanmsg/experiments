"""Guided blueprint upload, review, USD generation, and stream control."""

from __future__ import annotations

import json
import hashlib
import socket
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pymupdf as fitz
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

from .asset_library import b1_starter_furniture, catalog
from .geometry import measured_scale_audit, validate_plan
from .usd_builder import PALETTES, build_style_variants, build_usd
from .vision import suggest_rooms


ROOT = Path(__file__).resolve().parents[1]
UPLOADS = ROOT / "uploads"
OUTPUT = ROOT / "output"
EXAMPLE = ROOT / "data" / "b1_1502"
STREAM_RESOLUTIONS = {
    "standard": (640, 360),
    "hd": (1280, 720),
    "full_hd": (1920, 1080),
    "qhd": (2560, 1440),
    "uhd": (3840, 2160),
}
for directory in (UPLOADS, OUTPUT):
    directory.mkdir(exist_ok=True)

app = FastAPI(title="Blueprint to USD Studio", version="0.1.0")
app.mount("/static", StaticFiles(directory=ROOT / "app" / "static"), name="static")
_stream_process: subprocess.Popen | None = None
_stream_project: str | None = None
_stream_style: str | None = None
_stream_quality: str | None = None
_stream_physics = False


def _lan_address() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def _project_dir(project_id: str) -> Path:
    if not project_id or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for char in project_id):
        raise HTTPException(400, "Invalid project ID")
    path = UPLOADS / project_id
    if not path.is_dir():
        raise HTTPException(404, "Project not found")
    return path


def _read_plan(project_id: str) -> dict:
    path = _project_dir(project_id) / "plan.json"
    if not path.exists():
        raise HTTPException(404, "Plan not found")
    plan = json.loads(path.read_text())
    if plan.get('example') == 'B1-1502' and plan.get('dimension_model') == 'b1-clear-dimensions-v1':
        # Match the original v1 geometry, allowing JSON's int/float round trip.
        # Edited geometry is preserved rather than replaced by a new template.
        def normalized(value):
            if isinstance(value, dict):
                return {key: normalized(item) for key, item in value.items()}
            if isinstance(value, list):
                return [normalized(item) for item in value]
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return round(float(value), 8) or 0.0
            return value
        geometry_keys = ('rooms', 'wall_segments', 'openings', 'footprint')
        geometry = normalized({key: plan.get(key) for key in geometry_keys})
        fingerprint = hashlib.sha256(json.dumps(geometry, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        if fingerprint != '4543b206e0cf26682afae1da1a3672012e79a5ed760026f08dfa2182041078c7':
            raise HTTPException(409, 'This older B1 reconstruction has geometry edits. Your project is preserved; open the updated B1 example to use the corrected reconstruction.')
        updated = json.loads((EXAMPLE / 'plan.json').read_text())
        if plan.get('asset_placements'):
            from .dimensioned_b1 import relocate_assets
            original_rooms = {room['id']: room for room in plan['rooms']}
            relocation_rooms = [dict(room, source_polygon=original_rooms[room['id']]['polygon'])
                                for room in updated['rooms'] if room['id'] in original_rooms]
            plan['asset_placements'] = relocate_assets(plan['asset_placements'], relocation_rooms)
        for key in (*geometry_keys, 'dimension_model', 'dimension_note', 'reconstruction_decisions', 'scale_audit', 'source', 'calibration', 'image_size', 'reference_manifest', 'coordinate_system', 'source_footprint', 'source_wall_segments'):
            plan[key] = updated[key]
        if plan.get('asset_placements'):
            plan['reconstruction_decisions'].append({'id': 'legacy_furniture_relocation', 'kind': 'assumption',
                'summary': 'Earlier furniture positions moved with their nearest room; physical size, rotation and placement height retained.',
                'basis': 'The agreement reconstruction changes room registration. Relative offsets are preserved; fitted placement and door clearance need review.',
                'status': 'needs-review'})
        _save_plan(project_id, plan)
        shutil.copy2(EXAMPLE / updated['source'].get('primary_crop', 'approved_crop.jpg'), _project_dir(project_id) / 'plan.jpg')
    if plan.get('example') == 'B1-1502' and not plan.get('dimension_model'):
        raw = json.loads((EXAMPLE / 'raster_trace.json').read_text())
        keys = ('rooms', 'wall_segments', 'openings', 'footprint')
        if all(plan.get(key) == raw.get(key) for key in keys):
            from .dimensioned_b1 import build_dimensioned_plan
            plan = build_dimensioned_plan(plan)
            _save_plan(project_id, plan)
            shutil.copy2(EXAMPLE / plan['source'].get('primary_crop', 'approved_crop.jpg'), _project_dir(project_id) / 'plan.jpg')
        else:
            raise HTTPException(409, 'This older B1 project has geometry edits. Open the updated B1 example to use dimensioned rooms; your edited project is preserved.')
    return plan


def _save_plan(project_id: str, plan: dict) -> None:
    if plan.get('scale_audit'):
        plan['scale_audit'] = measured_scale_audit(plan)
    path = _project_dir(project_id) / "plan.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(plan, indent=2, ensure_ascii=False))
    temporary.replace(path)


def _raster_pdf(source: Path, destination: Path, page_number: int = 0) -> tuple[int, int, int]:
    with fitz.open(source) as document:
        if not 0 <= page_number < len(document):
            raise HTTPException(400, f"Page must be between 1 and {len(document)}")
        page = document[page_number]
        zoom = min(4.0, 3200.0 / max(page.rect.width, page.rect.height))
        pixels = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        pixels.save(destination)
        return pixels.width, pixels.height, len(document)


def _normalize_image(source: Path, destination: Path) -> tuple[int, int, int]:
    try:
        with Image.open(source) as image:
            image.verify()
        with Image.open(source) as image:
            if image.width * image.height > 100_000_000:
                raise HTTPException(400, "Image is too large; use a drawing under 100 megapixels")
            image.convert("RGB").save(destination, "PNG", optimize=True)
            return image.width, image.height, 1
    except (OSError, ValueError) as exc:
        raise HTTPException(400, "The uploaded image could not be opened") from exc


def _project_response(project_id: str) -> dict:
    plan = _read_plan(project_id)
    return {
        "id": project_id,
        "plan": plan,
        "image_url": f"/api/projects/{project_id}/image",
        "page_count": int(plan.get("page_count", 1)),
        "styles": [{"id": key, "label": value["label"], "category": value["category"], "description": value["description"], "wall_color": value["wall"][0], "floor_color": value["floor"][0]} for key, value in PALETTES.items()],
    }


@app.get("/")
def home():
    return FileResponse(ROOT / "app" / "static" / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True, "app": "Blueprint to USD Studio", "styles": list(PALETTES)}


@app.post("/api/projects/upload")
async def upload_blueprint(file: UploadFile = File(...), page: int = Form(1)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}:
        raise HTTPException(400, "Upload a PDF, PNG, JPEG, WebP, or TIFF drawing")
    project_id = uuid.uuid4().hex[:12]
    directory = UPLOADS / project_id
    directory.mkdir()
    source = directory / f"source{suffix}"
    total = 0
    with source.open("wb") as output:
        while chunk := await file.read(1024 * 1024):
            total += len(chunk)
            if total > 200 * 1024 * 1024:
                shutil.rmtree(directory)
                raise HTTPException(413, "Use a drawing smaller than 200 MB")
            output.write(chunk)
    if total == 0:
        shutil.rmtree(directory)
        raise HTTPException(400, "The upload is empty")
    preview = directory / "plan.png"
    try:
        if suffix == ".pdf":
            width, height, page_count = _raster_pdf(source, preview, page - 1)
        else:
            width, height, page_count = _normalize_image(source, preview)
    except Exception:
        shutil.rmtree(directory)
        raise
    plan = {
        "id": project_id,
        "name": Path(file.filename or "New project").stem,
        "structure_type": "home",
        "units": "m",
        "page": page,
        "page_count": page_count,
        "image_size": [width, height],
        "room_height_m": 2.9,
        "height_status": "assumed; confirm before construction use",
        "source": {"filename": file.filename, "page": page},
        "calibration": None,
        "footprint": {"polygon": []},
        "rooms": [],
        "balconies": [],
        "wall_segments": [],
        "openings": [],
        "asset_placements": [],
    }
    _save_plan(project_id, plan)
    return _project_response(project_id)


@app.post("/api/examples/b1-1502")
def load_flat_example():
    source_plan = EXAMPLE / "plan.json"
    if not source_plan.exists():
        raise HTTPException(503, "B1-1502 source tracing is still being prepared")
    plan = json.loads(source_plan.read_text())
    primary_crop = plan.get('source', {}).get('primary_crop', 'approved_crop.jpg')
    if primary_crop not in {'approved_crop.jpg', 'agreement_unit_crop.jpg'}:
        raise HTTPException(503, 'Unknown B1 source image')
    source_image = EXAMPLE / primary_crop
    if not source_image.exists():
        raise HTTPException(503, "B1-1502 source image is unavailable")
    project_id = uuid.uuid4().hex[:12]
    directory = UPLOADS / project_id
    directory.mkdir()
    shutil.copy2(source_image, directory / "plan.jpg")
    manifest = EXAMPLE / 'reference_manifest.json'
    if manifest.is_file():
        plan['reference_manifest'] = json.loads(manifest.read_text())
    plan["id"] = project_id
    plan["example"] = "B1-1502"
    plan["structure_type"] = "home"
    plan['asset_placements'] = b1_starter_furniture(plan)
    _save_plan(project_id, plan)
    return _project_response(project_id)


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    return _project_response(project_id)


@app.get("/api/projects/{project_id}/reconstruction-trace")
def project_reconstruction_trace(project_id: str):
    plan = _read_plan(project_id)
    trace = {"project_id": project_id, "source": plan.get("source", {}),
             "dimension_model": plan.get("dimension_model"),
             "decisions": plan.get("reconstruction_decisions", []),
             "scale_audit": measured_scale_audit(plan),
             "openings": plan.get("openings", []),
             "reference_manifest": plan.get('reference_manifest', {}),
             "asset_placements": plan.get("asset_placements", [])}
    export = OUTPUT / project_id / "reconstruction_trace.json"
    if export.is_file():
        trace["last_export"] = json.loads(export.read_text())
    return JSONResponse(trace, headers={
        "Content-Disposition": f'attachment; filename="{project_id}-reconstruction-trace.json"'})


@app.put("/api/projects/{project_id}/plan")
async def update_plan(project_id: str, request: Request):
    plan = await request.json()
    if not isinstance(plan, dict):
        raise HTTPException(400, "Expected a plan object")
    plan["id"] = project_id
    plan["units"] = "m"
    _save_plan(project_id, plan)
    return {"ok": True, "validation_errors": validate_plan(plan)}


@app.get("/api/projects/{project_id}/image")
def project_image(project_id: str):
    directory = _project_dir(project_id)
    for name in ("plan.png", "plan.jpg"):
        path = directory / name
        if path.exists():
            return FileResponse(path)
    raise HTTPException(404, "Plan image unavailable")


@app.post("/api/projects/{project_id}/page")
async def select_page(project_id: str, request: Request):
    directory = _project_dir(project_id)
    source = directory / "source.pdf"
    if not source.exists():
        raise HTTPException(400, "This project is not a PDF")
    body = await request.json()
    page = int(body.get("page", 1))
    width, height, count = _raster_pdf(source, directory / "plan.png", page - 1)
    plan = _read_plan(project_id)
    plan.update({"page": page, "page_count": count, "image_size": [width, height], "calibration": None, "footprint": {"polygon": []}, "rooms": [], "balconies": [], "wall_segments": [], "openings": [], "asset_placements": []})
    plan.setdefault("source", {})["page"] = page
    _save_plan(project_id, plan)
    return _project_response(project_id)


@app.get("/api/projects/{project_id}/suggest")
def suggest(project_id: str):
    directory = _project_dir(project_id)
    path = directory / ("plan.png" if (directory / "plan.png").exists() else "plan.jpg")
    return {"suggestions": suggest_rooms(path)}


@app.post("/api/projects/{project_id}/generate")
async def generate(project_id: str, request: Request):
    body = await request.json()
    style = str(body.get("style", "contemporary"))
    if style != "all" and style not in PALETTES:
        raise HTTPException(400, "Unknown style")
    plan = _read_plan(project_id)
    errors = validate_plan(plan)
    if errors:
        raise HTTPException(400, {"errors": errors})
    if _stream_project == project_id and _stream_process and _stream_process.poll() is None:
        stop_stream()
    destination = OUTPUT / project_id
    try:
        if style == "all":
            result = build_style_variants(plan, destination)
            with ZipFile(destination / "style_pack.zip", "w", compression=ZIP_DEFLATED) as archive:
                archive.write(destination / "all_styles.usda", "all_styles.usda")
                for style_name in result["styles"]:
                    archive.write(destination / f"{style_name}.usda", f"{style_name}.usda")
            result["download_url"] = f"/api/projects/{project_id}/pack"
        else:
            result = build_usd(plan, destination / f"{style}.usda", style)
            result["download_url"] = f"/api/projects/{project_id}/usd/{style}"
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(400, str(exc)) from exc
    trace = {"style": style, "dimension_model": plan.get("dimension_model"),
             "asset_imports": result.get("asset_imports", []),
             "presentation_decisions": result.get('presentation_decisions', []),
             "reference_manifest": plan.get('reference_manifest', {}),
             "styles": result.get("styles", {}) if style == "all" else {}}
    (destination / "reconstruction_trace.json").write_text(json.dumps(trace, indent=2))
    return result


@app.get("/api/projects/{project_id}/usd/{style}")
def get_usd(project_id: str, style: str):
    _project_dir(project_id)
    if style not in PALETTES and style != "all_styles":
        raise HTTPException(400, "Unknown style")
    path = OUTPUT / project_id / f"{style}.usda"
    if not path.exists():
        raise HTTPException(404, "Generate this style first")
    return FileResponse(path, media_type="model/vnd.usda", filename=f"{style}.usda")


@app.get("/api/projects/{project_id}/pack")
def get_style_pack(project_id: str):
    _project_dir(project_id)
    path = OUTPUT / project_id / "style_pack.zip"
    if not path.exists():
        raise HTTPException(404, "Generate the style pack first")
    return FileResponse(path, media_type="application/zip", filename="blueprint_styles.zip")


@app.get("/api/assets")
def assets():
    return catalog()


@app.post("/api/projects/{project_id}/starter-furniture")
def furnish_flat_example(project_id: str):
    plan = _read_plan(project_id)
    if plan.get("example") != "B1-1502":
        raise HTTPException(400, "Starter layout is for the B1-1502 example")
    additions = b1_starter_furniture(plan)
    if not additions:
        raise HTTPException(503, "SimReady furniture pack is not installed")
    existing = {item.get("id") for item in plan.get("asset_placements", [])}
    plan.setdefault("asset_placements", []).extend(item for item in additions if item["id"] not in existing)
    _save_plan(project_id, plan)
    return _project_response(project_id)


@app.get("/api/stream/status")
def stream_status():
    running = _stream_process is not None and _stream_process.poll() is None
    phase = "idle"
    if _stream_project:
        log_path = OUTPUT / _stream_project / "stream.log"
        if log_path.exists():
            with log_path.open("rb") as log:
                log.seek(0, 2)
                size = log.tell()
                log.seek(max(0, size - 131_072))
                for line in log.read().decode("utf-8", errors="replace").splitlines():
                    if not line.startswith("{"):
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if entry.get("status"):
                        phase = entry["status"]
    if _stream_process and not running and phase not in {"stopped", "error"}:
        phase = "error"
    return {"running": running, "phase": phase, "project_id": _stream_project, "style": _stream_style, "quality": _stream_quality, "physics": _stream_physics, "signal_port": 49100, "client_port": 8088}


@app.post("/api/projects/{project_id}/stream")
async def start_stream(project_id: str, request: Request):
    global _stream_process, _stream_project, _stream_style, _stream_quality, _stream_physics
    _project_dir(project_id)
    body = await request.json()
    style = str(body.get("style", "contemporary"))
    quality = str(body.get("quality", "hd"))
    physics = body.get("physics", False)
    if not isinstance(physics, bool):
        raise HTTPException(400, "Physics setting must be true or false")
    if quality not in STREAM_RESOLUTIONS:
        raise HTTPException(400, "Unknown stream quality")
    width, height = STREAM_RESOLUTIONS[quality]
    if style not in PALETTES and style != "all_styles":
        raise HTTPException(400, "Unknown style")
    path = OUTPUT / project_id / f"{style}.usda"
    if not path.exists():
        raise HTTPException(400, "Generate a USD scene before streaming")
    hostname = request.url.hostname or "127.0.0.1"
    if hostname in {"127.0.0.1", "localhost", "::1"}:
        hostname = _lan_address()
    client_url = f"http://{hostname}:8088/?signal_port=49100"
    if _stream_process and _stream_process.poll() is None:
        if (_stream_project, _stream_style, _stream_quality, _stream_physics) == (project_id, style, quality, physics):
            return {"started": False, **stream_status(), "client_url": client_url}
        if _stream_project != project_id:
            raise HTTPException(409, "Another scene is streaming. Stop it first.")
        stop_stream()
    script = ROOT / "streaming" / "run.py"
    if not script.exists():
        raise HTTPException(503, "WebRTC runtime is not installed yet")
    log_path = OUTPUT / project_id / "stream.log"
    command = [sys.executable, str(script), "--usd", str(path), "--signal-port", "49100", "--http-port", "8088", "--width", str(width), "--height", str(height)]
    if physics:
        command.append("--physics")
    with log_path.open("w") as log:
        _stream_process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    _stream_project = project_id
    _stream_style = style
    _stream_quality = quality
    _stream_physics = physics
    return {"started": True, **stream_status(), "client_url": client_url}


@app.post("/api/stream/stop")
def stop_stream():
    global _stream_process, _stream_project, _stream_style, _stream_quality, _stream_physics
    if _stream_process and _stream_process.poll() is None:
        _stream_process.terminate()
        try:
            _stream_process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            _stream_process.kill()
    _stream_process = None
    _stream_project = None
    _stream_style = None
    _stream_quality = None
    _stream_physics = False
    return {"running": False}


@app.on_event("shutdown")
def stop_stream_on_shutdown():
    stop_stream()


@app.exception_handler(Exception)
async def handle_unexpected(_request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    return JSONResponse({"detail": f"Unexpected server error: {type(exc).__name__}"}, status_code=500)
