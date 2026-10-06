"""Wrap a dimensioned USD scene with a camera and render product for ovrtx.

This runs in a separate process so the classic ``pxr`` authoring runtime is
never loaded into the ovstage/ovrtx rendering process.
"""

from __future__ import annotations

import argparse
import json
import math
import itertools
from pathlib import Path

from pxr import Gf, Usd, UsdGeom, UsdLux, UsdRender


CAMERA_PATH = "/World/StreamCamera"
PRODUCT_PATH = "/Render/Camera"
RENDER_VAR_PATH = "/Render/Camera/LdrColor"


def _vec3(value: Gf.Vec3d) -> list[float]:
    return [float(value[0]), float(value[1]), float(value[2])]


def prepare_scene(source: Path, destination: Path, width: int, height: int) -> dict:
    source = source.expanduser().resolve(strict=True)
    restricted = Path("/home/ovqa/Repos/Credentials")
    if source == restricted or restricted in source.parents:
        raise ValueError("This source location is unavailable to the application")
    if source.suffix.lower() not in {".usd", ".usda", ".usdc"}:
        raise ValueError("Expected a .usd, .usda, or .usdc scene")

    original = Usd.Stage.Open(str(source))
    if not original:
        raise ValueError("USD stage could not be opened")
    root = original.GetDefaultPrim()
    if not root:
        roots = [p for p in original.GetPseudoRoot().GetChildren() if p.IsActive()]
        if len(roots) != 1:
            raise ValueError("USD stage needs a default prim or exactly one root prim")
        root = roots[0]

    purposes = [UsdGeom.Tokens.default_, UsdGeom.Tokens.render, UsdGeom.Tokens.proxy]
    bbox_cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), purposes)
    bbox = bbox_cache.ComputeWorldBound(root).ComputeAlignedBox()
    if bbox.IsEmpty():
        raise ValueError("USD stage has no bounded geometry to frame")

    bounds_min = _vec3(bbox.GetMin())
    bounds_max = _vec3(bbox.GetMax())
    if not all(math.isfinite(v) for v in bounds_min + bounds_max):
        raise ValueError("USD stage bounds contain a non-finite coordinate")
    center = [(low + high) / 2 for low, high in zip(bounds_min, bounds_max)]
    spans = [high - low for low, high in zip(bounds_min, bounds_max)]
    axis = UsdGeom.GetStageUpAxis(original)
    if axis not in (UsdGeom.Tokens.z, UsdGeom.Tokens.y):
        raise ValueError("Only Y-up and Z-up USD stages are supported")
    up_index = 2 if axis == UsdGeom.Tokens.z else 1
    horizontal = [i for i in range(3) if i != up_index]
    center[up_index] = bounds_min[up_index] + 0.45 * spans[up_index]
    # Frame the actual bounds using both camera apertures. A fixed diagonal
    # multiplier left too much empty space and ignored portrait buildings.
    def frame_radius(pitch):
        direction = Gf.Vec3d(0, -math.cos(pitch), math.sin(pitch)) if up_index == 2 else Gf.Vec3d(0, math.sin(pitch), -math.cos(pitch))
        up = Gf.Vec3d(0, 0, 1) if up_index == 2 else Gf.Vec3d(0, 1, 0)
        right = Gf.Cross(-direction, up).GetNormalized()
        camera_up = Gf.Cross(right, -direction)
        tan_h = 36 / (2 * 28)
        tan_v = tan_h * height / width
        distances = []
        for corner in itertools.product(*zip(bounds_min, bounds_max)):
            offset = Gf.Vec3d(*corner) - Gf.Vec3d(*center)
            distances.append(max(abs(Gf.Dot(offset, right)) / tan_h,
                                 abs(Gf.Dot(offset, camera_up)) / tan_v) + Gf.Dot(offset, direction))
        return max(2.0, max(distances) * 1.10)
    radius = frame_radius(math.radians(62))
    plan_radius = frame_radius(math.pi / 2 - 0.0001)
    units = UsdGeom.GetStageMetersPerUnit(original)
    if not math.isfinite(units) or units <= 0:
        raise ValueError("Invalid USD metersPerUnit metadata")

    destination.parent.mkdir(parents=True, exist_ok=True)
    wrapper = Usd.Stage.CreateNew(str(destination))
    UsdGeom.SetStageUpAxis(wrapper, axis)
    UsdGeom.SetStageMetersPerUnit(wrapper, units)
    world = UsdGeom.Xform.Define(wrapper, "/World")
    wrapper.SetDefaultPrim(world.GetPrim())
    model = UsdGeom.Xform.Define(wrapper, "/World/Model")
    model.GetPrim().GetReferences().AddReference(str(source), root.GetPath())
    # ALL population renders physics prototypes as duplicates at the origin.
    # Expand this temporary composition; exported source instances stay intact.
    for prim in Usd.PrimRange(model.GetPrim()):
        if prim.IsInstance():
            prim.SetInstanceable(False)

    camera = UsdGeom.Camera.Define(wrapper, CAMERA_PATH)
    camera.CreateFocalLengthAttr(28.0)
    camera.CreateHorizontalApertureAttr(36.0)
    camera.CreateVerticalApertureAttr(36.0 * height / width)
    camera.CreateClippingRangeAttr(Gf.Vec2f(0.01, max(1000.0, radius * 100)))
    eye = list(center)
    eye[horizontal[0]] += radius * 0.62
    eye[horizontal[1]] -= radius * 0.62
    eye[up_index] += radius * 0.48
    world_up = [0.0, 0.0, 0.0]
    world_up[up_index] = 1.0
    view = Gf.Matrix4d().SetLookAt(
        Gf.Vec3d(*eye), Gf.Vec3d(*center), Gf.Vec3d(*world_up)
    )
    camera.AddTransformOp().Set(view.GetInverse())

    if not any(prim.HasAPI(UsdLux.LightAPI) for prim in original.Traverse()):
        dome = UsdLux.DomeLight.Define(wrapper, "/World/Environment")
        dome.CreateIntensityAttr(300.0)

    rooms = []
    for prim in original.Traverse():
        polygon = prim.GetCustomDataByKey('polygonM')
        if not polygon:
            continue
        polygon = json.loads(polygon)
        floor_prim = prim.GetChild('Floor')
        modeled = None
        if floor_prim and floor_prim.IsA(UsdGeom.Mesh):
            points = UsdGeom.Mesh(floor_prim).GetPointsAttr().Get()
            polygon = [[float(p[0]), float(p[1])] for p in points[:len(points)//2]]
            spans = [max(p[i] for p in polygon)-min(p[i] for p in polygon) for i in range(2)]
            modeled = spans.copy()
            if prim.GetCustomDataByKey('dimensionMode') == 'average_depth':
                area = abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(polygon,polygon[1:]+polygon[:1])))/2
                span_axis = int(prim.GetCustomDataByKey('spanAxis'))
                modeled[1-span_axis] = area/spans[span_axis]
        low = [min(p[i] for p in polygon) for i in range(2)]
        high = [max(p[i] for p in polygon) for i in range(2)]
        # Plan coordinates are metre-based XY (the authoring pipeline is Z-up).
        eye = [low[0] + (high[0] - low[0]) * .18,
               low[1] + (high[1] - low[1]) * .28, 1.6]
        look = [low[0] + (high[0] - low[0]) * .85,
                low[1] + (high[1] - low[1]) * .65, 1.35]
        rooms.append({'id': prim.GetName(), 'name': prim.GetCustomDataByKey('label'),
                      'polygon': polygon, 'min': low + [0], 'max': high + [0],
                      'eye': eye, 'look_at': look,
                      'dimensions': json.loads(prim.GetCustomDataByKey('printedDimensionsM') or '[]'),
                      'dimension_mode': prim.GetCustomDataByKey('dimensionMode') or 'raster',
                      'modeled_dimensions': modeled})
    floor = original.GetPrimAtPath(str(root.GetPath()) + '/Building/FloorSlab')
    footprint = []
    if floor:
        points = UsdGeom.Mesh(floor).GetPointsAttr().Get()
        footprint = [[float(p[0]), float(p[1])] for p in points[:len(points)//2]]

    product = UsdRender.Product.Define(wrapper, PRODUCT_PATH)
    product.CreateCameraRel().SetTargets([camera.GetPath()])
    product.CreateResolutionAttr(Gf.Vec2i(width, height))
    render_var = UsdRender.Var.Define(wrapper, RENDER_VAR_PATH)
    render_var.CreateSourceNameAttr("LdrColor")
    product.CreateOrderedVarsRel().SetTargets([render_var.GetPath()])

    wrapper.GetRootLayer().Save()
    repository = Path(__file__).resolve().parents[1]
    style = root.GetCustomDataByKey('style')
    preview_path = None
    if (source.parent.parent == repository / 'output' and root.GetCustomDataByKey('isDesignScheme')
            and style == source.stem and all(char in 'abcdefghijklmnopqrstuvwxyz0123456789_-' for char in style)):
        preview_path = str(source.parent / 'previews' / f'{style}.png')
    source_image = None
    if source.parent.parent == repository / 'output':
        for filename in ('plan.jpg', 'plan.png'):
            candidate = repository / 'uploads' / source.parent.name / filename
            if candidate.is_file():
                source_image = str(candidate)
                break
    if source_image is None and root.GetCustomDataByKey('planName') == 'PWC Miami B1-1502':
        source_data = json.loads(root.GetCustomDataByKey('source') or '{}')
        primary_crop = source_data.get('primary_crop', 'approved_crop.jpg')
        candidate = repository / 'data/b1_1502' / primary_crop if primary_crop in {'approved_crop.jpg', 'agreement_unit_crop.jpg'} else None
        if candidate and candidate.is_file():
            source_image = str(candidate)
    reopened = Usd.Stage.Open(str(destination))
    if not reopened or not reopened.GetPrimAtPath("/World/Model").IsValid():
        raise RuntimeError("Prepared USD scene did not reopen correctly")
    return {
        "scene": str(destination),
        "bounds_min": bounds_min,
        "bounds_max": bounds_max,
        "target": center,
        "radius": radius,
        "plan_radius": plan_radius,
        "rooms": rooms,
        "ceiling_paths": [str(prim.GetPath()) for prim in Usd.PrimRange(model.GetPrim())
                          if prim.IsA(UsdGeom.Mesh) and prim.GetParent().GetName() == 'Ceilings'],
        "footprint": footprint,
        "walls": json.loads(root.GetCustomDataByKey('wallTrace') or '[]'),
        "calibration": json.loads(root.GetCustomDataByKey('traceCalibration') or '{}'),
        "source_image": source_image,
        "name": root.GetCustomDataByKey('planName') or source.stem,
        "asset_count": len(original.GetPrimAtPath(str(root.GetPath()) + '/Assets').GetChildren()) if original.GetPrimAtPath(str(root.GetPath()) + '/Assets') else 0,
        "geometry_note": root.GetCustomDataByKey('dimensionNote') or 'Traced from the drawing. Wall positions are approximate; height and thickness are assumed.',
        "reconstruction_decisions": json.loads(root.GetCustomDataByKey('reconstructionDecisions') or '[]'),
        "scale_audit": json.loads(root.GetCustomDataByKey('scaleAudit') or '{}'),
        "openings": json.loads(root.GetCustomDataByKey('openingTrace') or '[]'),
        "assets": json.loads(root.GetCustomDataByKey('assetImports') or '[]'),
        "presentation_decisions": json.loads(root.GetCustomDataByKey('presentationDecisions') or '[]'),
        "reference_manifest": json.loads(root.GetCustomDataByKey('referenceManifest') or '{}'),
        "style": style,
        "preview_path": preview_path,
        "plan_fingerprint": root.GetCustomDataByKey('planFingerprint'),
        "up_axis": str(axis),
        "meters_per_unit": units,
        "camera": CAMERA_PATH,
        "render_product": PRODUCT_PATH,
        "render_var": RENDER_VAR_PATH,
        "width": width,
        "height": height,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usd", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    args = parser.parse_args()
    if min(args.width, args.height) <= 0:
        parser.error("resolution must be positive")
    print(json.dumps(prepare_scene(args.usd, args.output, args.width, args.height)))


if __name__ == "__main__":
    main()
