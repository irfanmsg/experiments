"""Conservative, reviewable placements of installed full-size USD furniture."""

import math
import os
from pathlib import Path
import re

from pxr import Tf

from shapely.affinity import rotate, translate
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

from .geometry import safe_name
from .asset_library import DEFAULT_ASSET_ROOT


_MATCH = {'sofa': r'sofa|couch', 'chair': r'chair', 'coffee_table': r'coffee.*table',
          'dining_table': r'dining.*table', 'table': r'table', 'bed': r'\bbed\b',
          'desk': r'desk|workstation', 'shelving': r'shelv|storage rack', 'pallet': r'pallet'}


def _roles(room, building, single_room=False):
    label = ' '.join(str(room.get(key, '')) for key in ('category', 'name', 'id')).lower().replace('_', ' ')
    if re.search(r'balcon|bath|toilet|kitchen|corridor|hallway|stairs|service|terrace', label):
        return [], 'Wet, outdoor, service and circulation spaces require a specific furnishing plan.'
    if building == 'home':
        if re.search(r'living|lounge|family', label) and 'dining' in label:
            return ['sofa', 'coffee_table', 'dining_table', 'chair'], 'Assumed combined living and dining furniture from the room label.'
        for pattern, roles in [(r'bedroom|sleep', ['bed']), (r'living|lounge|family', ['sofa', 'coffee_table', 'chair']),
                               (r'dining', ['dining_table', 'chair']), (r'study|office|wfh|work', ['desk', 'chair'])]:
            if re.search(pattern, label):
                return roles, 'Assumed furniture roles from the room label: '+label.strip()+'.'
    if building == 'office':
        if re.search(r'meeting|conference', label):
            return ['table', 'chair'], 'Assumed meeting furniture from the room label.'
        if re.search(r'office|work|study', label):
            return ['desk', 'chair'], 'Assumed workstation furniture from the room label.'
    if building == 'factory' and re.search(r'factory|warehouse|storage|production|workshop', label):
        return ['shelving', 'pallet'], 'Assumed storage/handling roles; equipment and operating aisles need review.'
    if building == 'showroom' and re.search(r'showroom|display|sales', label):
        return ['table', 'shelving'], 'Assumed display furniture from the room label.'
    defaults = {'office': ['desk', 'chair'], 'factory': ['shelving', 'pallet'], 'showroom': ['table', 'shelving']}
    generic_category = str(room.get('category', '')).lower() in {'', 'room', 'space', 'other', 'unknown'}
    generic_name = re.fullmatch(r'(?:(?:detected )?(?:room|space|area|zone)[ _-]*\d*)?', str(room.get('name', '')).strip(), re.I)
    if single_room and building in defaults and generic_category and generic_name:
        return defaults[building], f'Assumed starter {building} use for a single reviewed room; confirm this room purpose before accepting the arrangement.'
    return [], 'Label this room with its purpose before suggesting furniture; building type alone does not identify room use.'


def _asset_bounds(path, physics_mode='static'):
    """Match the builder's unit/up-axis conversion while retaining its XY pivot."""
    from pxr import Gf, Usd, UsdGeom
    library = Path(os.environ.get('BLUEPRINT_STUDIO_ASSET_ROOT', DEFAULT_ASSET_ROOT)).expanduser().resolve()
    source = Path(path).expanduser().absolute()
    if not source.is_file() or not source.is_relative_to(library) or not source.resolve().is_relative_to(library):
        raise ValueError('Asset must exist inside the configured asset library.')
    stage = Usd.Stage.Open(str(path))
    if not stage or not stage.GetDefaultPrim():
        raise ValueError('Asset has no default prim.')
    # Changes live only in the anonymous session layer, never the source asset.
    stage.SetEditTarget(stage.GetSessionLayer())
    root = stage.GetDefaultPrim()
    variant = root.GetVariantSet('PhysicsVariant')
    if physics_mode != 'none' and 'RigidBody' in variant.GetVariantNames():
        variant.SetVariantSelection('RigidBody')
    units, axis = UsdGeom.GetStageMetersPerUnit(stage), str(UsdGeom.GetStageUpAxis(stage))
    if not math.isfinite(units) or units <= 0 or axis not in {'Y', 'Z'}:
        raise ValueError('Asset needs valid physical units and up axis.')
    bound = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render', 'proxy']).ComputeWorldBound(root)
    conversion = Gf.Matrix4d().SetScale(units)
    if axis == 'Y':
        conversion *= Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(1, 0, 0), 90))
    bound.Transform(conversion)
    aligned = bound.ComputeAlignedBox()
    size = [float(v) for v in aligned.GetSize()]
    if aligned.IsEmpty() or not all(math.isfinite(v) and v > 0 for v in size):
        raise ValueError('Asset has no finite physical volume.')
    center = [float(v) for v in aligned.GetMidpoint()]
    return size, center


def furniture_layout(plan, catalog_assets, occupied_objects=()):
    """Return new placements and decisions; never mutate the plan or resize assets.

    The caller must gate automatic use on accepted scale and reviewed room
    outlines. These limited suggestions are not a circulation or safety audit.
    ``occupied_objects`` supplies measured world bounds of generated furniture
    and floor-level decor in the current edited style.
    """
    result = {'placements': [], 'decisions': []}

    def decision(room, role, summary, status='skipped', **details):
        result['decisions'].append({'id': f'auto_{safe_name(room)}_{role}', 'room_id': room,
                                    'role': role, 'status': status, 'summary': summary, **details})

    if plan.get('units') != 'm':
        decision('plan', 'scale', 'Confirm a metric scale before suggesting physical-size assets.')
        return result
    if not plan.get('rooms'):
        decision('plan', 'rooms', 'Accept room outlines and label their purposes before suggesting furniture.')
        return result
    building = plan.get('structure_type', 'home')
    available = [asset for asset in catalog_assets if building in asset.get('structure_types', [])]
    cache = {}

    def measured(path, mode='static'):
        key = (str(path), mode)
        if key not in cache:
            cache[key] = _asset_bounds(path, mode)
        return cache[key]

    occupied, existing = [], []
    for item in occupied_objects:
        try:
            x0, y0, x1, y1 = map(float, item['bounds_xy_m'])
            if not all(math.isfinite(value) for value in (x0, y0, x1, y1)) or x0 >= x1 or y0 >= y1:
                raise ValueError('Invalid generated object bounds')
            shape = box(x0, y0, x1, y1)
            occupied.append(shape.buffer(.25))
            existing.append((item, shape))
        except (ValueError, KeyError, TypeError):
            decision('plan', 'existing_objects', 'An existing generated object could not be measured. Regenerate the current style before suggesting furniture.')
            return result
    for item in plan.get('asset_placements', []):
        try:
            size, center = measured(item['asset_path'], item.get('physics_mode', 'static'))
            shape = box(center[0]-size[0]/2, center[1]-size[1]/2, center[0]+size[0]/2, center[1]+size[1]/2)
            shape = translate(rotate(shape, float(item.get('rotation_deg', 0)), origin=(0, 0)),
                              *map(float, item.get('position', [0, 0])[:2]))
            occupied.append(shape.buffer(.25))
            name = item.get('name') or next((a['name'] for a in catalog_assets if a.get('usd_path') == item['asset_path']), '')
            existing.append(({**item, 'name': name}, shape))
        except (ValueError, OSError, KeyError, TypeError, Tf.ErrorException):
            decision('plan', 'existing_assets', 'An existing asset could not be measured. Repair its library reference before adding suggestions.')
            return result
    walls = plan.get('wall_segments', [])
    for wall in walls:
        occupied.append(LineString([wall['start'], wall['end']]).buffer(float(wall.get('thickness_m') or .18)/2+.1))
    for opening in plan.get('openings', []):
        a, b = opening.get('start'), opening.get('end')
        width = float(opening.get('width_m') or opening.get('width') or .9)
        if a is not None and b is not None:
            clearance = .65 if opening.get('no_header') else max(.65, width)
            occupied.append(LineString([a, b]).buffer(clearance))
        elif opening.get('center') is not None or opening.get('position') is not None:
            occupied.append(Point((opening.get('center') or opening['position'])[:2]).buffer(width+.65))
        else:
            wall = next((w for i, w in enumerate(walls)
                         if str(w.get('id', i)) == str(opening.get('wall_id', opening.get('wall', opening.get('wall_index'))))), None)
            if wall:
                segment = LineString([wall['start'], wall['end']])
                offset = next((float(opening[key]) for key in ('offset_m', 'distance_m', 'center_m') if key in opening), segment.length/2)
                occupied.append(segment.interpolate(offset).buffer(width+.65))
            else:
                decision('plan', 'openings', 'An opening has no usable position. Locate it before adding furniture suggestions.')
                return result
    footprint = plan.get('footprint', {})
    outline = Polygon(footprint['polygon'], footprint.get('holes', [])) if footprint.get('polygon') else None
    for hole in footprint.get('holes', []):
        occupied.append(Polygon(hole).buffer(.1))
    used_ids = {item.get('id') for item in plan.get('asset_placements', [])}
    for index, room in enumerate(plan['rooms']):
        identifier = str(room.get('id', f'room_{index}'))
        roles, basis = _roles(room, building, len(plan['rooms']) == 1)
        if not roles:
            decision(identifier, 'room_use', basis)
            continue
        polygon = Polygon(room['polygon'], room.get('holes', []))
        if not polygon.is_valid or (outline is not None and not outline.is_valid):
            decision(identifier, 'geometry', 'Repair the room or footprint boundary before furnishing.')
            continue
        safe = polygon.buffer(-.2)
        if outline is not None:
            safe = safe.intersection(outline.buffer(-.1))
        low_x, low_y, high_x, high_y = polygon.bounds
        # ponytail: fixed candidate grid can miss a valid fit; skip without
        # shrinking real furniture when this small deterministic search fails.
        candidates = [(low_x+(high_x-low_x)*x/10, low_y+(high_y-low_y)*y/10)
                      for x in (2, 8, 5, 3, 7, 1, 9, 4, 6) for y in (2, 8, 5, 3, 7, 1, 9, 4, 6)]
        for role in roles:
            placement_id = f'auto_{safe_name(identifier)}_{role}'
            pattern = _MATCH[role]
            if placement_id in used_ids or any(shape.intersects(polygon) and re.search(pattern, item.get('name', ''), re.I)
                                                for item, shape in existing):
                decision(identifier, role, 'Existing furniture already covers this role; its placement is preserved.')
                continue
            matches = [asset for asset in available if re.search(pattern, asset.get('name', ''), re.I)]
            if role == 'chair' and building == 'office':
                matches.sort(key=lambda asset: ('armchair' in asset.get('name', '').lower(),
                                                'office' not in asset.get('category', '').lower()))
            if not matches:
                decision(identifier, role, f'No installed {role.replace("_", " ")} asset matches {building}. Import a suitable full-size USD asset or place one manually.')
                continue
            chosen = None
            positions = candidates
            if role in {'coffee_table', 'chair'}:
                companion = 'sofa|couch' if role == 'coffee_table' else 'desk|dining.*table|coffee.*table|table'
                anchor = next((shape.centroid for item, shape in reversed(existing)
                               if shape.intersects(polygon) and re.search(companion, item.get('name', ''), re.I)), None)
                if anchor is not None:
                    positions = sorted(candidates, key=lambda point: (point[0]-anchor.x)**2+(point[1]-anchor.y)**2)
            for asset in matches:
                try:
                    size, center = measured(asset['usd_path'])
                except (ValueError, OSError, KeyError, TypeError, Tf.ErrorException):
                    continue
                if size[2] > float(plan.get('room_height_m') or 2.8):
                    continue
                for angle in (0, 90):
                    width, depth = (size[0], size[1]) if angle == 0 else (size[1], size[0])
                    blocked = unary_union(occupied)
                    for x, y in positions:
                        shape = box(x-width/2, y-depth/2, x+width/2, y+depth/2)
                        if safe.covers(shape) and not blocked.intersects(shape):
                            chosen = (asset, size, center, angle, x, y, shape)
                            break
                    if chosen:
                        break
                if chosen:
                    break
            if not chosen:
                decision(identifier, role, 'No full-size asset fits the room, height and recorded clearances, or its source cannot be measured. Review the room and library assets; nothing was resized.')
                continue
            asset, size, center, angle, x, y, shape = chosen
            cx, cy = (center[0], center[1]) if angle == 0 else (-center[1], center[0])
            provenance = basis+' Suggested full-size catalog asset; placement and room role need review. Door/wall/object clearances checked; circulation is not certified.'
            placement = {'id': placement_id, 'name': asset['name'], 'asset_path': asset['usd_path'],
                         'room_id': identifier, 'position': [x-cx, y-cy, 0], 'rotation_deg': angle,
                         'physics_mode': 'static', 'size_xyz_m': size,
                         'asset_kind': asset.get('asset_kind', 'Catalog USD asset (SimReady not verified)'),
                         'provenance': provenance}
            result['placements'].append(placement)
            occupied.append(shape.buffer(.25))
            existing.append((placement, shape))
            used_ids.add(placement_id)
            decision(identifier, role, provenance, 'proposed', asset_name=asset['name'],
                     asset_kind=placement['asset_kind'], size_xyz_m=size,
                     placement_center_xy_m=[x, y], source_center_offset_xy_m=[cx, cy])
    return result
