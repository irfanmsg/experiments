"""Dimension-driven B1-1502 reconstruction.

Printed clear dimensions are hard constraints. Adjacency comes from the drawing;
partition thickness (0.15 m), orthogonal room alignment and exact curve shape
remain modeling assumptions. Source raster geometry is kept separately.
"""
from __future__ import annotations

from copy import deepcopy
import math

from shapely import affinity, set_precision
from shapely.geometry import Polygon, LineString, Point, box
from shapely.ops import unary_union

VERSION = 'b1-clear-dimensions-v1'
PARTITION = 0.15


def _parts(geometry):
    if geometry.is_empty:
        return []
    return list(geometry.geoms) if hasattr(geometry, 'geoms') else [geometry]


def _rectangles(geometry):
    """Disjoint rectangles for orthogonal wall solids (including holes)."""
    for polygon in _parts(set_precision(geometry, 1e-7)):
        if polygon.geom_type != 'Polygon' or polygon.area < 1e-8:
            continue
        xs = sorted({round(x, 8) for ring in [polygon.exterior, *polygon.interiors] for x, _ in ring.coords})
        low_y, high_y = polygon.bounds[1], polygon.bounds[3]
        for x0, x1 in zip(xs, xs[1:]):
            if x1-x0 < 1e-7:
                continue
            for piece in _parts(polygon.intersection(box(x0, low_y-1, x1, high_y+1))):
                if piece.geom_type != 'Polygon' or piece.area < 1e-8:
                    continue
                bounds = piece.bounds
                if abs(box(*bounds).area-piece.area) > 1e-7:
                    raise ValueError(f'Wall decomposition encountered a non-rectangular region: {piece.wkt} area={piece.area} box={box(*bounds).area}')
                yield bounds


def relocate_assets(placements, rooms):
    """Move placements with rooms, without changing furniture scale."""
    result = deepcopy(placements)
    for asset in result:
        x, y, z = asset['position']
        candidates = [r for r in rooms if r.get('source_polygon')]
        room = min(candidates, key=lambda r: Polygon(r['source_polygon']).distance(Point(x, y)))
        old = Polygon(room['source_polygon']).bounds
        new = Polygon(room['polygon']).bounds
        asset['position'] = [round(new[0]+(x-old[0])/(old[2]-old[0])*(new[2]-new[0]), 6),
                             round(new[1]+(y-old[1])/(old[3]-old[1])*(new[3]-new[1]), 6), z]
    return result


def build_dimensioned_plan(source):
    plan = deepcopy(source)
    rooms = {r['id']: r for r in plan['rooms']}
    t = PARTITION
    bounds = {}

    def size(name):
        w, h = map(float, rooms[name]['dimensions_m'])
        if not all(math.isfinite(v) and v > 0 for v in (w, h)):
            raise ValueError(f'Invalid printed dimensions for {name}')
        return w, h

    def put(name, *, left=None, right=None, bottom=None, top=None):
        w, h = size(name)
        x = float(left) if left is not None else float(right)-w
        y = float(bottom) if bottom is not None else float(top)-h
        bounds[name] = (x, y, x+w, y+h)
        return bounds[name]

    # Living/dining is the layout anchor; the coordinate origin is arbitrary.
    # All subsequent positions are relationships, not raster pixel distances.
    lx, ly, rx, ty = put('living_dining', left=2.8, bottom=9.8)
    on = put('bedroom_outer_north', right=rx, bottom=ty+t)
    bn = put('bedroom_north', right=on[0]-t-size('bathroom_north')[0]-t, bottom=ty+t)
    k = put('kitchen', right=bn[0]-t, bottom=ty+t)
    bath = put('bathroom_north', left=bn[2]+t, top=bn[3])
    put('bathroom_outer_north', left=on[0], bottom=on[3]+t)
    db = put('dry_balcony', right=bn[0], bottom=k[3]+t)
    kb = put('kitchen_balcony', left=bn[0]+t, bottom=bn[3]+t)
    service = put('service_room', right=db[0]-t, bottom=db[1])
    put('service_wc', left=service[0], bottom=service[3]+t)
    put('entry', right=lx, bottom=ly)
    os = put('bedroom_outer_south', right=rx, top=ly-t)
    wfh = put('wfh', right=os[0]-t, top=ly-t)
    passage = put('passage', right=wfh[0]-t, top=ly-t)
    bs = put('bedroom_south', right=passage[2], top=passage[1])
    put('bathroom_south', left=bs[2]+t, top=wfh[1]-t)
    walk = put('walk_in', left=os[0], top=os[1]-t)
    put('bathroom_outer_south', left=walk[2]+t, top=os[1]-t)

    shapes = {}
    for name, b in bounds.items():
        shapes[name] = box(*b)
        room = rooms[name]
        room['source_polygon'] = deepcopy(room['polygon'])
        room['polygon'] = [[b[0], b[3]], [b[2], b[3]], [b[2], b[1]], [b[0], b[1]]]
        room['dimension_mode'] = 'clear_rectangle'
        room['geometry_provenance'] = 'printed clear dimensions; adjacency reconstructed from source drawing'
        room['confidence'] = 'printed dimensions enforced; wall thickness and orthogonal alignment assumed'
        room.pop('geometry_uncertainty_m', None)

    # Irregular terraces: the labels specify average depth, not a rectangular
    # bounding box. Enforce area / labelled span = average depth, retain a
    # provisional curved/trapezoidal shape, and do not call the max depth "AVG".
    curved = rooms['balcony_curved']
    depth, span = size('balcony_curved')
    y0 = (on[3]+os[1]-span)/2
    profile = [(0, 0), (0, span)]
    # Use a provisional bowed profile; its detailed curve is not measured.
    for i in range(13):
        f = i/12
        profile.append((0.35 + 2.1*math.sin(math.pi*f), span*(1-f)))
    shape = Polygon(profile)
    shape = affinity.scale(shape, xfact=depth*span/shape.area, yfact=1, origin=(0, 0))
    shapes['balcony_curved'] = affinity.translate(shape, xoff=rx+t, yoff=y0)
    south = rooms['balcony_south']
    width, average = size('balcony_south')
    # The lower edge slopes as in the scan; only its mean depth is dimensioned.
    shape = Polygon([(0, 0), (width, 0), (width, -average*.8), (0, -average*1.2)])
    shapes['balcony_south'] = affinity.translate(shape, xoff=bs[0], yoff=bs[1]-t)
    for name, axis in [('balcony_curved', 1), ('balcony_south', 0)]:
        room = rooms[name]
        room['source_polygon'] = deepcopy(room['polygon'])
        room['polygon'] = [list(p) for p in list(shapes[name].exterior.coords)[:-1]]
        room['dimension_mode'] = 'average_depth'
        room['span_axis'] = axis
        room['dimension_roles'] = ['average_depth', 'span'] if axis == 1 else ['span', 'average_depth']
        room['geometry_provenance'] = 'printed span and average depth enforced; curve/slope remains a visualization assumption'
        room['confidence'] = 'printed span/average enforced; detailed perimeter unmeasured'

    names = list(shapes)
    for i, a in enumerate(names):
        for b in names[i+1:]:
            if shapes[a].intersection(shapes[b]).area > 1e-7:
                raise ValueError(f'Dimension constraints overlap rooms: {a}, {b}')

    # Open north circulation ties the living space to the toilet/bedroom doors.
    circulation = box(bn[2], ty, on[0], bath[1]-t)
    clear = unary_union([*shapes.values(), circulation])
    inside = unary_union([shape for name, shape in shapes.items() if rooms[name]['category'] != 'balcony'])
    masonry = inside.buffer(t, join_style=2).difference(inside).difference(clear)
    glazing = unary_union([
        box(rx, os[1], rx+t, on[3]),
        box(bs[0], bs[1]-t, bs[2], bs[1]),
        box(bn[0], bn[3], bn[2], bn[3]+t),
    ]).intersection(masonry)
    masonry = masonry.difference(glazing)
    gaps = []
    openings = []

    def opening(identifier, room, side, fraction, width, kind='door', no_header=False):
        b = bounds[room]
        horizontal = side in {'north', 'south'}
        start, end = (b[0], b[2]) if horizontal else (b[1], b[3])
        width = min(width, end-start)
        middle = max(start+width/2, min(end-width/2, start+(end-start)*fraction))
        constant = {'north': b[3]+t/2, 'south': b[1]-t/2,
                    'west': b[0]-t/2, 'east': b[2]+t/2}[side]
        lo, hi = middle-width/2, middle+width/2
        a, z = ([lo, constant], [hi, constant]) if horizontal else ([constant, lo], [constant, hi])
        # Cut both shared-wall copies; full thickness remains outside clear rooms.
        gaps.append(box(lo, constant-t, hi, constant+t) if horizontal else box(constant-t, lo, constant+t, hi))
        if not no_header:
            openings.append({'id': identifier, 'type': kind, 'space_id': room,
                             'start': a, 'end': z, 'center': [(a[j]+z[j])/2 for j in range(2)],
                             'width_m': width, 'height_m': 2.2, 'free_opening': True,
                             'confidence': 'location from source topology; width and assembly assumed'})

    opening('main_entry', 'entry', 'west', .6, .93)
    opening('entry_to_living', 'entry', 'east', .5, size('entry')[1], no_header=True)
    # Also remove the living room's wall at this zero-gap open boundary.
    eb = bounds['entry']; gaps.append(box(lx-t, eb[1], lx+t, eb[3]))
    opening('kitchen_to_living', 'kitchen', 'south', 1, k[2]-lx, no_header=True)
    gaps.append(box(bn[2], ty-t, on[0], ty+t))
    opening('passage_opening', 'passage', 'north', .5, .93, 'opening')
    opening('passage_to_south_bedroom', 'passage', 'south', .5, size('passage')[0], no_header=True)
    pb = bounds['passage']; gaps.append(box(pb[0], pb[1]-t, pb[2], pb[1]+t))
    opening('north_bedroom_door', 'bedroom_north', 'east', .13, .86)
    opening('outer_north_bedroom_door', 'bedroom_outer_north', 'south', .5, 1.03)
    opening('wfh_door', 'wfh', 'north', .8, .94)
    opening('outer_lower_bedroom_door', 'bedroom_outer_south', 'north', .12, .93)
    opening('service_wc_door', 'service_wc', 'south', .8, .8)
    opening('service_room_door', 'service_room', 'east', .5, .86)
    opening('kitchen_dry_balcony_door', 'kitchen', 'north', .75, .9)
    opening('north_toilet_door', 'bathroom_north', 'south', .7, .79)
    opening('outer_north_toilet_door', 'bathroom_outer_north', 'south', .2, .8)
    opening('south_toilet_door', 'bathroom_south', 'west', .2, .8)
    opening('walk_in_door', 'walk_in', 'north', .5, .8)
    opening('outer_south_toilet_door', 'bathroom_outer_south', 'west', .5, .8)
    opening('living_balcony_slider', 'living_dining', 'east', .5, 1.96, 'sliding_door')
    opening('lower_balcony_slider', 'bedroom_south', 'south', .5, 1.56, 'sliding_door')
    opening('kitchen_balcony_slider', 'bedroom_north', 'north', .65, 1.67, 'sliding_door')
    door_cuts = unary_union(gaps)
    masonry, glazing = masonry.difference(door_cuts), glazing.difference(door_cuts)
    walls = []
    for kind, geometry in [('partition', masonry), ('glazed_exterior', glazing)]:
        for i, (x0, y0, x1, y1) in enumerate(_rectangles(geometry)):
            if max(x1-x0, y1-y0) < .005:
                continue
            horizontal = x1-x0 >= y1-y0
            a, b = ([x0, (y0+y1)/2], [x1, (y0+y1)/2]) if horizontal else ([(x0+x1)/2, y0], [(x0+x1)/2, y1])
            walls.append({'id': f'{kind}_{i:03d}', 'start': a, 'end': b, 'kind':kind,
                          'thickness_m': (y1-y0) if horizontal else (x1-x0),
                          'height_m': plan['room_height_m'], 'confidence':'dimension-driven',
                          'geometry_provenance':'outside dimensioned room clear boundaries',
                          'height_thickness_provenance':'assumed wall build-up and height'})
    for name, shape in shapes.items():
        if rooms[name]['category'] != 'balcony':
            continue
        ring = list(shape.exterior.coords)
        for i, (a, b) in enumerate(zip(ring, ring[1:])):
            line = LineString([a, b])
            if line.length < .05 or inside.distance(line.interpolate(.5, normalized=True)) < t+.001:
                continue
            # Offset rails outside the dimensioned clear balcony footprint.
            left_normal = (-(b[1]-a[1])/line.length, (b[0]-a[0])/line.length)
            sign = -1 if shape.exterior.is_ccw else 1
            offset = [sign * n * .04 for n in left_normal]
            walls.append({'id':f'{name}_guard_{i}', 'start':[a[j]+offset[j] for j in (0,1)],
                          'end':[b[j]+offset[j] for j in (0,1)], 'kind':'balcony_guard',
                          'height_m':1.1, 'thickness_m':.08, 'confidence':'assumed railing build-up'})
    # The slab follows the dimensioned rooms and the source's connecting spaces.
    # It is a gross geometric footprint, not the RERA net area schedule.
    footprint = unary_union([clear, inside.buffer(t, join_style=2),
                             *[LineString([o['start'],o['end']]).buffer(t, cap_style=2) for o in openings]])
    # Connect terrace floors across the glazing thickness; do not fill service voids.
    footprint = unary_union([footprint, box(rx, os[1], rx+t, on[3]),
                            box(bs[0], bs[1]-t, bs[2], bs[1]),
                            box(db[0], k[3], db[2], db[1]), box(kb[0], bn[3], kb[2], kb[1])])
    if footprint.geom_type != 'Polygon':
        raise ValueError('Dimensioned plan produced disconnected floor components')
    plan['source_wall_segments'] = deepcopy(source['wall_segments'])
    plan['source_footprint'] = deepcopy(source['footprint'])
    plan['footprint'] = {'polygon':[list(p) for p in list(footprint.exterior.coords)[:-1]],
                         'holes':[[list(p) for p in list(ring.coords)[:-1]] for ring in footprint.interiors],
                         'includes_balconies':True, 'modeled_gross_area_m2':footprint.area,
                         'confidence':'dimension-driven rooms; unmeasured connections/curve shape assumed'}
    plan['rooms'] = list(rooms.values())
    plan['wall_segments'], plan['openings'] = walls, openings
    plan['dimension_model'] = VERSION
    plan['coordinate_system']['origin'] = 'metric layout origin; source pixel registration is only for source traces'
    plan['dimension_note'] = '1 scene unit = 1 m. Rectangular clear spans and balcony span/average depth follow printed dimensions. Wall thickness, heights, orthogonal alignment and detailed curve remain assumed.'
    if plan.get('asset_placements'):
        plan['asset_placements'] = relocate_assets(plan['asset_placements'], plan['rooms'])
    return plan
