"""Author metre-accurate, Z-up OpenUSD buildings from reviewed plan geometry.

This module deliberately uses OpenUSD for persistent authoring. ovstage,
ovrtx, and ovstream consume the resulting scene at runtime.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

import usdex.core

from .geometry import bbox, polygon_area, safe_name, segment_length, triangulate, validate_plan


PALETTES = {
    "contemporary": {
        "label": "Contemporary",
        "category": "home",
        "description": "Warm wood and calm neutrals",
        "wall": ((0.85, 0.83, 0.78), 0.78, 0.0),
        "floor": ((0.56, 0.40, 0.27), 0.62, 0.0),
        "balcony": ((0.50, 0.51, 0.49), 0.82, 0.0),
        "door": ((0.36, 0.23, 0.15), 0.55, 0.0),
        "glass": ((0.57, 0.75, 0.82), 0.12, 0.0),
        "metal": ((0.27, 0.29, 0.30), 0.26, 0.85),
    },
    "minimal": {
        "label": "Light minimal",
        "category": "home",
        "description": "Pale oak and clean whites",
        "wall": ((0.91, 0.91, 0.87), 0.73, 0.0),
        "floor": ((0.72, 0.66, 0.55), 0.68, 0.0),
        "balcony": ((0.69, 0.68, 0.64), 0.88, 0.0),
        "door": ((0.65, 0.57, 0.47), 0.64, 0.0),
        "glass": ((0.68, 0.80, 0.83), 0.10, 0.0),
        "metal": ((0.63, 0.65, 0.64), 0.30, 0.78),
    },
    "classic": {
        "label": "Classic",
        "category": "home",
        "description": "Cream walls and dark walnut",
        "wall": ((0.83, 0.76, 0.61), 0.83, 0.0),
        "floor": ((0.28, 0.15, 0.09), 0.48, 0.0),
        "balcony": ((0.68, 0.61, 0.47), 0.84, 0.0),
        "door": ((0.25, 0.13, 0.07), 0.48, 0.0),
        "glass": ((0.58, 0.70, 0.75), 0.13, 0.0),
        "metal": ((0.54, 0.43, 0.22), 0.30, 0.82),
    },
    "industrial": {
        "label": "Industrial loft",
        "category": "home",
        "description": "Concrete and dark steel",
        "wall": ((0.45, 0.46, 0.44), 0.88, 0.0),
        "floor": ((0.33, 0.34, 0.34), 0.72, 0.0),
        "balcony": ((0.43, 0.44, 0.43), 0.90, 0.0),
        "door": ((0.20, 0.20, 0.20), 0.52, 0.15),
        "glass": ((0.53, 0.68, 0.73), 0.12, 0.0),
        "metal": ((0.23, 0.24, 0.25), 0.27, 0.88),
    },
    "home_luxury": {
        "label": "Contemporary luxury",
        "category": "home",
        "description": "Stone, walnut and bronze",
        "wall": ((0.76, 0.72, 0.65), 0.52, 0.0),
        "floor": ((0.35, 0.29, 0.25), 0.39, 0.0),
        "balcony": ((0.65, 0.63, 0.60), 0.64, 0.0),
        "door": ((0.24, 0.16, 0.12), 0.40, 0.0),
        "glass": ((0.61, 0.73, 0.77), 0.08, 0.0),
        "metal": ((0.60, 0.44, 0.25), 0.25, 0.84),
    },
    "factory": {
        "label": "Clean production",
        "category": "factory",
        "description": "Light, washable surfaces",
        "wall": ((0.68, 0.70, 0.69), 0.79, 0.0),
        "floor": ((0.38, 0.43, 0.43), 0.50, 0.0),
        "balcony": ((0.52, 0.54, 0.52), 0.86, 0.0),
        "door": ((0.38, 0.43, 0.45), 0.45, 0.45),
        "glass": ((0.55, 0.70, 0.74), 0.13, 0.0),
        "metal": ((0.42, 0.45, 0.47), 0.24, 0.88),
    },
    "warehouse": {
        "label": "Warehouse",
        "category": "factory",
        "description": "Concrete and galvanized steel",
        "wall": ((0.58, 0.59, 0.57), 0.85, 0.0),
        "floor": ((0.43, 0.43, 0.40), 0.70, 0.0),
        "balcony": ((0.55, 0.56, 0.53), 0.86, 0.0),
        "door": ((0.39, 0.40, 0.37), 0.44, 0.5),
        "glass": ((0.55, 0.68, 0.73), 0.15, 0.0),
        "metal": ((0.44, 0.46, 0.43), 0.36, 0.82),
    },
    "hightech_factory": {
        "label": "High-tech plant",
        "category": "factory",
        "description": "Cool clean-room finishes",
        "wall": ((0.79, 0.83, 0.84), 0.55, 0.0),
        "floor": ((0.35, 0.50, 0.54), 0.42, 0.12),
        "balcony": ((0.60, 0.70, 0.71), 0.52, 0.0),
        "door": ((0.34, 0.45, 0.49), 0.28, 0.7),
        "glass": ((0.56, 0.76, 0.82), 0.08, 0.0),
        "metal": ((0.55, 0.64, 0.67), 0.20, 0.92),
    },
    "open_office": {
        "label": "Open workspace",
        "category": "office",
        "description": "Bright and neutral",
        "wall": ((0.88, 0.89, 0.86), 0.77, 0.0),
        "floor": ((0.48, 0.52, 0.50), 0.78, 0.0),
        "balcony": ((0.59, 0.63, 0.59), 0.82, 0.0),
        "door": ((0.49, 0.52, 0.48), 0.58, 0.0),
        "glass": ((0.61, 0.78, 0.82), 0.09, 0.0),
        "metal": ((0.43, 0.47, 0.47), 0.24, 0.76),
    },
    "warm_office": {
        "label": "Warm collaborative",
        "category": "office",
        "description": "Timber and inviting tones",
        "wall": ((0.83, 0.82, 0.74), 0.82, 0.0),
        "floor": ((0.56, 0.42, 0.29), 0.63, 0.0),
        "balcony": ((0.61, 0.58, 0.50), 0.84, 0.0),
        "door": ((0.44, 0.30, 0.19), 0.48, 0.0),
        "glass": ((0.65, 0.79, 0.78), 0.10, 0.0),
        "metal": ((0.38, 0.41, 0.39), 0.25, 0.79),
    },
    "executive_office": {
        "label": "Executive",
        "category": "office",
        "description": "Dark stone and walnut",
        "wall": ((0.71, 0.68, 0.63), 0.62, 0.0),
        "floor": ((0.24, 0.25, 0.27), 0.51, 0.0),
        "balcony": ((0.50, 0.50, 0.49), 0.75, 0.0),
        "door": ((0.28, 0.19, 0.12), 0.41, 0.0),
        "glass": ((0.54, 0.68, 0.73), 0.10, 0.0),
        "metal": ((0.39, 0.35, 0.28), 0.25, 0.84),
    },
    "gallery": {
        "label": "Gallery",
        "category": "showroom",
        "description": "White display walls",
        "wall": ((0.93, 0.93, 0.91), 0.82, 0.0),
        "floor": ((0.76, 0.76, 0.71), 0.55, 0.0),
        "balcony": ((0.74, 0.73, 0.69), 0.77, 0.0),
        "door": ((0.62, 0.63, 0.60), 0.45, 0.0),
        "glass": ((0.72, 0.85, 0.88), 0.07, 0.0),
        "metal": ((0.59, 0.60, 0.57), 0.23, 0.80),
    },
    "luxury_showroom": {
        "label": "Luxury display",
        "category": "showroom",
        "description": "Dark stone and brass",
        "wall": ((0.56, 0.51, 0.42), 0.49, 0.0),
        "floor": ((0.18, 0.18, 0.17), 0.30, 0.06),
        "balcony": ((0.47, 0.43, 0.38), 0.55, 0.0),
        "door": ((0.25, 0.20, 0.16), 0.31, 0.08),
        "glass": ((0.53, 0.67, 0.69), 0.06, 0.0),
        "metal": ((0.69, 0.54, 0.28), 0.21, 0.84),
    },
    "tech_showroom": {
        "label": "Technology display",
        "category": "showroom",
        "description": "Charcoal and cool metals",
        "wall": ((0.62, 0.67, 0.70), 0.51, 0.0),
        "floor": ((0.17, 0.24, 0.29), 0.36, 0.16),
        "balcony": ((0.45, 0.54, 0.59), 0.54, 0.0),
        "door": ((0.23, 0.29, 0.34), 0.33, 0.42),
        "glass": ((0.46, 0.77, 0.86), 0.08, 0.0),
        "metal": ((0.36, 0.49, 0.57), 0.22, 0.89),
    },
}


def _pxr():
    try:
        from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdPhysics, UsdShade
    except ImportError as exc:
        raise RuntimeError("OpenUSD is unavailable. Run omni_setup/setup.sh first.") from exc
    return Gf, Sdf, Usd, UsdGeom, UsdLux, UsdPhysics, UsdShade


def _make_material(stage, path: str, spec: tuple, modules):
    Gf, Sdf, _, _, _, _, UsdShade = modules
    rgb, roughness, metallic = spec
    material = UsdShade.Material.Define(stage, path)
    shader = UsdShade.Shader.Define(stage, path + "/PBR")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*rgb))
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(float(roughness))
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(float(metallic))
    if path.endswith("/glass"):
        shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(0.24)
    shader.CreateOutput("surface", Sdf.ValueTypeNames.Token)
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return material


def _bind(prim, material, modules):
    *_, UsdShade = modules
    UsdShade.MaterialBindingAPI.Apply(prim).Bind(material)


def _wood_floor_texture(stage, material, output_path, modules):
    """Use the installed SimReady walnut map with metre-based floor UVs."""
    _, Sdf, _, _, _, _, UsdShade = modules
    root = Path(os.environ.get('BLUEPRINT_STUDIO_ASSET_ROOT', '/home/ovqa/Repos/OmniverseAssets'))
    texture = root / 'SimReady_Furniture_Misc_01/Assets/simready_content/common_assets/props/desk_01/textures/Walnut_BaseColor.png'
    if not texture.is_file():
        return
    base = str(material.GetPath())
    reader = UsdShade.Shader.Define(stage, base + '/UV')
    reader.CreateIdAttr('UsdPrimvarReader_float2')
    reader.CreateInput('varname', Sdf.ValueTypeNames.Token).Set('st')
    reader.CreateOutput('result', Sdf.ValueTypeNames.Float2)
    sampler = UsdShade.Shader.Define(stage, base + '/Walnut')
    sampler.CreateIdAttr('UsdUVTexture')
    sampler.CreateInput('file', Sdf.ValueTypeNames.Asset).Set(os.path.relpath(texture, output_path.parent))
    sampler.CreateInput('sourceColorSpace', Sdf.ValueTypeNames.Token).Set('sRGB')
    sampler.CreateInput('wrapS', Sdf.ValueTypeNames.Token).Set('repeat')
    sampler.CreateInput('wrapT', Sdf.ValueTypeNames.Token).Set('repeat')
    sampler.CreateInput('st', Sdf.ValueTypeNames.Float2).ConnectToSource(reader.ConnectableAPI(), 'result')
    sampler.CreateOutput('rgb', Sdf.ValueTypeNames.Float3)
    UsdShade.Shader.Get(stage, base + '/PBR').GetInput('diffuseColor').ConnectToSource(sampler.ConnectableAPI(), 'rgb')
    material.GetPrim().SetCustomDataByKey('textureSource', 'NVIDIA SimReady desk_01 walnut; illustrative finish')


def _box(stage, path, center, size, yaw_degrees, material, modules, collision=True):
    Gf, _, _, UsdGeom, _, UsdPhysics, _ = modules
    box = UsdGeom.Cube.Define(stage, path)
    box.CreateSizeAttr(1.0)
    xform = UsdGeom.Xformable(box.GetPrim())
    xform.AddTranslateOp().Set(Gf.Vec3d(*map(float, center)))
    xform.AddRotateZOp().Set(float(yaw_degrees))
    xform.AddScaleOp().Set(Gf.Vec3f(*map(float, size)))
    _bind(box.GetPrim(), material, modules)
    if collision:
        UsdPhysics.CollisionAPI.Apply(box.GetPrim())
    return box.GetPrim()


def _slab(stage, path, polygon, material, modules, top=0.0, depth=0.15, holes=()):
    Gf, Sdf, _, UsdGeom, _, UsdPhysics, _ = modules
    xy = [tuple(map(float, p[:2])) for p in polygon]
    if len(xy) > 3 and xy[0] == xy[-1]:
        xy.pop()
    rings = [xy] + [[tuple(map(float, p[:2])) for p in ring] for ring in holes]
    if holes:
        from shapely import constrained_delaunay_triangles
        from shapely.geometry import Polygon
        xy = [point for ring in rings for point in ring]
        indices = {point: i for i, point in enumerate(xy)}
        triangles = []
        for triangle in constrained_delaunay_triangles(Polygon(rings[0], rings[1:])).geoms:
            face = [indices[tuple(p)] for p in list(triangle.exterior.coords)[:3]]
            a, b, c = [xy[i] for i in face]
            if (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]) < 0:
                face.reverse()
            triangles.append(face)
    else:
        triangles = triangulate(xy)
    n = len(xy)
    points = [Gf.Vec3f(x, y, top) for x, y in xy] + [Gf.Vec3f(x, y, top - depth) for x, y in xy]
    faces = [list(face) for face in triangles]
    faces += [[c + n, b + n, a + n] for a, b, c in triangles]
    offset = 0
    for ring in rings:
        for k in range(len(ring)):
            i, j = offset+k, offset+(k+1)%len(ring)
            faces.append([i, i+n, j+n, j])
        offset += len(ring)
    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.CreatePointsAttr(points)
    mesh.CreateFaceVertexCountsAttr([len(face) for face in faces])
    mesh.CreateFaceVertexIndicesAttr([index for face in faces for index in face])
    mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    mesh.CreateDoubleSidedAttr(True)
    UsdGeom.PrimvarsAPI(mesh).CreatePrimvar('st', Sdf.ValueTypeNames.TexCoord2fArray,
                                         UsdGeom.Tokens.vertex).Set(
        [Gf.Vec2f(p[0] / 2, p[1] / 2) for p in points])
    _bind(mesh.GetPrim(), material, modules)
    UsdPhysics.CollisionAPI.Apply(mesh.GetPrim())
    return mesh.GetPrim()


def _wall_piece(stage, base, number, a, b, begin, end, z0, z1, thickness, material, modules):
    length = segment_length(a, b)
    if end - begin < 0.005 or z1 - z0 < 0.005 or length < 0.005:
        return
    ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
    mid = (begin + end) / 2
    center = (a[0] + ux * mid, a[1] + uy * mid, (z0 + z1) / 2)
    return _box(stage, f"{base}/Piece_{number:03d}", center, (end - begin, thickness, z1 - z0), math.degrees(math.atan2(uy, ux)), material, modules)


def _openings_for_wall(wall, index, all_openings):
    wall_id = str(wall.get("id", index))
    result = []
    for opening in all_openings:
        assoc = opening.get("wall_id", opening.get("wall", opening.get("wall_index")))
        if assoc is None or str(assoc) != wall_id:
            continue
        result.append(opening)
    return result


def _opening_center(opening, a, b, length):
    for key in ("offset_m", "distance_m", "center_m"):
        if key in opening:
            return float(opening[key])
    p = opening.get("center", opening.get("position"))
    if isinstance(p, (list, tuple)) and len(p) >= 2:
        return max(0.0, min(length, ((float(p[0]) - a[0]) * (b[0] - a[0]) + (float(p[1]) - a[1]) * (b[1] - a[1])) / length))
    return length / 2


def _derive_walls(plan):
    if plan.get("wall_segments"):
        return plan["wall_segments"]
    seen = set()
    walls = []
    shapes = []
    if plan.get("footprint", {}).get("polygon"):
        shapes.append(("outer", plan["footprint"]["polygon"]))
    shapes.extend(("inner", room["polygon"]) for room in plan.get("rooms", []))
    for kind, polygon in shapes:
        for i, a in enumerate(polygon):
            b = polygon[(i + 1) % len(polygon)]
            key = tuple(sorted((tuple(round(float(v), 3) for v in a[:2]), tuple(round(float(v), 3) for v in b[:2]))))
            if key in seen:
                continue
            seen.add(key)
            walls.append({"id": f"wall_{len(walls)+1}", "start": a[:2], "end": b[:2], "kind": kind, "thickness_m": 0.18 if kind == "outer" else 0.12, "confidence": "derived"})
    return walls


def _safe_asset_path(value: str, scene_path: Path) -> str:
    # Only the dedicated Omniverse asset library can be referenced. In
    # particular, never let arbitrary local paths leak into authored USD.
    root = Path(os.environ.get("BLUEPRINT_STUDIO_ASSET_ROOT", "/home/ovqa/Repos/OmniverseAssets")).expanduser().resolve()
    asset = Path(value).expanduser().absolute()
    if not asset.is_file() or not asset.is_relative_to(root) or not asset.resolve().is_relative_to(root):
        raise ValueError(f"SimReady asset must exist under {root}")
    # Preserve symlink-based overlays so relative MDL imports resolve through
    # the overlay while validation still checks the underlying asset library.
    return os.path.relpath(asset, scene_path.parent)


def _configure_asset_physics(stage, placement_prim, model, placement, furniture_material, modules):
    """Use a SimReady collider variant, with a bounded proxy as a fallback."""
    Gf, _, Usd, UsdGeom, _, UsdPhysics, UsdShade = modules
    mode = str(placement.get("physics_mode", "static")).strip().lower()
    if mode not in {"none", "static", "dynamic"}:
        raise ValueError("asset physics_mode must be none, static, or dynamic")
    placement_prim.SetCustomDataByKey("physicsMode", mode)
    if mode == "none":
        return

    physics_variant = model.GetVariantSet("PhysicsVariant")
    selected_variant = physics_variant.IsValid() and "RigidBody" in physics_variant.GetVariantNames()
    if selected_variant:
        # The curated SimReady files select "None" by default. Their other
        # variant supplies authored convex-decomposition colliders, which are
        # more faithful than a generated bounding box.
        physics_variant.SetVariantSelection("RigidBody")

    colliders = sum(
        prim.HasAPI(UsdPhysics.CollisionAPI)
        for prim in Usd.PrimRange(model, Usd.TraverseInstanceProxies())
    )
    if not colliders:
        bound = UsdGeom.BBoxCache(
            Usd.TimeCode.Default(),
            [UsdGeom.Tokens.default_, UsdGeom.Tokens.render, UsdGeom.Tokens.proxy],
        ).ComputeLocalBound(model).ComputeAlignedBox()
        if bound.IsEmpty():
            raise ValueError("SimReady asset has no bounded geometry for a collision proxy")
        minimum, maximum = bound.GetMin(), bound.GetMax()
        center = [(float(minimum[i]) + float(maximum[i])) / 2 for i in range(3)]
        size = [max(0.02, float(maximum[i]) - float(minimum[i])) for i in range(3)]
        proxy = UsdGeom.Cube.Define(stage, str(model.GetPath()) + "/CollisionProxy")
        proxy.CreateSizeAttr(1.0)
        proxy.CreateVisibilityAttr(UsdGeom.Tokens.invisible)
        xform = UsdGeom.Xformable(proxy.GetPrim())
        xform.AddTranslateOp().Set(Gf.Vec3d(*center))
        xform.AddScaleOp().Set(Gf.Vec3f(*size))
        UsdPhysics.CollisionAPI.Apply(proxy.GetPrim())
        placement_prim.SetCustomDataByKey("colliderSource", "boundsProxy")
    else:
        placement_prim.SetCustomDataByKey(
            "colliderSource", "simReadyVariant" if selected_variant else "asset")

    UsdShade.MaterialBindingAPI.Apply(model).Bind(
        furniture_material, UsdShade.Tokens.weakerThanDescendants, "physics")
    rigid_body = UsdPhysics.RigidBodyAPI.Get(stage, model.GetPath())
    if mode == "dynamic":
        if not rigid_body:
            rigid_body = UsdPhysics.RigidBodyAPI.Apply(model)
        rigid_body.CreateRigidBodyEnabledAttr(True)
        mass_kg = placement.get("mass_kg")
        if mass_kg is not None:
            mass_kg = float(mass_kg)
            if not math.isfinite(mass_kg) or mass_kg <= 0:
                raise ValueError("asset mass_kg must be a positive finite number")
            UsdPhysics.MassAPI.Apply(model).CreateMassAttr(mass_kg)
        elif not colliders:
            # The proxy encloses the object's empty space; use an indicative
            # furniture bulk density rather than the SDK's solid-material
            # default. A measured mass_kg can override this estimate.
            UsdPhysics.MassAPI.Apply(model).CreateDensityAttr(80.0)
    elif rigid_body:
        # NVIDIA's USD Physics guide says disabling the body leaves its child
        # colliders as static geometry. This keeps the asset in place while
        # preserving the vendor's detailed collision shapes.
        rigid_body.CreateRigidBodyEnabledAttr(False)


def build_usd(plan: dict, output_path: str | Path, style: str = "contemporary") -> dict:
    """Build one style; return paths and measured/declared area notes."""
    if style not in PALETTES:
        raise ValueError(f"Unknown style: {style}")
    errors = validate_plan(plan)
    if errors:
        raise ValueError("; ".join(errors))
    modules = _pxr()
    Gf, _, Usd, UsdGeom, UsdLux, UsdPhysics, _ = modules
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()
    stage = usdex.core.createStage(
        identifier=str(output_path), defaultPrimName="World",
        upAxis=UsdGeom.Tokens.z, linearUnits=UsdGeom.LinearUnits.meters,
        authoringMetadata="Blueprint Studio",
    )
    if stage is None:
        raise RuntimeError(f"Could not create USD stage at {output_path}")
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    stage.GetRootLayer().comment = "Generated from a reviewed plan; see prim metadata for source and uncertainty. Z-up, metres."
    world.GetPrim().SetCustomDataByKey("planName", str(plan.get("name", "Untitled plan")))
    world.GetPrim().SetCustomDataByKey("source", json.dumps(plan.get("source", {}), ensure_ascii=False))
    world.GetPrim().SetCustomDataByKey("heightStatus", str(plan.get("height_status", "user provided or assumed")))
    world.GetPrim().SetCustomDataByKey("style", style)
    world.GetPrim().SetCustomDataByKey('traceCalibration', json.dumps(plan.get('calibration', {})))
    world.GetPrim().SetCustomDataByKey('wallTrace', json.dumps(plan.get('source_wall_segments', plan.get('wall_segments', []))))
    if plan.get("area_schedule_m2"):
        world.GetPrim().SetCustomDataByKey("areaScheduleM2", json.dumps(plan["area_schedule_m2"]))
    world.GetPrim().SetCustomDataByKey('dimensionModel', plan.get('dimension_model', 'raster'))
    world.GetPrim().SetCustomDataByKey('dimensionNote', plan.get('dimension_note', 'Raster trace in meters; dimensions not constrained'))
    style_specs = PALETTES[style]
    materials = {key: _make_material(stage, f"/World/Looks/{safe_name(key)}", spec, modules) for key, spec in style_specs.items() if isinstance(spec, tuple)}
    if style in {'contemporary', 'classic', 'warm_office', 'executive_office'}:
        _wood_floor_texture(stage, materials['floor'], output_path, modules)
    materials['tile'] = _make_material(stage, '/World/Looks/tile', ((.65, .63, .58), .45, 0), modules)
    height = float(plan.get("room_height_m") or 2.9)
    physics_scene = UsdPhysics.Scene.Define(stage, "/World/PhysicsScene")
    physics_scene.CreateGravityDirectionAttr(Gf.Vec3f(0, 0, -1))
    physics_scene.CreateGravityMagnitudeAttr(9.81)

    footprint = plan.get("footprint", {}).get("polygon", [])
    rooms = plan.get("rooms", [])
    if footprint:
        floor = _slab(stage, "/World/Building/FloorSlab", footprint, materials["floor"], modules, holes=plan.get("footprint", {}).get("holes", []))
        floor.SetCustomDataByKey("traceConfidence", str(plan.get("footprint", {}).get("confidence", "reviewed")))
    elif rooms:
        for i, room in enumerate(rooms):
            _slab(stage, f"/World/Building/Floor_{i:03d}", room["polygon"], materials["floor"], modules)
    for i, room in enumerate(rooms):
        room_prim = UsdGeom.Xform.Define(stage, f"/World/Spaces/{safe_name(room.get('id', f'room_{i}'))}").GetPrim()
        room_prim.SetCustomDataByKey("label", str(room.get("name", room.get("id", "Room"))))
        room_prim.SetCustomDataByKey("polygonM", json.dumps(room["polygon"]))
        room_prim.SetCustomDataByKey("category", str(room.get("category", "room")))
        room_prim.SetCustomDataByKey('dimensionMode', room.get('dimension_mode', 'raster'))
        room_prim.SetCustomDataByKey('spanAxis', int(room.get('span_axis', -1)))
        if room.get('dimension_mode'):
            category = room.get('category')
            finish = materials['balcony'] if category == 'balcony' else materials['tile'] if category in {'bathroom','kitchen','service'} else materials['floor']
            _slab(stage, str(room_prim.GetPath()) + '/Floor', room['polygon'], finish, modules, top=.008, depth=.008)

        room_prim.SetCustomDataByKey("printedDimensionsM", json.dumps(room.get("dimensions_m", [])))
        room_prim.SetCustomDataByKey("tracedAreaM2", round(polygon_area(room["polygon"]), 4))
        room_prim.SetCustomDataByKey("confidence", str(room.get("confidence", "reviewed")))
        room_prim.SetCustomDataByKey("provenance", json.dumps(room.get("provenance", {}), ensure_ascii=False))
        for source_key, target_key in (("dimension_provenance", "dimensionProvenance"), ("geometry_provenance", "geometryProvenance")):
            if source_key in room:
                room_prim.SetCustomDataByKey(target_key, str(room[source_key]))
        if "geometry_uncertainty_m" in room:
            room_prim.SetCustomDataByKey("geometryUncertaintyM", float(room["geometry_uncertainty_m"]))
        if "balcon" in str(room.get("category", "")).lower():
            _slab(stage, f"/World/Building/BalconyFinish_{i:03d}", room["polygon"], materials["balcony"], modules, top=0.007, depth=0.008)
        elif room.get('category') in {'bathroom', 'kitchen', 'service'}:
            _slab(stage, f'/World/Building/RoomFinish_{i:03d}', room['polygon'], materials['tile'], modules, top=.006, depth=.007)

    balconies = plan.get("balconies", [])
    for i, balcony in enumerate(balconies):
        poly = balcony.get("polygon", [])
        if not poly:
            continue
        prim = _slab(stage, f"/World/Building/Balcony_{i:03d}", poly, materials["balcony"], modules, top=-0.025, depth=0.15)
        prim.SetCustomDataByKey("printedDimensionsM", json.dumps(balcony.get("dimensions_m", [])))

    walls = _derive_walls(plan)
    for i, wall in enumerate(walls):
        a = [float(v) for v in wall["start"][:2]]
        b = [float(v) for v in wall["end"][:2]]
        length = segment_length(a, b)
        if length < 0.005:
            continue
        wall_id = safe_name(wall.get("id", f"wall_{i}"))
        base = f"/World/Building/Walls/{wall_id}"
        wall_prim = UsdGeom.Xform.Define(stage, base).GetPrim()
        wall_prim.SetCustomDataByKey("traceConfidence", str(wall.get("confidence", "reviewed")))
        wall_prim.SetCustomDataByKey("kind", str(wall.get("kind", "wall")))
        for source_key, target_key in (("geometry_provenance", "geometryProvenance"), ("height_thickness_provenance", "heightThicknessProvenance")):
            if source_key in wall:
                wall_prim.SetCustomDataByKey(target_key, str(wall[source_key]))
        if "geometry_uncertainty_m" in wall:
            wall_prim.SetCustomDataByKey("geometryUncertaintyM", float(wall["geometry_uncertainty_m"]))
        wall_kind = str(wall.get("kind", "")).lower()
        is_guard = "guard" in wall_kind or "rail" in wall_kind
        is_glazed = "glaz" in wall_kind or "window" in wall_kind
        wall_height = float(wall.get("height_m") or (1.1 if is_guard else height))
        wall_material = materials["metal"] if is_guard else materials["glass"] if is_glazed else materials["wall"]
        thickness = float(wall.get("thickness_m") or (0.05 if is_guard else 0.18 if wall.get("kind") in ("outer", "exterior") else 0.12))
        if is_guard:
            # A railing is not a solid one-metre-high metal wall. These are
            # illustrative assemblies; the source only locates the boundary.
            _wall_piece(stage, base, 0, a, b, 0, length, .06, wall_height-.06, .018, materials['glass'], modules)
            _wall_piece(stage, base, 1, a, b, 0, length, wall_height-.05, wall_height, .055, materials['metal'], modules)
            for post in range(max(1, math.ceil(length / 1.2)) + 1):
                offset = length * post / max(1, math.ceil(length / 1.2))
                _wall_piece(stage, base, post+2, a, b, max(0, offset-.025), min(length, offset+.025), 0, wall_height, .05, materials['metal'], modules)
            wall_prim.SetCustomDataByKey('assemblyNote', 'Illustrative glass railing; specification unmeasured')
            continue
        openings = _openings_for_wall(wall, i, plan.get("openings", []))
        intervals = []
        for opening in openings:
            width = min(length, max(0.2, float(opening.get("width_m") or 0.9)))
            center = _opening_center(opening, a, b, length)
            start, end = max(0, center - width / 2), min(length, center + width / 2)
            if end - start >= 0.2:
                intervals.append((start, end, opening))
        intervals.sort(key=lambda item: item[0])
        cursor = 0.0
        piece = 0
        for start, end, opening in intervals:
            if start < cursor:
                continue
            _wall_piece(stage, base, piece, a, b, cursor, start, 0, wall_height, thickness, wall_material, modules)
            piece += 1
            kind = str(opening.get("type", opening.get("kind", "door"))).lower()
            if "window" in kind or "glaz" in kind:
                sill = float(opening.get("sill_m", 0.9))
                top = min(wall_height, sill + float(opening.get("height_m", 1.3)))
                _wall_piece(stage, base, piece, a, b, start, end, 0, sill, thickness, wall_material, modules)
                piece += 1
                _wall_piece(stage, base, piece, a, b, start, end, top, wall_height, thickness, wall_material, modules)
                piece += 1
                _wall_piece(stage, base, piece, a, b, start, end, sill, top, min(0.025, thickness / 4), materials["glass"], modules)
                piece += 1
            else:
                door_height = min(wall_height - 0.1, float(opening.get("height_m", 2.1)))
                _wall_piece(stage, base, piece, a, b, start, end, door_height, wall_height, thickness, wall_material, modules)
                piece += 1
                # A thin visible door leaf leaves the physics opening passable.
                _wall_piece(stage, base, piece, a, b, start + 0.02, end - 0.02, 0.02, door_height - 0.02, min(0.04, thickness / 3), materials["door"], modules)
                door_prim = stage.GetPrimAtPath(f"{base}/Piece_{piece:03d}")
                if door_prim:
                    door_prim.RemoveAPI(UsdPhysics.CollisionAPI)
                piece += 1
            cursor = end
        _wall_piece(stage, base, piece, a, b, cursor, length, 0, wall_height, thickness, wall_material, modules)
        if is_glazed:
            _wall_piece(stage, base, piece + 1, a, b, 0, length, 0, 0.055, min(0.06, thickness), materials["metal"], modules)
            _wall_piece(stage, base, piece + 2, a, b, 0, length, wall_height - 0.055, wall_height, min(0.06, thickness), materials["metal"], modules)
            divisions = max(1, math.ceil(length / 1.1))
            for post in range(divisions + 1):
                offset = length * post / divisions
                _wall_piece(stage, base, piece+3+post, a, b, max(0, offset-.025), min(length, offset+.025), 0, wall_height, .055, materials['metal'], modules)

    # The B1 trace already splits walls around doors. Complete these gaps with
    # lintels and slim jambs, without inventing a closed leaf or blocking travel.
    for i, opening in enumerate(plan.get('openings', [])):
        if not opening.get('free_opening') or not opening.get('start') or not opening.get('end'):
            continue
        a, b = opening['start'], opening['end']
        length = segment_length(a, b)
        base = f'/World/Building/Openings/{safe_name(opening.get("id", str(i)))}'
        UsdGeom.Xform.Define(stage, base).GetPrim().SetCustomDataByKey('assemblyNote', 'Illustrative jambs and lintel; opening positions traced, assembly dimensions assumed')
        head = min(height-.1, float(opening.get('height_m', 2.2)))
        _wall_piece(stage, base, 0, a, b, 0, length, head, height, .15, materials['wall'], modules)
        if opening.get('type') != 'opening':
            _wall_piece(stage, base, 1, a, b, 0, .035, 0, head, .16, materials['door'], modules)
            _wall_piece(stage, base, 2, a, b, length-.035, length, 0, head, .16, materials['door'], modules)
            _wall_piece(stage, base, 3, a, b, .035, length-.035, head-.035, head, .16, materials['door'], modules)

    physics_specs = {
        "Masonry": (0.72, 0.56, 0.08),
        "FinishedFloor": (0.65, 0.48, 0.06),
        "Metal": (0.48, 0.36, 0.12),
        "Glass": (0.40, 0.30, 0.04),
        "Furniture": (0.58, 0.42, 0.05),
    }
    physics_materials = {}
    for name, (static_friction, dynamic_friction, restitution) in physics_specs.items():
        material = modules[-1].Material.Define(stage, f"/World/PhysicsMaterials/{name}")
        api = UsdPhysics.MaterialAPI.Apply(material.GetPrim())
        api.CreateStaticFrictionAttr(static_friction)
        api.CreateDynamicFrictionAttr(dynamic_friction)
        api.CreateRestitutionAttr(restitution)
        physics_materials[name] = material
    for prim in stage.Traverse():
        path = str(prim.GetPath())
        if not path.startswith("/World/Building/") or not prim.HasAPI(UsdPhysics.CollisionAPI):
            continue
        if "Balcony" in path or "Floor" in path:
            material = physics_materials["FinishedFloor"]
        elif "guard" in path.lower():
            material = physics_materials["Metal"]
        elif "glaz" in path.lower():
            material = physics_materials["Glass"]
        else:
            material = physics_materials["Masonry"]
        modules[-1].MaterialBindingAPI.Apply(prim).Bind(material, modules[-1].Tokens.weakerThanDescendants, "physics")
    world.GetPrim().SetCustomDataByKey("physicsMaterialNote", "Indicative dry-surface friction/restitution; site-specific engineering values need confirmation")

    for i, placement in enumerate(plan.get("asset_placements", [])):
        path = _safe_asset_path(str(placement["asset_path"]), output_path)
        prim = UsdGeom.Xform.Define(stage, f"/World/Assets/{safe_name(placement.get('id', f'asset_{i}'))}").GetPrim()
        position = placement.get("position", [0, 0, 0])
        UsdGeom.Xformable(prim).AddTranslateOp().Set(Gf.Vec3d(*map(float, position)))
        UsdGeom.Xformable(prim).AddRotateZOp().Set(float(placement.get("rotation_deg", 0)))
        # Reference below a placement wrapper: many SimReady roots already
        # author translate/rotate/scale ops and cannot accept duplicate ops.
        model = UsdGeom.Xform.Define(stage, str(prim.GetPath()) + "/Model").GetPrim()
        model.GetReferences().AddReference(path)
        prim.SetCustomDataByKey("simReady", True)
        _configure_asset_physics(stage, prim, model, placement,
                                 physics_materials["Furniture"], modules)

    warm_styles = {"contemporary", "classic", "home_luxury", "warm_office", "executive_office", "luxury_showroom"}
    cool_styles = {"factory", "hightech_factory", "tech_showroom"}
    if style in warm_styles:
        sky_intensity, sky_color, sun_intensity, sun_color = 360.0, (1.0, 0.92, 0.82), 2200.0, (1.0, 0.88, 0.75)
    elif style in cool_styles:
        sky_intensity, sky_color, sun_intensity, sun_color = 480.0, (0.79, 0.89, 1.0), 2700.0, (0.89, 0.95, 1.0)
    else:
        sky_intensity, sky_color, sun_intensity, sun_color = 420.0, (0.94, 0.96, 1.0), 2500.0, (1.0, 0.99, 0.96)
    dome = UsdLux.DomeLight.Define(stage, "/World/Lighting/Sky")
    dome.CreateIntensityAttr(sky_intensity)
    dome.CreateColorAttr(Gf.Vec3f(*sky_color))
    area_polygons = [footprint] if footprint else [r["polygon"] for r in rooms]
    minx, miny, maxx, maxy = bbox(area_polygons)
    sun = UsdLux.DistantLight.Define(stage, "/World/Lighting/Sun")
    sun.CreateIntensityAttr(sun_intensity)
    sun.CreateColorAttr(Gf.Vec3f(*sun_color))
    sun.CreateAngleAttr(0.53)
    UsdGeom.Xformable(sun.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(45, -25, 35))
    stage.SetStartTimeCode(0)
    stage.SetEndTimeCode(0)
    stage.GetRootLayer().Save()
    return {
        "usd_path": str(output_path),
        "style": style,
        "footprint_area_m2": round(polygon_area(footprint) - sum(polygon_area(h) for h in plan.get("footprint", {}).get("holes", [])), 2) if footprint else None,
        "traced_room_area_m2": round(sum(polygon_area(r["polygon"]) for r in rooms), 2),
        "room_count": len(rooms),
        "wall_count": len(walls),
        "bounds_m": [minx, miny, maxx, maxy],
        "height_m": height,
        "height_status": plan.get("height_status", "assumed"),
        "source": plan.get("source", {}),
    }


def build_style_variants(plan: dict, output_dir: str | Path) -> dict:
    """Build every palette and a composition file with a USD style variant."""
    Gf, _, Usd, UsdGeom, _, _, _ = _pxr()
    del Gf
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    category = plan.get("structure_type", "home")
    selected_styles = [name for name, spec in PALETTES.items() if category == "other" or spec["category"] == category]
    if not selected_styles:
        raise ValueError(f"No styles available for {category}")
    reports = {style: build_usd(plan, output_dir / f"{style}.usda", style) for style in selected_styles}
    variants_path = output_dir / "all_styles.usda"
    if variants_path.exists():
        variants_path.unlink()
    stage = Usd.Stage.CreateNew(str(variants_path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    root = UsdGeom.Xform.Define(stage, "/World").GetPrim()
    stage.SetDefaultPrim(root)
    variants = root.GetVariantSets().AddVariantSet("architecturalStyle")
    for style in selected_styles:
        variants.AddVariant(style)
        variants.SetVariantSelection(style)
        with variants.GetVariantEditContext():
            root.GetReferences().AddReference(f"{style}.usda")
    variants.SetVariantSelection(selected_styles[0])
    stage.GetRootLayer().Save()
    return {"variants_path": str(variants_path), "styles": reports}
