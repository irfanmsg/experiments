"""Author metre-accurate, Z-up OpenUSD buildings from reviewed plan geometry.

This module deliberately uses OpenUSD for persistent authoring. ovstage,
ovrtx, and ovstream consume the resulting scene at runtime.
"""

from __future__ import annotations

import json
import hashlib
import math
import os
from pathlib import Path

import usdex.core

from .asset_library import DEFAULT_ASSET_ROOT
from .geometry import bbox, measured_scale_audit, polygon_area, safe_name, segment_length, triangulate, validate_plan


PALETTES = {
    "home_specification": {
        "label": "B1-1502 specified finishes",
        "category": "home",
        "description": "Annexure F: vitrified tiles, master bedroom wood, ceramic bathrooms and granite kitchen",
        "wall": ((.89, .88, .84), .78, 0.0),
        "floor": ((.74, .72, .67), .30, 0.0),
        "balcony": ((.58, .55, .50), .86, 0.0),
        "door": ((.38, .23, .13), .42, 0.0),
        "glass": ((.65, .78, .81), .08, 0.0),
        "metal": ((.62, .65, .66), .22, .90),
    },
    "contemporary": {
        "label": "Warm neutral finishes",
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
        "label": "Light neutral finishes",
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
        "label": "Cream and walnut",
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
        "label": "Concrete and steel",
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
        "label": "Stone and bronze",
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


INTERIOR_SCHEMES = {
    'saved_linen_timber': {
        'label': 'Linen & light timber', 'url': 'https://www.instagram.com/p/DclJJ7wmeQX/',
        'description': 'Cream textiles, timber display, linen folds, woven rug and warm cone pendants',
        'wall': (.91, .88, .80), 'wood': (.54, .34, .16), 'textile': (.88, .83, .72),
        'accent': (.65, .49, .29), 'rug': (.67, .60, .47), 'ink': (.34, .39, .33),
        'metal': (.61, .43, .22), 'light_kelvin': 3100, 'sky': 290, 'sun': 1800,
        'features': ['cream upholstery', 'timber display and books', 'pleated linen curtains', 'woven rug', 'cone pendants', 'framed geometric art', 'plants'],
        'generic_description': 'Cream walls, a woven rug, a pale cone floor lamp and greenery',
        'generic_features': ['cream wall finish', 'woven rug', 'pale cone floor lamp', 'potted greenery'],
    },
    'saved_evening_lounge': {
        'label': 'Warm evening lounge', 'url': 'https://www.instagram.com/p/Dce9CWFqgnn/',
        'description': 'Olive beige upholstery, graphic posters, timber console and pools of warm practical light',
        'wall': (.77, .74, .65), 'wood': (.34, .20, .10), 'textile': (.45, .47, .34),
        'accent': (.64, .30, .15), 'rug': (.77, .73, .63), 'ink': (.10, .13, .12),
        'metal': (.20, .18, .14), 'light_kelvin': 2700, 'sky': 95, 'sun': 240,
        'features': ['olive beige upholstery', 'graphic rug and posters', 'opal globe floor lamp', 'mushroom and amber table lamps', 'timber media console', 'books and greenery'],
        'generic_description': 'Warm neutral walls, a graphic rug, a globe floor lamp and greenery',
        'generic_features': ['warm neutral wall finish', 'graphic rug', 'globe floor lamp', 'potted greenery'],
    },
    'saved_botanical_cane': {
        'label': 'Botanical cane & terracotta', 'url': 'https://www.instagram.com/p/DYi4XJVod1V/',
        'description': 'Cane details, terracotta cushions, botanical accents, woven shades and layered greenery',
        'wall': (.89, .87, .79), 'wood': (.43, .27, .13), 'textile': (.83, .80, .70),
        'accent': (.64, .27, .14), 'rug': (.70, .60, .40), 'ink': (.24, .35, .18),
        'metal': (.45, .32, .19), 'light_kelvin': 3000, 'sky': 310, 'sun': 1600,
        'features': ['cane headboards and cabinet fronts', 'terracotta and botanical cushions', 'woven lamp shades', 'small framed gallery', 'linen curtains', 'woven rug', 'layered plants'],
        'generic_description': 'Natural colours, a patterned rug, a woven floor lamp and terracotta plant pots',
        'generic_features': ['natural wall finish', 'patterned rug', 'woven floor lamp', 'terracotta plant pots'],
    },
    'indian_contemporary': {
        'label': 'Contemporary Indian', 'url': 'https://www.studiolotus.in/projects/the-quadrant-house',
        'reference_context': 'Studio Lotus project; contemporary Indian interpretation',
        'description': 'Crafted timber, geometric textile borders, a lattice cabinet front and warm brass pendants',
        'wall': (.89, .83, .72), 'wood': (.32, .16, .07), 'textile': (.80, .70, .51),
        'accent': (.57, .16, .10), 'rug': (.74, .62, .41), 'ink': (.13, .25, .29),
        'metal': (.66, .44, .15), 'light_kelvin': 3100, 'sky': 310, 'sun': 1600,
        'features': ['geometric textile borders', 'timber lattice cabinet front', 'brass pendant shades', 'ochre and indigo cushions', 'framed geometric art', 'timber and greenery'],
        'observed_features': ['Indian-inspired rug motifs', 'patterned textiles', 'crafted timber furnishings', 'contemporary Indian art'],
        'generic_description': 'Warm walls, geometric rug motifs, a brass-tone floor lamp and greenery',
        'generic_features': ['warm wall finish', 'geometric rug motifs', 'brass-tone floor lamp', 'potted greenery'],
    },
    'bohemian': {
        'label': 'Bohemian', 'url': 'https://www.instagram.com/p/DYi4XJVod1V/',
        'reference_context': 'Saved natural-material reference; proposed bohemian interpretation',
        'description': 'Layered patterned rugs, knotted wall hanging, woven shades and mixed indigo and terracotta textiles',
        'wall': (.90, .86, .76), 'wood': (.46, .27, .12), 'textile': (.84, .76, .61),
        'accent': (.66, .25, .13), 'rug': (.67, .52, .32), 'ink': (.13, .22, .35),
        'metal': (.47, .34, .19), 'light_kelvin': 3000, 'sky': 310, 'sun': 1600,
        'features': ['layered patterned rugs', 'knotted textile wall hanging', 'woven pendant shades', 'mixed indigo and terracotta cushions', 'clay accents', 'layered plants'],
        'observed_features': ['woven shades', 'natural-fibre furniture', 'terracotta textiles', 'plants'],
        'generic_description': 'Layered patterned rugs, a woven floor lamp and terracotta plant pots',
        'generic_features': ['warm wall finish', 'layered patterned rugs', 'woven floor lamp', 'terracotta plant pots'],
    },
}
for scheme_id, scheme in INTERIOR_SCHEMES.items():
    PALETTES[scheme_id] = {**PALETTES['home_specification'],
        'label': scheme['label'], 'description': scheme['description'],
        'wall': (scheme['wall'], .82, 0), 'door': (scheme['wood'], .52, 0),
        'metal': (scheme['metal'], .30, .72),
        'requires_reference': False, 'is_design_scheme': True,
        'generic_description': scheme['generic_description']+'; decor added only where a safe candidate fits',
        'generic_design_features': scheme['generic_features'],
        'design_features': scheme['features'], 'reference_urls': [scheme['url']]}


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
    root = Path(os.environ.get('BLUEPRINT_STUDIO_ASSET_ROOT', DEFAULT_ASSET_ROOT)).expanduser()
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
    root = Path(os.environ.get("BLUEPRINT_STUDIO_ASSET_ROOT", DEFAULT_ASSET_ROOT)).expanduser().resolve()
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
        # The child proxy inherits model transforms; its bounds must exclude them.
        bound = UsdGeom.BBoxCache(
            Usd.TimeCode.Default(),
            [UsdGeom.Tokens.default_, UsdGeom.Tokens.render, UsdGeom.Tokens.proxy],
        ).ComputeUntransformedBound(model).ComputeAlignedBox()
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


def _specified_home(stage, plan, materials, modules):
    """Specified finish classes, with explicitly assumed fixture forms and sizes."""
    from shapely.geometry import LineString, Polygon, box
    from shapely.ops import unary_union

    Gf, _, Usd, UsdGeom, _, UsdPhysics, _ = modules
    source = {'file': 'Miami PWC House Documents.pdf', 'pdf_page': 28,
              'printed_page': 23, 'annexure': 'F'}
    decisions = [
        {'id': 'specified_home_finishes', 'kind': 'source-specified', 'source': source,
         'summary': 'Wood in master bedroom; vitrified tiles elsewhere; matte wet-area tiles, 7-foot ceramic bathroom dado, veneer/laminated doors, aluminium glazing, glass rails and granite/stainless kitchen.',
         'parameters': {'master_room_id': 'bedroom_outer_south', 'bathroom_dado_height_m': 2.1336},
         'status': 'source-specified'},
        {'id': 'home_presentation_assumptions', 'kind': 'assumed',
         'source': {'file': 'Layout.jpeg', 'role': 'Placement guide only; room dimensions remain the reviewed metric plan'},
         'summary': 'Tile option, colours, grout, furniture and fixture dimensions/forms are assumed. Layout-guided placements clear doorway approaches and the shown open leaves; no manufacturer geometry is claimed.',
         'parameters': {'tile_size_m': [.6, 1.2], 'grout_m': .003, 'door_clearance_m': .55,
                        'bed_wardrobe_clearance_m': .60,
                        'master_assignment': 'Master bedroom label in Layout.jpeg',
                        'children_toilet_assignment': 'bathroom_outer_north inferred; confirm shower partition assignment'}, 'status': 'needs-review'},
    ]
    rooms = {room['id']: room for room in plan.get('rooms', [])}
    door_shapes = [LineString([o['start'], o['end']]).buffer(.55, cap_style=2)
                   for o in plan.get('openings', []) if o.get('start') and o.get('end')]
    transforms = UsdGeom.XformCache()
    for opening in plan.get('openings', []):
        leaf = stage.GetPrimAtPath('/World/Building/Openings/'+safe_name(opening.get('id', ''))+'/Leaf')
        if not leaf or not leaf.IsA(UsdGeom.Cube):
            continue
        transform = transforms.GetLocalToWorldTransform(leaf)
        half = UsdGeom.Cube(leaf).GetSizeAttr().Get()/2
        corners = [transform.Transform(Gf.Vec3d(x*half, y*half, 0))
                   for x, y in [(-1, -1), (1, -1), (1, 1), (-1, 1)]]
        door_shapes.append(Polygon([(point[0], point[1]) for point in corners]))
    doors = unary_union(door_shapes)
    opening_cuts = unary_union([LineString([o['start'], o['end']]).buffer(.1, cap_style=2)
                                for o in plan.get('openings', []) if o.get('start') and o.get('end')])
    occupied = {key: [] for key in rooms}

    def fixture(room, name, kind, size, preference, parts, yaw=0):
        polygon = Polygon(room['polygon'])
        lowx, lowy, highx, highy = polygon.bounds
        width, depth = size[:2] if yaw == 0 else (size[1], size[0])
        wanted = (lowx+(highx-lowx)*preference[0], lowy+(highy-lowy)*preference[1])
        if highx-lowx < width+.08 or highy-lowy < depth+.08:
            candidates = []
        else:
            # ponytail: fixed placement grid; increase sampling if custom rooms need it.
            xs = [max(lowx+width/2+.04, min(highx-width/2-.04, wanted[0]))]
            ys = [max(lowy+depth/2+.04, min(highy-depth/2-.04, wanted[1]))]
            xs += [lowx+width/2+.04+(highx-lowx-width-.08)*i/5 for i in range(6)]
            ys += [lowy+depth/2+.04+(highy-lowy-depth-.08)*i/5 for i in range(6)]
            candidates = sorted(((x, y) for x in xs for y in ys),
                                key=lambda p: (p[0]-wanted[0])**2+(p[1]-wanted[1])**2)
        for x, y in candidates:
            footprint = box(x-width/2, y-depth/2, x+width/2, y+depth/2)
            if (polygon.covers(footprint) and footprint.intersection(doors).area < 1e-9
                    and all(footprint.intersection(other).area < 1e-9
                            and (room.get('category') != 'bedroom' or {kind, other_kind} != {'bed', 'wardrobe'}
                                 or footprint.distance(other) >= .60)
                            for other_kind, other in occupied[room['id']])):
                break
        else:
            decisions.append({'id': room['id']+'_'+name, 'kind': 'assumed', 'status': 'not-placed',
                              'summary': 'Fixed-size '+kind+' omitted because room/door clearance is insufficient',
                              'parameters': {'size_xyz_m': list(size)}})
            return
        occupied[room['id']].append((kind, footprint))
        base = '/World/Fixtures/'+safe_name(room['id'])+'/'+name
        prim = UsdGeom.Xform.Define(stage, base).GetPrim()
        transform = UsdGeom.Xformable(prim)
        transform.AddTranslateOp().Set(Gf.Vec3d(x, y, .014))
        transform.AddRotateZOp().Set(yaw)
        note = 'Assumed metric size and generic form; Layout.jpeg placement guide, adjusted for measured room and door clearance'
        for key, value in {'assumedFixture': True, 'roomId': room['id'], 'fixtureType': kind,
                           'provenance': note, 'sizeXYZM': Gf.Vec3d(*size)}.items():
            prim.SetCustomDataByKey(key, value)
        for part, center, dimensions, material, rounded in parts:
            if rounded:
                shape = UsdGeom.Sphere.Define(stage, base+'/'+part)
                shape.CreateRadiusAttr(1)
                xf = UsdGeom.Xformable(shape.GetPrim())
                xf.AddTranslateOp().Set(Gf.Vec3d(*center))
                xf.AddScaleOp().Set(Gf.Vec3f(*(v/2 for v in dimensions)))
                _bind(shape.GetPrim(), materials[material], modules)
            else:
                _box(stage, base+'/'+part, center, dimensions, 0, materials[material], modules)
        decisions.append({'id': room['id']+'_'+name, 'kind': 'assumed', 'status': 'needs-review',
                          'summary': note, 'parameters': {'room_id': room['id'], 'fixture_type': kind,
                          'size_xyz_m': list(size), 'position_m': [x, y, .014], 'yaw_deg': yaw}})

    for room in rooms.values():
        polygon = Polygon(room['polygon'])
        path = '/World/Spaces/'+safe_name(room['id'])
        space = stage.GetPrimAtPath(path)
        wet = room.get('category') in {'bathroom', 'balcony'} or room['id'] == 'powder_room'
        finish = 'wood' if room['id'] == 'bedroom_outer_south' else 'matte tile' if wet else 'vitrified tile'
        space.SetCustomDataByKey('floorFinish', finish)
        space.SetCustomDataByKey('finishSource', json.dumps(source))
        if finish != 'wood':
            lowx, lowy, highx, highy = polygon.bounds
            tile_material = materials['matte'] if wet else materials['floor']
            n = 0
            for ix in range(math.ceil((highx-lowx)/.6)):
                for iy in range(math.ceil((highy-lowy)/1.2)):
                    tile = polygon.intersection(box(lowx+ix*.6+.0015, lowy+iy*1.2+.0015,
                                                    lowx+(ix+1)*.6-.0015, lowy+(iy+1)*1.2-.0015))
                    pieces = [tile] if tile.geom_type == 'Polygon' else getattr(tile, 'geoms', [])
                    for piece in pieces:
                        if piece.geom_type == 'Polygon' and piece.area > 1e-7:
                            prim = _slab(stage, path+f'/Tiles/Tile_{n:03d}', list(piece.exterior.coords), tile_material,
                                         modules, top=.012, depth=.003)
                            prim.RemoveAPI(UsdPhysics.CollisionAPI)  # The continuous room slab is the collider.
                            n += 1
            space.SetCustomDataByKey('tileSizeM', Gf.Vec2d(.6, 1.2))
        if room.get('category') == 'bathroom' or room['id'] == 'powder_room':
            dado = UsdGeom.Xform.Define(stage, path+'/CeramicDado').GetPrim()
            dado.SetCustomDataByKey('heightM', 2.1336)
            dado.SetCustomDataByKey('source', json.dumps(source))
            for i, (a, b) in enumerate(zip(room['polygon'], room['polygon'][1:]+room['polygon'][:1])):
                length = segment_length(a, b)
                if length < .02:
                    continue
                ux, uy = (b[0]-a[0])/length, (b[1]-a[1])/length
                middle = ((a[0]+b[0])/2, (a[1]+b[1])/2)
                inward = 1 if polygon.covers(box(middle[0]-uy*.012-.001, middle[1]+ux*.012-.001,
                                                middle[0]-uy*.012+.001, middle[1]+ux*.012+.001)) else -1
                a = [a[0]-uy*inward*.011, a[1]+ux*inward*.011]
                b = [b[0]-uy*inward*.011, b[1]+ux*inward*.011]
                pieces = LineString([a, b]).difference(opening_cuts)
                segments = [pieces] if pieces.geom_type == 'LineString' else getattr(pieces, 'geoms', [])
                for j, segment in enumerate(segments):
                    if segment.length > .02:
                        p, q = segment.coords[0], segment.coords[-1]
                        _wall_piece(stage, path+'/CeramicDado/Edge_'+str(i), j, p, q, 0, segment.length,
                                    .012, .012+2.1336, .016, materials['dado'], modules)

    bed_parts = [('Frame', (0, 0, .26), (2.14, 1.72, .20), 'cabinet', False),
                 ('Headboard', (-1.03, 0, .51), (.08, 1.72, 1.02), 'cabinet', False),
                 ('Mattress', (.04, 0, .45), (1.98, 1.60, .22), 'linen', False),
                 ('Blanket', (.40, 0, .578), (1.25, 1.62, .032), 'blanket', False)]
    bed_parts += [('Pillow_'+str(i), (-.65, (i-.5)*.79, .64), (.52, .64, .17), 'linen', True) for i in range(2)]
    bed_parts += [('Leg_'+str(i), (x, y, .08), (.08, .08, .16), 'cabinet', False)
                  for i, (x, y) in enumerate([(-.92, -.72), (-.92, .72), (.92, -.72), (.92, .72)])]
    wardrobe = [('Body', (0, 0, 1.05), (1.80, .55, 2.10), 'cabinet', False)]
    wardrobe += [('Door_'+str(i), ((i-.5)*.9, -.275, 1.05), (.885, .025, 2.06), 'door', False) for i in range(2)]
    wardrobe += [('Handle_'+str(i), ((i-.5)*.12, -.29, 1.10), (.016, .02, .20), 'metal', False) for i in range(2)]
    for room in rooms.values():
        if room.get('category') == 'bedroom':
            yaw = 90 if room['id'] in {'bedroom_outer_north', 'bedroom_outer_south'} else 0
            preference = (.63, .36) if yaw else (.38, .52) if room['id'] == 'bedroom_south' else (.38, .58)
            fixture(room, 'Bed', 'bed', (2.14, 1.72, 1.02), preference, bed_parts, yaw)
            fixture(room, 'Wardrobe', 'wardrobe', (1.8, .60, 2.10),
                    (.09, .5) if yaw else (.34, .94) if room['id'] == 'bedroom_south' else (.5, .09), wardrobe, 90 if yaw else 0)
        elif room['id'] == 'walk_in':
            fixture(room, 'Wardrobe', 'wardrobe', (1.8, .60, 2.10), (.1, .5), wardrobe, 90)
        if room.get('category') == 'bathroom' or room['id'] == 'powder_room':
            fixture(room, 'WC', 'wc', (.55, .72, .85), (.83, .5), [
                ('Cistern', (0, .25, .62), (.50, .16, .42), 'porcelain', False),
                ('Pedestal', (0, -.035, .19), (.30, .42, .36), 'porcelain', True),
                ('Bowl', (0, -.035, .37), (.49, .62, .25), 'porcelain', True),
                ('Seat', (0, -.035, .49), (.48, .59, .045), 'porcelain', True),
                ('BowlInset', (0, -.035, .508), (.34, .43, .017), 'matte', True)])
            if room['id'] not in {'service_wc', 'powder_room'}:
                shower = [('Tray', (0, 0, .035), (.82, .82, .07), 'porcelain', False),
                          ('Drain', (0, 0, .074), (.09, .09, .007), 'metal', False),
                          ('ShowerRail', (-.36, .36, 1.40), (.025, .025, 1.05), 'metal', False),
                          ('ShowerHead', (-.24, .36, 1.95), (.25, .18, .028), 'metal', False)]
                if room['id'] in {'bathroom_outer_north', 'bathroom_outer_south'}:
                    shower.append(('GlassPartition', (.40, 0, .95), (.014, .80, 1.90), 'glass', False))
                fixture(room, 'Shower', 'shower', (.82, .82, 1.97), (.2, .83), shower)
            fixture(room, 'Washbasin', 'washbasin', (.52, .42, 1.20), (.2, .18), [
                ('Cabinet', (0, 0, .40), (.5, .40, .78), 'cabinet', False),
                ('Basin', (0, 0, .83), (.52, .42, .12), 'porcelain', True),
                ('BasinInset', (0, -.01, .881), (.38, .29, .017), 'matte', True),
                ('Tap', (.15, .14, .955), (.028, .028, .16), 'metal', False)])

    if 'kitchen' in rooms:
        room = rooms['kitchen']
        cabinets = [('Counter', (0, 0, .875), (.64, 2.40, .05), 'granite', False)]
        cabinets += [('Cabinet_'+str(i), (0, (i-1.5)*.6, .435), (.60, .585, .85), 'cabinet', False) for i in range(4)]
        cabinets += [('Front_'+str(i), (.302, (i-1.5)*.6, .435), (.016, .565, .79), 'door', False) for i in range(4)]
        cabinets += [('Handle_'+str(i), (.313, (i-1.5)*.6, .69), (.014, .22, .018), 'metal', False) for i in range(4)]
        cook = cabinets+[
            ('Hob', (0, -.25, .908), (.48, .58, .025), 'black', False),
            ('Chimney', (0, -.25, 1.88), (.60, .66, .13), 'metal', False),
            ('ChimneyDuct', (-.17, -.25, 2.12), (.20, .22, .38), 'metal', False)]
        cook += [('Burner_'+str(i), (x, y-.25, .928), (.145, .145, .022), 'black', True)
                 for i, (x, y) in enumerate([(-.12, -.15), (-.12, .15), (.12, -.15), (.12, .15)])]
        fixture(room, 'CookingRun', 'kitchen_cabinetry', (.64, 2.40, 2.31), (.06, .67), cook)
        sink = [(name, (-center[0], center[1], center[2]) if name.startswith(('Front_', 'Handle_')) else center,
                 dimensions, material, rounded) for name, center, dimensions, material, rounded in cabinets]+[
            ('Sink', (0, .45, .905), (.49, .59, .055), 'metal', False),
            ('SinkInset', (0, .45, .936), (.37, .45, .018), 'black', False),
            ('Tap', (.20, .45, 1.04), (.025, .025, .27), 'metal', False),
            ('TopUnit', (.08, -.60, 1.98), (.42, 1.10, .68), 'cabinet', False)]
        fixture(room, 'SinkRun', 'kitchen_cabinetry', (.64, 2.40, 2.32), (.94, .56), sink)
        fixture(room, 'Fridge', 'refrigerator', (.72, .70, 1.84), (.08, .09), [
            ('Body', (0, 0, .92), (.66, .70, 1.84), 'porcelain', False),
            ('FreezerDoor', (.338, 0, 1.53), (.016, .69, .57), 'metal', False),
            ('FridgeDoor', (.338, 0, .61), (.016, .69, 1.20), 'metal', False),
            ('Handle', (.351, -.26, .82), (.018, .024, .42), 'metal', False)])
    stage.GetDefaultPrim().SetCustomDataByKey('presentationDecisions', json.dumps(decisions, ensure_ascii=False))
    return decisions


def _interior_scheme(stage, plan, style, materials, modules):
    """Dress the measured home using observed saved-design cues and assumed objects."""
    from shapely.geometry import LineString, Polygon, box
    from shapely.ops import unary_union

    Gf, _, Usd, UsdGeom, UsdLux, _, UsdShade = modules
    scheme = INTERIOR_SCHEMES[style]
    rooms = {room['id']: room for room in plan['rooms']}
    living = rooms['living_dining']
    x0, y0, x1, y1 = bbox([living['polygon']])
    living_x = x1-2.5
    height = float(plan.get('room_height_m') or 2.8)
    base = '/World/Interiors'
    root = UsdGeom.Xform.Define(stage, base).GetPrim()
    root.SetCustomDataByKey('scheme', style)
    root.SetCustomDataByKey('referenceURL', scheme['url'])
    decisions = [{'id': style, 'kind': 'reference-inspired', 'interior_scheme': style,
        'source': {'url': scheme['url'], 'collection': scheme.get('reference_context', 'Instagram Saved / Design'), 'role': 'Aesthetic cues only'},
        'summary': scheme['description']+'. Procedural interpretation, not a measured replica; source flooring and construction retained.',
        'parameters': {'observed_features': scheme.get('observed_features', scheme['features']),
                       'proposed_features': scheme['features'], 'light_temperature_k': scheme['light_kelvin'],
                       'colours_rgb': {key: list(scheme[key]) for key in ('wall', 'wood', 'textile', 'accent', 'rug', 'ink', 'metal')},
                       'lighting_values': 'assumed visualization settings', 'image_authenticity': 'not established'},
        'status': 'needs-review'}]
    for key, spec in {
        'upholstery': (scheme['textile'], .93, 0), 'rug': (scheme['rug'], .98, 0),
        'rug_thread': (tuple(v*.86 for v in scheme['rug']), .99, 0),
        'accent': (scheme['accent'], .94, 0), 'ink': (scheme['ink'], .87, 0),
        'curtain': ((.92, .89, .81), .95, 0), 'leaf': ((.15, .29, .10), .73, 0),
        'leaf_light': ((.28, .40, .16), .81, 0), 'pot': (scheme['accent'], .85, 0),
        'paper': ((.91, .87, .76), .94, 0), 'glow': ((1, .85, .62), .31, 0),
    }.items():
        materials[key] = _make_material(stage, '/World/Looks/Interior/'+key, spec, modules)
    UsdShade.Shader.Get(stage, str(materials['curtain'].GetPath())+'/PBR').CreateInput('opacity', modules[1].ValueTypeNames.Float).Set(.72)
    UsdShade.Shader.Get(stage, str(materials['glow'].GetPath())+'/PBR').CreateInput('emissiveColor', modules[1].ValueTypeNames.Color3f).Set(Gf.Vec3f(1, .73, .37))

    # Expand only the scene's material-bearing instances. Vendor files and mesh
    # transforms stay untouched; source units/physical dimensions are retained.
    assets = stage.GetPrimAtPath('/World/Assets')
    if assets:
        for prim in Usd.PrimRange(assets):
            if prim.IsInstance():
                prim.SetInstanceable(False)
        for prim in Usd.PrimRange(assets):
            if not prim.IsA(UsdGeom.Mesh):
                continue
            material, _ = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
            if material and 'leather' in material.GetPrim().GetName():
                _bind(prim, materials['upholstery'], modules)
            elif 'cabinet_b01' in str(prim.GetPath()) and material:
                _bind(prim, materials['cabinet'], modules)

    door_shapes = [LineString([o['start'], o['end']]).buffer(.55, cap_style=2) for o in plan['openings']]
    transforms = UsdGeom.XformCache()
    for opening in plan['openings']:
        leaf = stage.GetPrimAtPath('/World/Building/Openings/'+safe_name(opening['id'])+'/Leaf')
        if leaf:
            transform = transforms.GetLocalToWorldTransform(leaf)
            corners = [transform.Transform(Gf.Vec3d(x*.5, y*.5, 0)) for x, y in [(-1,-1),(1,-1),(1,1),(-1,1)]]
            door_shapes.append(Polygon([(p[0], p[1]) for p in corners]))
    doors = unary_union(door_shapes)

    def part(parent, name, center, size, material, shape='Cube', rotate=(0, 0, 0)):
        path = str(parent.GetPath())+'/'+safe_name(name)
        if shape == 'Cube':
            return _box(stage, path, center, size, rotate[2], materials[material], modules, collision=False)
        primitive = getattr(UsdGeom, shape).Define(stage, path)
        primitive.CreateRadiusAttr(1)
        if shape != 'Sphere':
            primitive.CreateHeightAttr(2)
            primitive.CreateAxisAttr('Z')
        xf = UsdGeom.Xformable(primitive.GetPrim())
        xf.AddTranslateOp().Set(Gf.Vec3d(*center))
        xf.AddRotateXYZOp().Set(Gf.Vec3f(*rotate))
        xf.AddScaleOp().Set(Gf.Vec3f(*(v/2 for v in size)))
        _bind(primitive.GetPrim(), materials[material], modules)
        return primitive.GetPrim()

    def assembly(name, kind, position, room='living_dining', role='surface'):
        prim = UsdGeom.Xform.Define(stage, base+'/'+name).GetPrim()
        UsdGeom.Xformable(prim).AddTranslateOp().Set(Gf.Vec3d(*position))
        for key, value in {'interiorDecor': True, 'decorType': kind, 'roomId': room,
                           'clearanceRole': role, 'provenance': 'Reference-inspired; exact dimensions, form, colour and placement assumed'}.items():
            prim.SetCustomDataByKey(key, value)
        return prim

    def finish(prim):
        bound = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render']).ComputeWorldBound(prim).ComputeAlignedBox()
        low, high = bound.GetMin(), bound.GetMax()
        footprint = box(low[0], low[1], high[0], high[1])
        role = prim.GetCustomDataByKey('clearanceRole')
        valid = role != 'floor' or (Polygon(rooms[prim.GetCustomDataByKey('roomId')]['polygon']).buffer(1e-7).covers(footprint)
                                  and footprint.intersection(doors).area < 1e-8)
        decisions.append({'id': str(prim.GetPath()), 'kind': 'assumed', 'interior_scheme': style,
            'source': {'url': scheme['url'], 'role': 'Decor cues; no measured item dimensions'},
            'summary': prim.GetCustomDataByKey('provenance'), 'status': 'needs-review' if valid else 'not-placed',
            'parameters': {'room_id': prim.GetCustomDataByKey('roomId'), 'decor_type': prim.GetCustomDataByKey('decorType'),
                           'size_xyz_m': [float(v) for v in bound.GetSize()],
                           'bounds_min_m': [float(v) for v in low], 'bounds_max_m': [float(v) for v in high],
                           'clearance_role': role}})
        if not valid:
            stage.RemovePrim(prim.GetPath())

    def light(parent, name, center, intensity=160):
        lamp = UsdLux.SphereLight.Define(stage, str(parent.GetPath())+'/'+name)
        lamp.CreateRadiusAttr(.045)
        lamp.CreateIntensityAttr(intensity)
        lamp.CreateEnableColorTemperatureAttr(True)
        lamp.CreateColorTemperatureAttr(float(scheme['light_kelvin']))
        UsdGeom.Xformable(lamp.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(*center))

    # Actual woven/graphic surface geometry, with a six-millimetre rug skin.
    rug = assembly('LivingRug', 'rug', (living_x, y0+1.95, .015), role='floor')
    part(rug, 'Backing', (0, 0, 0), (3.6, 2.8, .006), 'rug')
    for i in range(37):
        part(rug, 'Weft_'+str(i), ((i-18)*.095, 0, .0038), (.003, 2.76, .0015), 'rug_thread')
    for i in range(29):
        part(rug, 'Warp_'+str(i), (0, (i-14)*.096, .0039), (3.56, .003, .0015), 'rug_thread')
    for i in range(30):
        for sign in (-1, 1):
            part(rug, 'Fringe_'+str(i)+'_'+str(sign), ((i-14.5)*.116, sign*1.425, .001), (.009, .07, .003), 'rug_thread')
    if style != 'saved_linen_timber':
        for i in range(9):
            part(rug, 'Graphic_'+str(i), ((i-4)*.37, -1.20, .0048), (.15, .08, .001), 'ink' if i%2 else 'accent')
    if style in {'indian_contemporary', 'bohemian'}:
        for sign in (-1, 1):
            for i in range(11):
                part(rug, 'Diamond_'+str(sign)+'_'+str(i), ((i-5)*.29, sign*1.04, .006),
                     (.095, .095, .002), 'ink' if i%2 else 'accent', rotate=(0, 0, 45))
    if style == 'bohemian':
        part(rug, 'LayeredRunner', (0, 0, .009), (2.7, 1.55, .008), 'accent')
        for i in range(17):
            part(rug, 'RunnerStripe_'+str(i), ((i-8)*.15, 0, .014), (.045, 1.49, .002), 'ink' if i%3 else 'paper')
    finish(rug)

    # Gathered panels sit outside each source slider's access span.
    for opening in plan['openings']:
        if opening['type'] != 'sliding_door':
            continue
        a, b = opening['start'], opening['end']
        length = segment_length(a, b)
        ux, uy = (b[0]-a[0])/length, (b[1]-a[1])/length
        room_id = opening['space_id']
        centroid = Polygon(rooms[room_id]['polygon']).centroid
        sign = 1 if -uy*(centroid.x-a[0])+ux*(centroid.y-a[1]) >= 0 else -1
        nx, ny = -uy*sign, ux*sign
        curtains = assembly('Curtains_'+opening['id'], 'curtains', (0,0,0), room_id, 'wall')
        for panel, endpoint, offset in [(0, a, -.20), (1, b, .20)]:
            points = []
            for z in (.025, height-.16):
                for i in range(25):
                    along = offset+(i/24-.5)*.24
                    fold = .17+math.sin(i*math.pi/2)*.035
                    points.append(Gf.Vec3f(endpoint[0]+ux*along+nx*fold, endpoint[1]+uy*along+ny*fold, z))
            mesh = UsdGeom.Mesh.Define(stage, str(curtains.GetPath())+'/Pleats_'+str(panel))
            mesh.CreatePointsAttr(points)
            mesh.CreateFaceVertexCountsAttr([4]*24)
            mesh.CreateFaceVertexIndicesAttr([j for i in range(24) for j in (i,i+1,i+26,i+25)])
            mesh.CreateSubdivisionSchemeAttr('none')
            mesh.CreateDoubleSidedAttr(True)
            _bind(mesh.GetPrim(), materials['curtain'], modules)
        finish(curtains)

    art = assembly('GraphicPosters' if style == 'saved_evening_lounge' else 'BotanicalGallery' if style == 'saved_botanical_cane' else 'TimberGallery', 'art', (living_x, y1-.045, 1.80), role='wall')
    for i in range(2 if style == 'saved_evening_lounge' else 3):
        x = (i-.5)*.80 if style == 'saved_evening_lounge' else (i-1)*.57
        width, tall = (.65, .90) if style == 'saved_evening_lounge' else (.48, .66)
        part(art, 'Frame_'+str(i), (x,0,0), (width,.032,tall), 'ink' if style == 'saved_evening_lounge' else 'cabinet')
        part(art, 'Paper_'+str(i), (x,-.020,0), (width-.045,.008,tall-.045), 'paper')
        for j in range(3):
            part(art, 'Motif_'+str(i)+'_'+str(j), (x+(j-1)*.09,-.026,(j-1)*.12), (.20,.005,.12 if style == 'saved_evening_lounge' else .22), 'ink' if j%2 else 'accent', 'Sphere', (0,0,j*28))
    finish(art)

    if style == 'bohemian':
        textile = assembly('KnottedWallHanging', 'woven_wall_hanging', (living_x-1.40, y1-.07, 1.82), role='wall')
        part(textile, 'TimberRod', (0, 0, .36), (.62, .025, .025), 'cabinet')
        for i in range(19):
            length = .40+.22*(1-abs(i-9)/9)
            part(textile, 'Cord_'+str(i), ((i-9)*.027, -.016, .34-length/2), (.008, .008, length), 'paper')
            for j in range(3):
                part(textile, 'Knot_'+str(i)+'_'+str(j), ((i-9)*.027, -.021, .25-j*.09), (.017, .015, .02), 'paper', 'Sphere')
        finish(textile)

    console = assembly('TimberMediaConsole', 'media_console', (living_x,y0+.26,0), role='floor')
    part(console, 'Body', (0,0,.32), (1.60,.40,.40), 'cabinet')
    for i in range(3):
        part(console, 'Front_'+str(i), ((i-1)*.52,.207,.32), (.50,.016,.36), 'door')
    if style == 'indian_contemporary':
        for i in range(25):
            part(console, 'LatticeVertical_'+str(i), ((i-12)*.06,.220,.32), (.012,.012,.32), 'cabinet')
        for i in range(6):
            part(console, 'LatticeHorizontal_'+str(i), (0,.227,.17+i*.06), (1.48,.012,.012), 'metal')
    for i, (x,y) in enumerate([(-.65,-.13),(-.65,.13),(.65,-.13),(.65,.13)]):
        part(console, 'Leg_'+str(i), (x,y,.06), (.04,.04,.12), 'cabinet')
    part(console, 'Screen', (0,-.07,.98), (1.05,.035,.59), 'black')
    part(console, 'ScreenStand', (0,-.07,.58), (.20,.10,.12), 'metal')
    finish(console)

    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default','render'])
    sofa = stage.GetPrimAtPath('/World/Assets/living_sofa')
    if sofa:
        bounds = cache.ComputeWorldBound(sofa).ComputeAlignedBox()
        low, high = bounds.GetMin(), bounds.GetMax()
        cushions = assembly('TerracottaCushions' if style == 'saved_botanical_cane' else 'LoungeCushions', 'cushions', (0,0,0))
        for i in range(3):
            colour = 'ink' if style in {'indian_contemporary', 'bohemian'} and i == 1 else 'accent' if i != 1 else 'upholstery'
            part(cushions, 'Pillow_'+str(i), ((low[0]+high[0])/2+(i-1)*.70, high[1]-.30, .63), (.42,.14,.36), colour, 'Sphere', (-12,0,0))
        finish(cushions)
    table = stage.GetPrimAtPath('/World/Assets/living_table')
    if table:
        bounds = cache.ComputeWorldBound(table).ComputeAlignedBox()
        mid = bounds.GetMidpoint()
        books = assembly('CoffeeTableBooks', 'book_accents', (mid[0],mid[1],bounds.GetMax()[2]+.003))
        for i in range(3):
            part(books, 'Pages_'+str(i), (0,0,i*.025+.011), (.24,.18,.019), 'paper')
            part(books, 'Cover_'+str(i), (0,0,i*.025+.022), (.25,.19,.003), 'accent' if i%2 else 'ink')
        part(books, 'Vase', (.37,0,.10), (.13,.13,.20), 'pot', 'Sphere')
        finish(books)
    cabinet = stage.GetPrimAtPath('/World/Assets/den_cabinet')
    if cabinet:
        bounds = cache.ComputeWorldBound(cabinet).ComputeAlignedBox()
        mid = bounds.GetMidpoint()
        books = assembly('TimberDisplayBooks', 'book_accents', (mid[0],mid[1],.008), 'wfh', 'furniture-overlay')
        for shelf in range(4):
            for i in range(5):
                part(books, 'Book_'+str(shelf)+'_'+str(i), (.025,(i-2)*.045,shelf*.39+.23), (.22,.039,.24+(i%2)*.025), 'ink' if i%3==0 else 'accent' if i%3==1 else 'paper')
        finish(books)

    def plant(name, x, y, room='living_dining'):
        parent = assembly(name, 'plant', (x,y,.014), room, 'floor')
        part(parent, 'Pot', (0,0,.19), (.30,.30,.38), 'pot', 'Cone')
        part(parent, 'Stem', (0,0,.65), (.025,.025,.95), 'cabinet', 'Cylinder')
        for i in range(9):
            angle = i*2.4
            part(parent, 'Leaf_'+str(i), (.16*math.cos(angle),.16*math.sin(angle),.56+i*.075), (.31,.14,.032), 'leaf' if i%2 else 'leaf_light', 'Sphere', (18, -18, math.degrees(angle)))
        finish(parent)
    plant('CornerPlant', living_x+1.73, y1-.40)
    if style != 'saved_evening_lounge':
        plant('TimberSidePlant', living_x-1.73, y1-.95)
    if style == 'saved_botanical_cane':
        dx0,dy0,dx1,dy1 = bbox([rooms['wfh']['polygon']])
        plant('DenGreenery', dx1-1.05, dy0+.48, 'wfh')
        for prim in list(stage.Traverse()):
            if prim.GetCustomDataByKey('fixtureType') not in {'bed','wardrobe'}:
                continue
            panel = UsdGeom.Xform.Define(stage, str(prim.GetPath())+'/CaneWeave').GetPrim()
            panel.SetCustomDataByKey('provenance', 'Cane visual detail inspired by saved reference; material, weave and dimensions assumed')
            if prim.GetCustomDataByKey('fixtureType') == 'bed':
                for i in range(21):
                    part(panel, 'Vertical_'+str(i), (-.978,(i-10)*.07,.55), (.006,.007,.70), 'accent')
                for i in range(11):
                    part(panel, 'Horizontal_'+str(i), (-.974,0,.20+i*.07), (.006,1.47,.007), 'cabinet')
            else:
                for i in range(23):
                    part(panel, 'Vertical_'+str(i), ((i-11)*.07,-.289,1.05), (.007,.005,1.74), 'accent')
                for i in range(25):
                    part(panel, 'Horizontal_'+str(i), (0,-.292,.21+i*.07), (1.60,.005,.007), 'cabinet')

    if style == 'saved_evening_lounge':
        lamp = assembly('OpalFloorGlobe', 'lamp', (living_x-1.73,y1-.95,.014), role='floor')
        part(lamp, 'Base', (0,0,.025), (.34,.34,.05), 'metal', 'Cylinder')
        part(lamp, 'Stem', (0,0,.69), (.026,.026,1.30), 'metal', 'Cylinder')
        part(lamp, 'OpalGlobe', (0,0,1.48), (.40,.40,.36), 'glow', 'Sphere')
        light(lamp, 'PracticalLight', (0,0,1.48), 420)
        finish(lamp)
        lamp = assembly('MushroomSideLamp', 'lamp', (living_x+1.50,y1-.90,.014), role='floor')
        part(lamp, 'TimberSideTable', (0,0,.25), (.38,.40,.50), 'cabinet')
        part(lamp, 'Stem', (0,0,.62), (.055,.055,.23), 'porcelain', 'Cylinder')
        part(lamp, 'OpalDome', (0,0,.77), (.32,.32,.18), 'glow', 'Sphere')
        light(lamp, 'PracticalLight', (0,0,.73), 220)
        finish(lamp)
        lamp = assembly('AmberConsoleLamp', 'lamp', (living_x+.56,y0+.28,.53))
        part(lamp, 'Base', (0,0,.035), (.14,.14,.07), 'metal', 'Cylinder')
        part(lamp, 'AmberShade', (0,0,.20), (.24,.24,.27), 'glow', 'Sphere')
        light(lamp, 'PracticalLight', (0,0,.20), 160)
        finish(lamp)
    else:
        dining = stage.GetPrimAtPath('/World/Assets/dining_table')
        center = cache.ComputeWorldBound(dining).ComputeAlignedBox().GetMidpoint() if dining else Gf.Vec3d(x0+2.38,(y0+y1)/2,0)
        for i in range(2):
            woven = style in {'saved_botanical_cane', 'bohemian'}
            lamp = assembly(('WovenPendant_' if woven else 'ConePendant_')+str(i), 'lamp', (center[0]+(i-.5)*.68,center[1],0), role='overhead')
            part(lamp, 'Suspension', (0,0,height-.25), (.012,.012,.48), 'metal', 'Cylinder')
            if woven:
                for j in range(24):
                    angle = j*math.tau/24
                    part(lamp, 'WovenRib_'+str(j), (.23*math.cos(angle),.23*math.sin(angle),height-.60), (.018,.018,.27), 'cabinet')
                part(lamp, 'ShadeTop', (0,0,height-.45), (.49,.49,.025), 'cabinet', 'Cylinder')
            else:
                part(lamp, 'ConeShade', (0,0,height-.60), (.46,.46,.30), 'metal' if style == 'indian_contemporary' else 'accent', 'Cone')
            part(lamp, 'Bulb', (0,0,height-.73), (.10,.10,.085), 'glow', 'Sphere')
            light(lamp, 'PracticalLight', (0,0,height-.73), 210)
            finish(lamp)

    # Faces point down; the streaming viewer hides them for cutaway views.
    ceiling_lights = []
    for room in rooms.values():
        if room.get('category') == 'balcony':
            continue
        mesh = UsdGeom.Mesh.Define(stage, base+'/Ceilings/'+safe_name(room['id']))
        mesh.CreatePointsAttr([Gf.Vec3f(x,y,height) for x,y in room['polygon']])
        faces = triangulate(room['polygon'])
        mesh.CreateFaceVertexCountsAttr([3]*len(faces))
        mesh.CreateFaceVertexIndicesAttr([index for face in faces for index in reversed(face)])
        mesh.CreateDoubleSidedAttr(False)
        mesh.CreateSubdivisionSchemeAttr('none')
        _bind(mesh.GetPrim(), materials['wall'], modules)
        mesh.GetPrim().SetCustomDataByKey('provenance', 'Assumed visualization ceiling at plan height; downward single-sided faces for cutaway top view')
        center = Polygon(room['polygon']).representative_point()
        centers = [(center.x, center.y)]
        if room['id'] == 'living_dining':
            centers.append((living_x, y0+1.95))
        for index, (x, y) in enumerate(centers):
            lamp = UsdLux.RectLight.Define(stage, base+'/CeilingLights/'+safe_name(room['id'])+'_'+str(index))
            lamp.CreateWidthAttr(.6)
            lamp.CreateHeightAttr(.6)
            lamp.CreateIntensityAttr(3500 if style == 'saved_evening_lounge' else 5000)
            lamp.CreateEnableColorTemperatureAttr(True)
            lamp.CreateColorTemperatureAttr(float(scheme['light_kelvin']))
            UsdGeom.Xformable(lamp.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(x, y, height-.03))
            ceiling_lights.append({'room_id': room['id'], 'position_m': [x, y, height-.03],
                                   'size_m': [.6, .6], 'intensity': lamp.GetIntensityAttr().Get(),
                                   'temperature_k': scheme['light_kelvin']})
    footprint = plan.get('footprint', {})
    if footprint.get('polygon'):
        circulation = Polygon(footprint['polygon'], footprint.get('holes', [])).difference(
            unary_union([Polygon(room['polygon']) for room in rooms.values()]))
        for index, polygon in enumerate(getattr(circulation, 'geoms', [circulation])):
            if polygon.area < .02:
                continue
            infill = _slab(stage, base+'/Ceilings/Circulation_'+str(index), list(polygon.exterior.coords),
                           materials['wall'], modules, top=height+.03, depth=.03,
                           holes=[list(ring.coords)[:-1] for ring in polygon.interiors])
            infill.RemoveAPI(modules[5].CollisionAPI)
    decisions.append({'id': style+'_ceiling', 'kind': 'assumed', 'interior_scheme': style,
        'summary': 'Add a downward single-sided visualization ceiling; height remains unverified by a section.',
        'parameters': {'height_m': height, 'single_sided': True,
                       'lights': ceiling_lights,
                       'circulation_infill': 'Assumed ceiling over the remaining footprint, excluding all room and balcony polygons; follows the provisional footprint',
                       'ceiling_lights': 'Assumed 0.6 m square lights per room, with separate living and dining lights; positions and intensities are visualization choices'}, 'status': 'needs-review'})
    return decisions


def _generic_interior_scheme(stage, plan, style, materials, modules):
    """Propose fixed-size decor inside reviewed polygons; omit anything that cannot fit."""
    from shapely.geometry import LineString, Polygon, box
    from shapely.ops import unary_union

    Gf, _, Usd, UsdGeom, UsdLux, _, _ = modules
    scheme = INTERIOR_SCHEMES[style]
    base = '/World/Interiors'
    root = UsdGeom.Xform.Define(stage, base).GetPrim()
    root.SetCustomDataByKey('scheme', style)
    root.SetCustomDataByKey('referenceURL', scheme['url'])
    height = float(plan.get('room_height_m') or 2.9)
    basis = ('Assumed fixed-size decor, positioned from reviewed room polygons with boundary, '
             'opening, wall and existing asset clearance; limited candidate search, not a circulation audit')
    decisions = [{'id': style, 'kind': 'reference-inspired', 'interior_scheme': style,
                  'source': {'url': scheme['url'], 'role': 'Aesthetic cues only'},
                  'summary': scheme['generic_description']+'. Procedural suggestions, not automatic reconstruction.',
                  'parameters': {'placement_basis': basis, 'proposed_features': scheme['generic_features'],
                                 'light_temperature_k': scheme['light_kelvin'],
                                 'colours_rgb': {key: list(scheme[key]) for key in ('wall', 'wood', 'textile', 'accent', 'rug', 'ink', 'metal')}},
                  'status': 'needs-review'}]
    for key in ('wood', 'textile', 'accent', 'rug', 'ink', 'metal'):
        materials['decor_'+key] = _make_material(stage, '/World/Looks/Interior/'+key,
                                               (scheme[key], .85, .65 if key == 'metal' else 0), modules)
    materials['decor_leaf'] = _make_material(stage, '/World/Looks/Interior/leaf', ((.18, .32, .12), .85, 0), modules)
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render', 'proxy'])
    blocked = []
    # Actual opening assembly bounds include the illustrated open door leaves.
    for path in ('/World/Assets', '/World/Building/Openings'):
        group = stage.GetPrimAtPath(path)
        for prim in group.GetChildren() if group else []:
            bounds = cache.ComputeWorldBound(prim).ComputeAlignedBox()
            if not bounds.IsEmpty():
                low, high = bounds.GetMin(), bounds.GetMax()
                blocked.append(box(low[0], low[1], high[0], high[1]).buffer(.15 if path.endswith('Assets') else .6))
    for opening in plan.get('openings', []):
        if opening.get('start') is not None and opening.get('end') is not None:
            blocked.append(LineString([opening['start'], opening['end']]).buffer(.65))
    for wall in plan.get('wall_segments', []):
        blocked.append(LineString([wall['start'], wall['end']]).buffer(float(wall.get('thickness_m') or .18)/2+.1))
    footprint = plan.get('footprint', {})
    outline = Polygon(footprint['polygon'], footprint.get('holes', [])) if footprint.get('polygon') else None
    for hole in footprint.get('holes', []):
        blocked.append(Polygon(hole).buffer(.1))
    occupied = unary_union(blocked)

    def part(parent, name, center, size, material, shape='Cube', yaw=0):
        path = str(parent.GetPath())+'/'+name
        if shape == 'Cube':
            return _box(stage, path, center, size, yaw, materials['decor_'+material], modules, collision=False)
        mesh = getattr(UsdGeom, shape).Define(stage, path)
        mesh.CreateRadiusAttr(1)
        if shape != 'Sphere':
            mesh.CreateHeightAttr(2)
            mesh.CreateAxisAttr('Z')
        xf = UsdGeom.Xformable(mesh.GetPrim())
        xf.AddTranslateOp().Set(Gf.Vec3d(*center))
        xf.AddScaleOp().Set(Gf.Vec3f(*(v/2 for v in size)))
        _bind(mesh.GetPrim(), materials['decor_'+material], modules)

    for index, room in enumerate(plan.get('rooms', [])):
        room_id = str(room.get('id', f'room_{index}'))
        room_shape = Polygon(room['polygon'])
        safe = room_shape.buffer(-.2)
        if outline is not None:
            safe = safe.intersection(outline.buffer(-.1))
        category = str(room.get('category', 'room')).lower()
        if category in {'bathroom', 'kitchen', 'service', 'balcony', 'corridor', 'hallway', 'stairs', 'toilet'}:
            decisions.append({'id': room_id, 'kind': 'assumed', 'interior_scheme': style,
                              'summary': 'Decor omitted for a wet, service, outdoor or circulation room.',
                              'parameters': {'room_id': room_id, 'category': category}, 'status': 'not-placed'})
            continue
        x0, y0, x1, y1 = room_shape.bounds
        center = room_shape.representative_point()
        # ponytail: bounded candidate grid can miss a valid fit; skip rather than resize props.
        candidates = [(center.x, center.y)]+[(x0+(x1-x0)*x/10, y0+(y1-y0)*y/10)
                                             for x in range(1, 10) for y in range(1, 10)]
        for kind, width, depth, tall in [('rug', 1.6, 1.1, .05), ('plant', .55, .55, 1.0), ('lamp', .45, .45, 1.7)]:
            path = base+'/'+safe_name(room_id)+'_'+str(index)+'/'+kind
            position = next(((x, y) for x, y in candidates
                             if tall+.02 <= height and safe.covers(box(x-width/2, y-depth/2, x+width/2, y+depth/2))
                             and not occupied.intersects(box(x-width/2, y-depth/2, x+width/2, y+depth/2))), None)
            decision = {'id': path, 'kind': 'assumed', 'interior_scheme': style,
                        'source': {'url': scheme['url'], 'role': 'Decor cues; dimensions and placement assumed'},
                        'summary': basis, 'status': 'needs-review' if position else 'not-placed',
                        'parameters': {'room_id': room_id, 'decor_type': kind, 'placement_basis': basis,
                                       'size_xyz_m': [width, depth, tall], 'category': category}}
            decisions.append(decision)
            if position is None:
                decision['summary'] = 'No safe candidate found; omitted without resizing furniture or changing the plan.'
                continue
            x, y = position
            prim = UsdGeom.Xform.Define(stage, path).GetPrim()
            UsdGeom.Xformable(prim).AddTranslateOp().Set(Gf.Vec3d(x, y, .02))
            for key, value in {'interiorDecor': True, 'decorType': kind, 'roomId': room_id,
                               'clearanceRole': 'floor', 'provenance': basis}.items():
                prim.SetCustomDataByKey(key, value)
            if kind == 'rug':
                part(prim, 'Backing', (0, 0, .004), (1.6, 1.1, .008), 'rug')
                if style == 'bohemian':
                    part(prim, 'LayeredRunner', (0, 0, .013), (1.3, .7, .008), 'accent')
                for i in range(9):
                    if style == 'indian_contemporary':
                        part(prim, 'Diamond_'+str(i), ((i-4)*.16, .40, .010), (.08, .08, .003), 'ink', yaw=45)
                    else:
                        part(prim, ('Woven_' if style in {'saved_linen_timber', 'saved_botanical_cane'} else 'Stripe_')+str(i),
                             ((i-4)*.16, 0, .019), (.008 if style == 'saved_linen_timber' else .035, .65, .003),
                             'textile' if style == 'saved_linen_timber' else 'ink')
            elif kind == 'plant':
                part(prim, 'ClayPot', (0, 0, .16), (.30, .30, .32), 'accent', 'Cone')
                part(prim, 'Stem', (0, 0, .55), (.024, .024, .70), 'wood', 'Cylinder')
                for i in range(6):
                    angle = i*2.4
                    part(prim, 'Leaf_'+str(i), (.13*math.cos(angle), .13*math.sin(angle), .48+i*.075), (.25, .25, .09), 'leaf', 'Sphere')
            else:
                part(prim, 'Base', (0, 0, .025), (.35, .35, .05), 'metal', 'Cylinder')
                part(prim, 'Stem', (0, 0, .72), (.025, .025, 1.4), 'wood' if style == 'bohemian' else 'metal', 'Cylinder')
                if style in {'saved_botanical_cane', 'bohemian'}:
                    for i in range(18):
                        angle = i*math.tau/18
                        part(prim, 'WovenRib_'+str(i), (.19*math.cos(angle), .19*math.sin(angle), 1.45), (.016, .016, .32), 'wood')
                else:
                    part(prim, 'Globe' if style == 'saved_evening_lounge' else 'Shade', (0, 0, 1.45), (.4, .4, .32),
                         'metal' if style == 'indian_contemporary' else 'textile', 'Sphere' if style == 'saved_evening_lounge' else 'Cone')
                lamp = UsdLux.SphereLight.Define(stage, path+'/PracticalLight')
                lamp.CreateRadiusAttr(.04)
                lamp.CreateIntensityAttr(160)
                lamp.CreateEnableColorTemperatureAttr(True)
                lamp.CreateColorTemperatureAttr(float(scheme['light_kelvin']))
                UsdGeom.Xformable(lamp.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(0, 0, 1.4))
            bounds = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render']).ComputeWorldBound(prim).ComputeAlignedBox()
            decision['parameters'].update(bounds_min_m=list(bounds.GetMin()), bounds_max_m=list(bounds.GetMax()))
            occupied = occupied.union(box(x-width/2, y-depth/2, x+width/2, y+depth/2).buffer(.1))
    if not plan.get('rooms'):
        decisions.append({'id': style+'_placement', 'kind': 'assumed', 'interior_scheme': style,
                          'summary': 'No room polygons supplied; scheme finishes applied and decor omitted.', 'status': 'not-placed'})
    return decisions


def build_usd(plan: dict, output_path: str | Path, style: str = "contemporary") -> dict:
    """Build one style; return paths and measured/declared area notes."""
    if style not in PALETTES:
        raise ValueError(f"Unknown style: {style}")
    if style == 'home_specification' and plan.get('source', {}).get('primary_crop') != 'agreement_unit_crop.jpg':
        raise ValueError('B1-1502 specified finishes require the demarcated agreement reference')
    errors = validate_plan(plan)
    if errors:
        raise ValueError("; ".join(errors))
    if style in INTERIOR_SCHEMES and plan.get('source', {}).get('primary_crop') == 'agreement_unit_crop.jpg':
        room_ids = {room['id'] for room in plan.get('rooms', [])}
        required = {'living_dining'} | ({'wfh'} if style == 'saved_botanical_cane' else set())
        required.update(opening.get('space_id') for opening in plan.get('openings', [])
                        if opening.get('type') == 'sliding_door')
        if required - room_ids:
            raise ValueError('This interior scheme references rooms removed from the layout. Restore those rooms or choose a finish preset.')
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
    world.GetPrim().SetCustomDataByKey('referenceManifest', json.dumps(plan.get('reference_manifest', {}), ensure_ascii=False))
    world.GetPrim().SetCustomDataByKey("heightStatus", str(plan.get("height_status", "user provided or assumed")))
    world.GetPrim().SetCustomDataByKey("style", style)
    world.GetPrim().SetCustomDataByKey('planFingerprint', hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(',', ':')).encode()).hexdigest())
    world.GetPrim().SetCustomDataByKey('isDesignScheme', bool(PALETTES[style].get('is_design_scheme')))
    world.GetPrim().SetCustomDataByKey('traceCalibration', json.dumps(plan.get('calibration', {})))
    world.GetPrim().SetCustomDataByKey('wallTrace', json.dumps(plan.get('source_wall_segments', plan.get('wall_segments', []))))
    if plan.get("area_schedule_m2"):
        world.GetPrim().SetCustomDataByKey("areaScheduleM2", json.dumps(plan["area_schedule_m2"]))
    world.GetPrim().SetCustomDataByKey('dimensionModel', plan.get('dimension_model', 'raster'))
    world.GetPrim().SetCustomDataByKey('dimensionNote', plan.get('dimension_note', 'Raster trace in meters; dimensions not constrained'))
    world.GetPrim().SetCustomDataByKey('reconstructionDecisions', json.dumps(plan.get('reconstruction_decisions', []), ensure_ascii=False))
    world.GetPrim().SetCustomDataByKey('scaleAudit', json.dumps(measured_scale_audit(plan), ensure_ascii=False))
    world.GetPrim().SetCustomDataByKey('openingTrace', json.dumps(plan.get('openings', []), ensure_ascii=False))
    world.GetPrim().SetCustomDataByKey('presentationNote', 'Finish colours, furniture layout, door assembly and 75-degree open swing are illustrative assumptions; printed room dimensions remain source constraints')
    style_specs = PALETTES[style]
    home_details = style == 'home_specification' or (plan.get('source', {}).get('primary_crop') == 'agreement_unit_crop.jpg' and style_specs['category'] == 'home')
    materials = {key: _make_material(stage, f"/World/Looks/{safe_name(key)}", spec, modules) for key, spec in style_specs.items() if isinstance(spec, tuple)}
    if not home_details and style in {'contemporary', 'classic', 'home_luxury', 'warm_office', 'executive_office'}:
        _wood_floor_texture(stage, materials['floor'], output_path, modules)
    materials['tile'] = _make_material(stage, '/World/Looks/tile', ((.65, .63, .58), .45, 0), modules)
    if home_details:
        for key, spec in {
            'specified_wood': ((.40, .26, .15), .52, 0), 'matte': ((.58, .56, .51), .88, 0),
            'dado': ((.81, .80, .75), .25, 0), 'granite': ((.16, .17, .17), .24, 0),
            'porcelain': ((.94, .94, .92), .19, 0), 'cabinet': ((.48, .36, .25), .58, 0),
            'linen': ((.94, .91, .84), .92, 0), 'blanket': ((.22, .36, .38), .95, 0),
            'black': ((.035, .038, .04), .31, 0), 'laminated_door': ((.62, .54, .43), .51, 0),
        }.items():
            materials[key] = _make_material(stage, '/World/Looks/'+key, spec, modules)
        _wood_floor_texture(stage, materials['specified_wood'], output_path, modules)
        if style in INTERIOR_SCHEMES:
            scheme = INTERIOR_SCHEMES[style]
            for key, colour in {'cabinet': scheme['wood'], 'linen': scheme['textile'], 'blanket': scheme['accent']}.items():
                materials[key] = _make_material(stage, '/World/Looks/'+key, (colour, .91 if key != 'cabinet' else .57, 0), modules)
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
        if room.get('dimension_mode') or home_details:
            category = room.get('category')
            if home_details:
                finish = materials['specified_wood'] if room.get('id') == 'bedroom_outer_south' else materials['matte'] if category in {'bathroom', 'balcony'} or room.get('id') == 'powder_room' else materials['floor']
            else:
                finish = materials['balcony'] if category == 'balcony' else materials['tile'] if category in {'bathroom','kitchen','service'} else materials['floor']
            _slab(stage, str(room_prim.GetPath()) + '/Floor', room['polygon'], finish, modules, top=.008, depth=.008)

        room_prim.SetCustomDataByKey("printedDimensionsM", json.dumps(room.get("printed_dimensions_m", room.get("dimensions_m", []))))
        if 'source_evidence' in room:
            room_prim.SetCustomDataByKey('sourceEvidence', json.dumps(room['source_evidence'], ensure_ascii=False))
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
            if home_details:
                wall_prim.SetCustomDataByKey('assemblyNote', 'Glass railing specified in Annexure F; height, profiles and post spacing assumed')
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
            elif kind == 'opening':
                if not opening.get('no_header'):
                    head = min(wall_height - 0.1, float(opening.get('height_m', 2.1)))
                    _wall_piece(stage, base, piece, a, b, start, end, head, wall_height, thickness, wall_material, modules)
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

    # Dimension-driven walls are already cut around these openings.
    for i, opening in enumerate(plan.get('openings', [])):
        if not opening.get('free_opening') or not opening.get('start') or not opening.get('end'):
            continue
        a, b = opening['start'], opening['end']
        length = segment_length(a, b)
        if length < .1:
            continue
        base = f'/World/Building/Openings/{safe_name(opening.get("id", str(i)))}'
        opening_prim = UsdGeom.Xform.Define(stage, base).GetPrim()
        head = min(height-.1, float(opening.get('height_m', 2.2)))
        kind = str(opening.get('type', 'opening'))
        opening_room = next((r for r in rooms if r.get('id') == opening.get('space_id')), {})
        door_material = materials['laminated_door'] if home_details and (opening_room.get('category') == 'bathroom' or opening_room.get('id') == 'powder_room') else materials['door']
        for key, value in {'widthM': length, 'heightM': height if opening.get('no_header') else head,
                           'type': kind, 'label': str(opening.get('label', opening.get('id', i))),
                           'provenance': json.dumps(opening.get('provenance', {}), ensure_ascii=False),
                           'connects': json.dumps(opening.get('connects', []))}.items():
            opening_prim.SetCustomDataByKey(key, value)
        opening_prim.SetCustomDataByKey('assemblyNote', 'Illustrative jambs, frame and lintel; assembly dimensions and finishes assumed')
        if home_details and kind == 'door':
            laminated = opening_room.get('category') == 'bathroom' or opening_room.get('id') == 'powder_room'
            specified = laminated or opening_room.get('category') == 'bedroom' or opening.get('id') == 'main_entry'
            opening_prim.SetCustomDataByKey('leafFinish', 'laminate' if laminated else 'veneer')
            opening_prim.SetCustomDataByKey('leafFinishBasis', 'Annexure F, Miami PWC House Documents.pdf page 28' if specified else 'Veneer appearance assumed for this unlisted door')
        if opening.get('no_header'):
            opening_prim.SetCustomDataByKey('assemblyNote', 'Full-height circulation opening; no inferred frame, leaf or lintel')
            continue
        _wall_piece(stage, base, 0, a, b, 0, length, head, height, .15, materials['wall'], modules)
        if kind != 'opening':
            frame_material = materials['metal'] if home_details and kind == 'sliding_door' else materials['door']
            if home_details and kind == 'sliding_door':
                opening_prim.SetCustomDataByKey('frameFinish', 'aluminium')
                opening_prim.SetCustomDataByKey('frameFinishBasis', 'Annexure F, Miami PWC House Documents.pdf page 28; exact colour assumed')
            _wall_piece(stage, base, 1, a, b, 0, .035, 0, head, .16, frame_material, modules)
            _wall_piece(stage, base, 2, a, b, length-.035, length, 0, head, .16, frame_material, modules)
            _wall_piece(stage, base, 3, a, b, .035, length-.035, head-.035, head, .16, frame_material, modules)
        ux, uy = (b[0]-a[0])/length, (b[1]-a[1])/length
        yaw = math.degrees(math.atan2(uy, ux))
        if kind == 'door':
            room = next((r for r in rooms if r.get('id') == opening.get('space_id')), None)
            sign = 1
            if room:
                cx = sum(p[0] for p in room['polygon']) / len(room['polygon'])
                cy = sum(p[1] for p in room['polygon']) / len(room['polygon'])
                sign = 1 if -uy*(cx-a[0])+ux*(cy-a[1]) >= 0 else -1
            angle = math.radians(yaw + sign*75)
            dx, dy = math.cos(angle), math.sin(angle)
            hinge = [a[0]+ux*.04, a[1]+uy*.04]
            width = length-.09
            _box(stage, base+'/Leaf', (hinge[0]+dx*width/2, hinge[1]+dy*width/2, head/2),
                 (width, .035, head-.07), yaw+sign*75, door_material, modules, collision=False)
            _box(stage, base+'/Handle', (hinge[0]+dx*(width-.1)-dy*.027, hinge[1]+dy*(width-.1)+dx*.027, 1.02),
                 (.1, .025, .025), yaw+sign*75, materials['metal'], modules, collision=False)
            opening_prim.SetCustomDataByKey('assemblyNote', 'Illustrative timber leaf, slim frame and handle; hinge at opening start, 75-degree swing toward room assumed; leaf is not a physics obstacle')
            opening_prim.SetCustomDataByKey('swingDeg', float(sign*75))
        elif kind == 'sliding_door':
            for panel in range(2):
                along, offset = length*.75, (panel-.5)*.04
                _box(stage, f'{base}/Glass_{panel}', (a[0]+ux*along-uy*offset, a[1]+uy*along+ux*offset, head/2),
                     (length/2-.04, .014, head-.07), yaw, materials['glass'], modules, collision=False)
                _box(stage, f'{base}/Stile_{panel}', (a[0]+ux*(length/2+.02)-uy*offset, a[1]+uy*(length/2+.02)+ux*offset, head/2),
                     (.03, .028, head-.07), yaw, materials['metal'], modules, collision=False)
            opening_prim.SetCustomDataByKey('assemblyNote', 'Illustrative two-panel glass slider shown half-open; panel arrangement, frame and finish assumed; panels are not physics obstacles')

    presentation_decisions = _specified_home(stage, plan, materials, modules) if home_details else []

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

    asset_imports = []
    for i, placement in enumerate(plan.get("asset_placements", [])):
        path = _safe_asset_path(str(placement["asset_path"]), output_path)
        source_stage = Usd.Stage.Open(str(output_path.parent / path))
        if not source_stage or not source_stage.GetDefaultPrim():
            raise ValueError('SimReady asset must have a valid USD stage and default prim')
        source_units = UsdGeom.GetStageMetersPerUnit(source_stage)
        source_axis = str(UsdGeom.GetStageUpAxis(source_stage))
        if not math.isfinite(source_units) or source_units <= 0:
            raise ValueError('SimReady asset metersPerUnit must be positive and finite')
        if source_axis not in {'Y', 'Z'}:
            raise ValueError('SimReady asset upAxis must be Y or Z')
        unit_scale = source_units / UsdGeom.GetStageMetersPerUnit(stage)
        prim = UsdGeom.Xform.Define(stage, f"/World/Assets/{safe_name(placement.get('id', f'asset_{i}'))}").GetPrim()
        position = list(map(float, placement.get("position", [0, 0, 0])))
        rotation = float(placement.get("rotation_deg", 0))
        if len(position) != 3 or not all(math.isfinite(v) for v in [*position, rotation]):
            raise ValueError('SimReady position and rotation must be finite metre coordinates')
        xform = UsdGeom.Xformable(prim)
        xform.AddTranslateOp().Set(Gf.Vec3d(*position))
        xform.AddRotateZOp().Set(rotation)
        # Reference below a placement wrapper: many SimReady roots already
        # author translate/rotate/scale ops and cannot accept duplicate ops.
        model = stage.DefinePrim(str(prim.GetPath()) + "/Model")
        model.GetReferences().AddReference(path)
        prim.SetCustomDataByKey("simReady", True)
        _configure_asset_physics(stage, prim, model, placement,
                                 physics_materials["Furniture"], modules)
        # Physics variants can author a different root transform stack.
        source_reset = UsdGeom.Xformable(model).GetResetXformStack()
        if source_reset:
            # A standalone root reset would otherwise ignore placement and
            # unit conversion. Its authored translate/rotate/scale stay intact.
            UsdGeom.Xformable(model).SetResetXformStack(False)
        # USD references do not convert stage units or up axes. Keep the
        # vendor root operations intact and normalize on the placement wrapper.
        bound = UsdGeom.BBoxCache(Usd.TimeCode.Default(),
            [UsdGeom.Tokens.default_, UsdGeom.Tokens.render, UsdGeom.Tokens.proxy]).ComputeRelativeBound(model, prim)
        conversion = Gf.Matrix4d().SetScale(unit_scale)
        if source_axis == 'Y':
            conversion *= Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(1, 0, 0), 90))
        bound.Transform(conversion)
        box = bound.ComputeAlignedBox()
        if box.IsEmpty() or not all(math.isfinite(float(v)) for v in [*box.GetMin(), *box.GetMax()]):
            raise ValueError('SimReady asset must have finite bounded geometry')
        anchor = -float(box.GetMin()[2])
        xform.AddTranslateOp(opSuffix='floorAnchor').Set(Gf.Vec3d(0, 0, anchor))
        if source_axis == 'Y':
            xform.AddRotateXOp().Set(90)
        xform.AddScaleOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(unit_scale))
        floor_anchor = 'Asset geometry bottom anchored to placement Z; source pivot offset adjusted without resizing furniture'
        for key, value in {'sourceUnits': source_units, 'sourceUpAxis': source_axis,
                           'sourceRootReset': source_reset, 'unitScale': unit_scale, 'floorAnchor': floor_anchor,
                           'floorAnchorOffsetM': anchor}.items():
            prim.SetCustomDataByKey(key, value)
        asset_imports.append({'id': str(placement.get('id', f'asset_{i}')),
            'name': str(placement.get('name', source_stage.GetDefaultPrim().GetName())),
            'source_units_m': source_units, 'source_up_axis': source_axis,
            'source_root_reset': source_reset,
            'unit_scale': unit_scale, 'position_m': position,
            'size_xyz_m': [float(v) for v in box.GetSize()], 'bottom_m': position[2],
            'floor_anchor': floor_anchor, 'floor_anchor_offset_m': anchor,
            'note': 'Source units and up-axis converted to building metres/Z-up; source transforms and furniture size retained; floor anchoring is an explicit placement assumption'})
    world.GetPrim().SetCustomDataByKey('assetImports', json.dumps(asset_imports, ensure_ascii=False))
    if style in INTERIOR_SCHEMES:
        dress = _interior_scheme if home_details else _generic_interior_scheme
        presentation_decisions += dress(stage, plan, style, materials, modules)
        world.GetPrim().SetCustomDataByKey('presentationDecisions', json.dumps(presentation_decisions, ensure_ascii=False))

    warm_styles = {"home_specification", "contemporary", "classic", "home_luxury", "warm_office", "executive_office", "luxury_showroom"}
    cool_styles = {"factory", "hightech_factory", "tech_showroom"}
    if style in INTERIOR_SCHEMES:
        scheme = INTERIOR_SCHEMES[style]
        sky_intensity, sky_color, sun_intensity, sun_color = scheme['sky'], (1.0, .94, .85), scheme['sun'], (1.0, .91, .79)
    elif style in warm_styles:
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
    from .editable_objects import apply_object_edits
    editable_objects = apply_object_edits(stage, plan, style, presentation_decisions)
    from .runtime_trace import runtime_trace
    trace = runtime_trace(executed=['usd_authoring']+(['asset_import'] if asset_imports else []))
    world.GetPrim().SetCustomDataByKey('libraryTrace', json.dumps(trace))
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
        "asset_imports": asset_imports,
        "presentation_decisions": presentation_decisions,
        "editable_objects": editable_objects,
        "runtime_trace": trace,
    }


def build_style_variants(plan: dict, output_dir: str | Path) -> dict:
    """Build every palette and a composition file with a USD style variant."""
    Gf, _, Usd, UsdGeom, _, _, _ = _pxr()
    del Gf
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    category = plan.get("structure_type", "home")
    selected_styles = [name for name, spec in PALETTES.items()
                       if (category == "other" or spec["category"] == category)
                       and ((name != 'home_specification' and not spec.get('requires_reference')) or plan.get('source', {}).get('primary_crop') == 'agreement_unit_crop.jpg')]
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
    from .runtime_trace import runtime_trace
    trace = runtime_trace(executed=['usd_authoring'] + (['asset_import'] if any(report['asset_imports'] for report in reports.values()) else []))
    return {"variants_path": str(variants_path), "styles": reports, "runtime_trace": trace}
