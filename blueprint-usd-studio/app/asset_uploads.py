"""Import self-contained OpenUSD files without resolving external dependencies."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import uuid
import zipfile

from .asset_library import DEFAULT_ASSET_ROOT


MAX_ASSET_BYTES = 200 * 1024 * 1024
_USD_SUFFIXES = {'.usd', '.usda', '.usdc'}


def _unpack(source: Path, destination: Path) -> Path:
    """Check all ZIP paths and limits before extracting a USDZ package."""
    with zipfile.ZipFile(source) as archive:
        entries = archive.infolist()
        if not entries or len(entries) > 10000 or sum(item.file_size for item in entries) > MAX_ASSET_BYTES:
            raise ValueError('USDZ package is empty or exceeds the 200 MB unpacked limit.')
        names = set()
        files = []
        for item in entries:
            path = PurePosixPath(item.filename)
            mode = stat.S_IFMT(item.external_attr >> 16)
            if (not path.parts or path.is_absolute() or '..' in path.parts
                    or any(char in item.filename for char in '\\:\x00')
                    or str(path) in names or mode not in (0, stat.S_IFREG, stat.S_IFDIR)
                    or item.flag_bits & 1):
                raise ValueError('Unsafe path, link, duplicate, or encrypted entry in USDZ package.')
            names.add(str(path))
            if not item.is_dir():
                files.append(item)
        if not files or Path(files[0].filename).suffix.lower() not in _USD_SUFFIXES:
            raise ValueError('The first file in a USDZ package must be its root USD layer.')
        for item in files:
            target = destination / item.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item) as reader, target.open('xb') as writer:
                shutil.copyfileobj(reader, writer)
        return destination / files[0].filename


def _inspect_dependencies(layer_path: Path, root: Path) -> None:
    """Inspect authored Sdf data, including variants and clips, before composition."""
    from pxr import Sdf

    with layer_path.open('rb') as stream:
        magic = stream.read(8)
    if not (magic.startswith(b'#usda') or magic == b'PXR-USDC'):
        raise ValueError('Expected a standard USDA or USDC layer; custom file formats are unsupported.')
    layer = Sdf.Layer.FindOrOpen(str(layer_path))
    if not layer:
        raise ValueError('The uploaded USD layer could not be read.')

    def validate(value: str, composition=False):
        if not value:
            return
        if Path(value).is_absolute() or any(char in value for char in ':\\[]`$<>\x00'):
            raise ValueError('Asset has an external or unsupported dependency. Upload a self-contained USDZ package with relative paths.')
        target = (layer_path.parent / value).resolve()
        if not target.is_relative_to(root):
            raise ValueError('Asset dependency points outside the imported package.')
        if not target.is_file():
            raise ValueError('Asset is not self-contained: a dependency is missing. Bundle all layers and textures in a USDZ package.')
        if composition and target.suffix.lower() not in _USD_SUFFIXES:
            raise ValueError('USD composition dependencies must be standard USD layers; flatten nested packages or custom formats first.')

    for dependency in layer.GetExternalReferences():
        validate(dependency, composition=True)

    def inspect(value):
        if isinstance(value, Sdf.AssetPath):
            validate(value.path)
        elif isinstance(value, dict):
            for child in value.values():
                inspect(child)
        elif isinstance(value, (list, tuple, Sdf.AssetPathArray)):
            for child in value:
                inspect(child)

    def visit(path):
        spec = layer.GetObjectAtPath(path)
        for key in spec.ListInfoKeys():
            # Composition arcs were checked above. Layer offsets have no Python
            # converter in some OpenUSD builds and cannot contain asset paths.
            if key not in {'subLayerOffsets', 'references', 'payload', 'subLayers'}:
                inspect(spec.GetInfo(key))
    layer.Traverse('/', visit)


def import_asset(path: str | Path, filename: str) -> dict:
    """Copy one staged upload into the persistent library and return its entry.

    Raw USD must be self-contained; USDZ can include standard USD layers and
    textures. No source dependency is composed before containment checks pass.
    """
    from pxr import Usd, UsdGeom

    source = Path(path)
    name = Path(filename.replace('\\', '/')).name
    suffix = Path(name).suffix.lower()
    if suffix not in _USD_SUFFIXES | {'.usdz'}:
        raise ValueError('Upload a .usd, .usda, .usdc, or self-contained .usdz asset.')
    if source.is_symlink() or not source.is_file() or not 0 < source.stat().st_size <= MAX_ASSET_BYTES:
        raise ValueError('Asset upload must be a regular file between 1 byte and 200 MB.')
    root = Path(os.environ.get('BLUEPRINT_STUDIO_ASSET_ROOT', DEFAULT_ASSET_ROOT)).expanduser().resolve()
    imports = root / 'UserImports'
    if imports.is_symlink():
        raise ValueError('The asset import directory must not be a symbolic link.')
    identifier = uuid.uuid4().hex
    destination = imports / identifier
    destination.mkdir(parents=True)
    safe_stem = re.sub(r'[^a-zA-Z0-9_-]+', '_', Path(name).stem).strip('_')[:80] or 'asset'
    uploaded = destination / (safe_stem + suffix)
    try:
        shutil.copyfile(source, uploaded)
        dependency_root = destination / 'package' if suffix == '.usdz' else destination
        entry = _unpack(uploaded, dependency_root) if suffix == '.usdz' else uploaded
        # Inspect every USD layer, even unselected variants and unreferenced
        # files, so future variant selection cannot introduce an external arc.
        for layer in dependency_root.rglob('*'):
            if layer.is_file() and layer.suffix.lower() in _USD_SUFFIXES:
                _inspect_dependencies(layer, dependency_root)
        stage = Usd.Stage.Open(str(entry))
        if not stage or not stage.GetDefaultPrim():
            raise ValueError('Asset must define a default prim containing its model.')
        if stage.GetCompositionErrors():
            raise ValueError('Asset has USD composition errors. Repair references, payloads, or variants before importing.')
        units = UsdGeom.GetStageMetersPerUnit(stage)
        if not stage.HasAuthoredMetadata('metersPerUnit') or not math.isfinite(units) or units <= 0:
            raise ValueError('Asset must author a positive finite metersPerUnit value before import.')
        axis = str(UsdGeom.GetStageUpAxis(stage))
        if not stage.HasAuthoredMetadata('upAxis') or axis not in {'Y', 'Z'}:
            raise ValueError('Asset must author upAxis as Y or Z before import.')
        bounds = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render', 'proxy']).ComputeWorldBound(stage.GetDefaultPrim()).ComputeAlignedBox()
        size = [float(value) * units for value in bounds.GetSize()]
        if bounds.IsEmpty() or not all(math.isfinite(value) and value >= 0 for value in size) or max(size) <= 0:
            raise ValueError('Asset default prim must contain finite bounded geometry.')
        if axis == 'Y':
            size[1], size[2] = size[2], size[1]
        asset = {'id': identifier, 'name': Path(name).stem[:120] or 'Imported asset',
                 'category': 'Imported', 'usd_path': str(entry),
                 'asset_kind': 'Imported USD (SimReady not verified)',
                 'structure_types': ['home', 'office', 'factory', 'showroom', 'other'],
                 'size_xyz_m': size, 'source_units_m': units, 'source_up_axis': axis}
        # The final manifest is the publication marker; failed imports never
        # appear in catalog(). Store a relative path to keep the library movable.
        manifest = {**asset, 'usd_path': str(entry.relative_to(destination))}
        (destination / 'asset.json').write_text(json.dumps(manifest, indent=2))
        return asset
    except Exception as exc:
        shutil.rmtree(destination)
        if isinstance(exc, ValueError):
            raise
        raise ValueError('Asset could not be imported. Check that the USD or USDZ is valid and self-contained.') from exc
