"""Agreement-driven B1-1502 reconstruction.

Printed clear dimensions are hard constraints. Adjacency comes from the drawing;
partition thickness (0.15 m), orthogonal room alignment and exact curve shape
remain modeling assumptions. Source raster geometry is kept separately.
"""
from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
from statistics import median

from shapely import affinity, set_precision
from shapely.geometry import Polygon, LineString, Point, box
from shapely.ops import unary_union

VERSION = 'b1-agreement-dimensions-v3'
PARTITION = 0.15

# Coordinates refer ONLY to the upright 546 x 810 agreement_unit_crop.jpg.
# Clear dimensions come from the demarcated B1-1502 unit on agreement page 35.
AGREEMENT_ROOMS = {
    'service_wc': ([2.14, 1.22], [(38,17),(109,19),(107,51),(37,49)]),
    'service_room': ([2.14, 2.51], [(34,53),(107,55),(106,137),(31,133)]),
    'dry_balcony': ([1.93, 1.70], [(109,84),(173,87),(172,145),(106,139)]),
    'kitchen_balcony': ([2.98, 1.70], [(178,89),(280,93),(278,148),(175,144)]),
    'kitchen': ([2.75, 4.12], [(81,145),(173,148),(169,273),(77,271)]),
    'bedroom_north': ([3.05, 4.03], [(177,152),(277,154),(273,282),(170,277)]),
    'bathroom_north': ([1.38, 2.46], [(281,128),(328,129),(325,209),(277,207)]),
    'powder_room': ([1.38, 1.38], [(278,211),(324,212),(322,254),(275,252)]),
    'bathroom_outer_north': ([2.40, 1.52], [(332,130),(412,135),(411,180),(329,176)]),
    'bedroom_outer_north': ([3.96, 3.40], [(328,184),(459,191),(451,293),(322,287)]),
    'entry': ([1.65, 2.676], [(64,328),(119,330),(118,411),(59,408)]),
    'living_dining': ([9.83, 4.03], [(120,285),(322,294),(453,298),(442,425),(119,414)]),
    'passage': ([1.77, 2.00], [(122,417),(178,419),(176,483),(119,481)]),
    'wfh': ([3.05, 3.58], [(181,424),(280,426),(277,544),(177,535)]),
    'bedroom_outer_south': ([4.65, 3.65], [(286,429),(444,434),(439,548),(279,543)]),
    'bathroom_outer_south': ([2.43, 1.52], [(328,555),(413,560),(411,599),(324,592)]),
    'walk_in': ([1.45, 2.90], [(279,550),(324,555),(322,640),(274,637)]),
    'bathroom_south': ([1.52, 2.90], [(176,541),(225,546),(225,630),(173,626)]),
    'bedroom_south': ([3.58, 4.55], [(57,484),(176,486),(171,627),(52,622)]),
    'balcony_south': ([3.58, 2.45], [(50,629),(167,633),(164,697),(42,728)]),
}
AGREEMENT_OPENINGS_PX = {
    'main_entry': ((64,330),(63,362),'D'),
    'entry_to_living': ((120,353),(118,411),None),
    'kitchen_to_living': ((122,277),(169,279),None),
    'north_circulation_to_living': ((273,285),(320,289),None),
    'passage_opening': ((122,416),(177,418),None),
    'passage_to_south_bedroom': ((138,482),(176,484),'D'),
    'north_bedroom_door': ((275,258),(274,282),'D'),
    'outer_north_bedroom_door': ((324,263),(322,291),'D'),
    'wfh_door': ((254,422),(280,424),'D'),
    'outer_lower_bedroom_door': ((280,426),(319,428),'D'),
    'service_wc_door': ((62,52),(86,53),'D'),
    'service_room_door': ((108,106),(107,131),'D'),
    'kitchen_dry_balcony_door': ((122,144),(151,145),'D'),
    'north_toilet_door': ((279,163),(278,183),'D'),
    'powder_room_door': ((294,254),(319,255),'D'),
    'outer_north_toilet_door': ((329,177),(356,179),'D'),
    'south_toilet_door': ((174,595),(173,619),'D'),
    'walk_in_door': ((283,544),(321,547),None),
    'outer_south_toilet_door': ((326,549),(325,581),'D'),
    'living_balcony_slider': ((451,330),(447,401),'SD'),
    'lower_balcony_slider': ((111,627),(161,629),'SD'),
    'kitchen_balcony_slider': ((196,148),(249,150),'SD'),
    'outer_north_balcony_slider': ((458,207),(455,270),'SD'),
    'outer_south_balcony_slider': ((444,451),(441,522),'SD'),
}


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
    source = deepcopy(source)
    approved_rooms = {r['id']: deepcopy(r) for r in source['rooms']}
    dataset = Path(__file__).resolve().parents[1]/'data'/'b1_1502'
    comparison = json.loads((dataset/'raster_trace.json').read_text())
    approved_curve = Polygon(next(room['polygon'] for room in comparison['rooms'] if room['id'] == 'balcony_curved'))
    # The agreement photo truncates the middle of the main outer arc. Register
    # the approved contour as a disclosed shape prior at agreement endpoints.
    ax0, ay0, ax1, ay1 = approved_curve.bounds
    prior = affinity.scale(approved_curve, xfact=86/(ax1-ax0), yfact=373/(ay1-ay0), origin=(ax0, ay0))
    prior = affinity.translate(prior, xoff=460-ax0, yoff=-(551+ay0))
    curve_px = [[x, -y] for x, y in list(prior.exterior.coords)[:-1]]
    reference_dimensions = [
        {'space': 'kitchen', 'printed_m': 2.75, 'raster_span_px': 92, 'axis': 'x'},
        {'space': 'bedroom_north', 'printed_m': 3.05, 'raster_span_px': 100, 'axis': 'x'},
        {'space': 'bedroom_outer_north', 'printed_m': 3.96, 'raster_span_px': 131, 'axis': 'x'},
        {'space': 'bedroom_south', 'printed_m': 3.58, 'raster_span_px': 119, 'axis': 'x'},
        {'space': 'living_dining', 'printed_m': 9.83, 'raster_span_px': 324, 'axis': 'x'},
    ]
    pixels_per_metre = median(r['raster_span_px']/r['printed_m'] for r in reference_dimensions)
    origin_px = [42, 728]

    def metric(points):
        return [[(x-origin_px[0])/pixels_per_metre, (origin_px[1]-y)/pixels_per_metre] for x, y in points]

    agreement_rooms = dict(AGREEMENT_ROOMS)
    agreement_rooms['balcony_curved'] = ([2.40, 11.07], curve_px)
    source['rooms'] = []
    for identifier, (dimensions, pixels) in agreement_rooms.items():
        pixels = [list(point) for point in pixels]
        room = deepcopy(approved_rooms.get(identifier, approved_rooms['bathroom_north']))
        room.update({'id': identifier, 'dimensions_m': dimensions, 'polygon': metric(pixels),
                     'source_image_coordinates_px': pixels,
                     'dimension_provenance': 'printed metric label on demarcated agreement B1-1502, page 35',
                     'geometry_provenance': 'approximate manual agreement raster trace'})
        room.pop('source_polygon', None)
        if identifier == 'powder_room':
            room.update({'name': 'Powder room', 'category': 'bathroom'})
        elif identifier == 'passage':
            room.update({'name': 'Mandir', 'source_name': 'Mandir', 'dimension_note': '1.77 m first digit partly clipped; needs review', 'dimension_uncertainty_m': .02})
        elif identifier == 'wfh':
            room.update({'name': 'Theatre / den', 'source_name': 'THEATER / DEN'})
        elif identifier == 'entry':
            room['dimension_note'] = '2.676 m final digit overlaps the wall symbol; needs review'
            room['dimension_uncertainty_m'] = .01
        elif identifier == 'balcony_south':
            room['dimension_note'] = '2.45 m average depth on agreement page 35; clipboard reference appears 2.46 m, needs review'
            room['dimension_uncertainty_m'] = .01
        elif identifier == 'balcony_curved':
            room['geometry_provenance'] = 'agreement facade/endpoints; cropped outer arc completed from approved contour shape prior'
        source['rooms'].append(room)
    source['openings'] = [{'id': identifier, 'start': metric([a])[0], 'end': metric([b])[0],
                           'center': metric([[(a[i]+b[i])/2 for i in (0, 1)]])[0]}
                          for identifier, (a, b, _) in AGREEMENT_OPENINGS_PX.items()]
    # Visible agreement boundary with the cropped outer arc completed by the prior.
    outline_px = [(34,14),(113,16),(110,81),(282,92),(281,119),(333,124),(417,132),(417,171),(462,178),
                  *curve_px[1:-3], (441,548),(416,554),(414,602),(324,596),(323,641),(274,640),
                  (275,558),(229,553),(228,636),(167,632),(164,699),(42,727),(56,483),(121,482),
                  (121,416),(60,413),(64,322),(121,324),(124,276),(78,273),(81,145),(32,140)]
    source['footprint'] = {'polygon': metric(outline_px), 'holes': [],
                           'provenance': 'agreement visible boundary; cropped main arc inferred from approved shape prior'}
    documents = Path.home()/'Documents'/'PWC_B1_1502'
    source['source'].update({'filename': 'Miami PWC House Documents.pdf', 'file': 'Miami PWC House Documents.pdf',
                            'page': 35, 'primary_layout': str(documents/'Miami PWC House Documents.pdf')+'#page=35',
                            'primary_crop': 'agreement_unit_crop.jpg', 'agreement_highlight': str(documents/'Miami PWC House Documents.pdf')+'#page=35',
                            'approved_plan': str(documents/'B1-Building-3.pdf')+'#page=1',
                            'area_schedule': str(documents/'B1-Building-1.pdf')+'#page=1',
                            'source_policy': 'Agreement page 35 governs this demarcated apartment layout; approved drawing and furnished brochure are comparisons.'})
    source['calibration'] = {'crop_image_size_px': [546, 810], 'origin_in_crop_px': origin_px,
                              'pixels_per_metre': pixels_per_metre, 'reference_dimensions': reference_dimensions,
                              'scan_uncertainty': 'Agreement photo skew; raster registration is approximate, not a replacement for printed dimensions.'}
    source['image_size'] = [546, 810]
    source['height_status'] = 'assumed visualization height; no section or elevation supplied by agreement'
    plan = deepcopy(source)
    manifest = dataset/'reference_manifest.json'
    if manifest.is_file():
        plan['reference_manifest'] = json.loads(manifest.read_text())
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
    lx, ly, rx, ty = put('living_dining', left=(119-origin_px[0])/pixels_per_metre,
                        bottom=(origin_px[1]-414)/pixels_per_metre)
    on = put('bedroom_outer_north', right=rx, bottom=ty+t)
    bn = put('bedroom_north', right=on[0]-t-size('bathroom_north')[0]-t, bottom=ty+t)
    k = put('kitchen', right=bn[0]-t, bottom=ty+t)
    outer_bath = put('bathroom_outer_north', left=on[0], bottom=on[3]+t)
    bath = put('bathroom_north', left=bn[2]+t, top=outer_bath[3])
    powder = put('powder_room', left=bath[0], top=bath[1]-t)
    db = put('dry_balcony', right=bn[0], bottom=k[3]+t)
    kb = put('kitchen_balcony', left=bn[0]+t, bottom=bn[3]+t)
    service = put('service_room', right=db[0]-t, bottom=db[1])
    put('service_wc', left=service[0], bottom=service[3]+t)
    put('entry', right=lx, bottom=ly)
    os = put('bedroom_outer_south', right=rx, top=ly-t)
    wfh = put('wfh', right=os[0]-t, top=ly-t)
    passage = put('passage', right=wfh[0]-t, top=ly-t)
    bs = put('bedroom_south', right=passage[2], top=passage[1]-t)
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
        room['geometry_provenance'] = 'printed agreement clear dimensions; adjacency reconstructed from agreement page 35'
        room['confidence'] = 'printed dimensions enforced; wall thickness and orthogonal alignment assumed'
        room.pop('geometry_uncertainty_m', None)

    # Retain the traced terrace contours. Adapt their inner edges to the
    # inferred orthogonal facade, then enforce the printed span/average depth.
    # Detailed curves and this registration remain reviewable assumptions.
    curved = rooms['balcony_curved']
    depth, span = size('balcony_curved')
    y0 = (on[3]+os[1]-span)/2
    raw_curve = curved['polygon']
    upper, lower = raw_curve[0], raw_curve[-3]
    shear = (upper[0]-lower[0])/(upper[1]-lower[1])
    shape = affinity.affine_transform(Polygon(raw_curve),
                                     [1, -shear, 0, 1, -lower[0]+shear*lower[1], 0])
    profile = [list(point) for point in list(shape.exterior.coords)[:-1]]
    inner_indices = [0, len(profile)-3, len(profile)-2, len(profile)-1]
    for index in inner_indices:
        profile[index][0] = 0
    shape = Polygon(profile)
    x0, sy0, x1, sy1 = shape.bounds
    xfactor, yfactor = depth*(sy1-sy0)/shape.area, span/(sy1-sy0)
    shape = affinity.scale(shape, xfact=xfactor, yfact=yfactor, origin=(0, sy0))
    shapes['balcony_curved'] = affinity.translate(shape, xoff=rx+t, yoff=y0-sy0)
    profile_parameters = {'balcony_curved': {
        'source_vertex_count': len(raw_curve), 'x_shear_per_y': shear,
        'inboard_vertices_aligned': inner_indices, 'scale_xy': [xfactor, yfactor],
        'translation_xy': [rx+t, y0-sy0], 'printed_average_depth_m': depth,
        'printed_span_m': span, 'modeled_max_depth_m': (x1-x0)*xfactor}}
    south = rooms['balcony_south']
    width, average = size('balcony_south')
    raw_south = south['polygon']
    left, right = raw_south[:2]
    shear = (right[1]-left[1])/(right[0]-left[0])
    shape = affinity.affine_transform(Polygon(raw_south), [1, 0, -shear, 1, 0, shear*left[0]])
    sx0, sy0, sx1, sy1 = shape.bounds
    xfactor, yfactor = width/(sx1-sx0), width*average/(shape.area*(width/(sx1-sx0)))
    shape = affinity.scale(shape, xfact=xfactor, yfact=yfactor, origin=(sx0, sy1))
    shapes['balcony_south'] = affinity.translate(shape, xoff=bs[0]-sx0, yoff=bs[1]-t-sy1)
    profile_parameters['balcony_south'] = {
        'source_vertex_count': len(raw_south), 'y_shear_per_x': shear,
        'scale_xy': [xfactor, yfactor], 'translation_xy': [bs[0]-sx0, bs[1]-t-sy1],
        'printed_span_m': width, 'printed_average_depth_m': average,
        'modeled_max_depth_m': (sy1-sy0)*yfactor}
    for name, axis in [('balcony_curved', 1), ('balcony_south', 0)]:
        room = rooms[name]
        room['source_polygon'] = deepcopy(room['polygon'])
        room['polygon'] = [list(p) for p in list(shapes[name].exterior.coords)[:-1]]
        room['dimension_mode'] = 'average_depth'
        room['span_axis'] = axis
        room['dimension_roles'] = ['average_depth', 'span'] if axis == 1 else ['span', 'average_depth']
        room['geometry_provenance'] = ('source contour adapted to inferred orthogonal facade; printed agreement span/average depth enforced; '
                                       + ('cropped main arc completed from approved comparison prior' if name == 'balcony_curved' else 'agreement lower-balcony perimeter traced'))
        room['confidence'] = 'source contour and printed span/average enforced; facade alignment and detailed perimeter need review'

    names = list(shapes)
    for i, a in enumerate(names):
        for b in names[i+1:]:
            if shapes[a].intersection(shapes[b]).area > 1e-7:
                raise ValueError(f'Dimension constraints overlap rooms: {a}, {b}')

    # Open north circulation ties the living space to the toilet/bedroom doors.
    circulation = box(bn[2]+t, ty, on[0]-t, powder[1]-t)
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
    raw_openings = {opening['id']: opening for opening in source['openings']}
    connections = {
        'main_entry': ['entry', 'external'], 'entry_to_living': ['entry', 'living_dining'],
        'kitchen_to_living': ['kitchen', 'living_dining'],
        'north_circulation_to_living': ['north_circulation', 'living_dining'],
        'passage_opening': ['passage', 'living_dining'],
        'passage_to_south_bedroom': ['passage', 'bedroom_south'],
        'north_bedroom_door': ['bedroom_north', 'north_circulation'],
        'outer_north_bedroom_door': ['bedroom_outer_north', 'north_circulation'],
        'wfh_door': ['wfh', 'living_dining'],
        'outer_lower_bedroom_door': ['bedroom_outer_south', 'living_dining'],
        'service_wc_door': ['service_wc', 'service_room'],
        'service_room_door': ['service_room', 'dry_balcony'],
        'kitchen_dry_balcony_door': ['kitchen', 'dry_balcony'],
        'north_toilet_door': ['bathroom_north', 'bedroom_north'],
        'powder_room_door': ['powder_room', 'north_circulation'],
        'outer_north_toilet_door': ['bathroom_outer_north', 'bedroom_outer_north'],
        'south_toilet_door': ['bathroom_south', 'bedroom_south'],
        'walk_in_door': ['walk_in', 'bedroom_outer_south'],
        'outer_south_toilet_door': ['bathroom_outer_south', 'walk_in'],
        'living_balcony_slider': ['living_dining', 'balcony_curved'],
        'lower_balcony_slider': ['bedroom_south', 'balcony_south'],
        'kitchen_balcony_slider': ['bedroom_north', 'kitchen_balcony'],
        'outer_north_balcony_slider': ['bedroom_outer_north', 'balcony_curved'],
        'outer_south_balcony_slider': ['bedroom_outer_south', 'balcony_curved'],
    }

    def record_opening(identifier, room, a, z, width, kind, no_header=False):
        image_a, image_b, symbol = AGREEMENT_OPENINGS_PX[identifier]
        reference = {'file': 'Miami PWC House Documents.pdf', 'page': 35,
                     'image': 'agreement_unit_crop.jpg',
                     'image_coordinates_px': {'jamb_start': list(image_a), 'jamb_end': list(image_b)},
                     'image_coordinate_uncertainty_px': 4, 'symbol': symbol}
        raw = raw_openings.get(identifier)
        if raw:
            reference['trace_coordinates_m'] = {key: raw[key] for key in ('start', 'end', 'center')}
        if identifier == 'walk_in_door':
            basis = 'Unmarked north gap in agreement walk-in boundary; open access retained without inventing a hinged leaf.'
        elif kind == 'sliding_door':
            basis = 'SD symbol and facade gap visible in agreement page 35; exact width and offset estimated.'
        elif no_header or kind == 'opening':
            basis = 'Agreement room boundaries show open circulation; modeled boundary extent and registration assumed.'
        else:
            basis = 'D symbol and wall gap in agreement page 35 establish the connection; exact dimensions and placement remain estimates.'
        openings.append({'id': identifier, 'type': kind, 'space_id': room,
                         'start': a, 'end': z, 'center': [(a[j]+z[j])/2 for j in range(2)],
                         'width_m': width, 'height_m': 2.2, 'free_opening': True,
                         'no_header': no_header, 'connects': connections[identifier],
                         'confidence': 'source topology; widths, height and placement require review',
                         'provenance': {'topology': 'source-derived', 'basis': basis,
                                        'source_reference': reference,
                                        'width': 'scan estimate' if symbol else 'assumed',
                                        'height': 'assumed',
                                        'placement': 'assumed offset along source-derived boundary',
                                        'width_uncertainty_m': .25,
                                        'review_status': 'needs-review'}})

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
        record_opening(identifier, room, a, z, width, 'opening' if no_header else kind, no_header)

    opening('main_entry', 'entry', 'west', .6, .93)
    opening('entry_to_living', 'entry', 'east', .5, size('entry')[1], no_header=True)
    # Also remove the living room's wall at this zero-gap open boundary.
    eb = bounds['entry']; gaps.append(box(lx-t, eb[1], lx+t, eb[3]))
    opening('kitchen_to_living', 'kitchen', 'south', 1, k[2]-lx, no_header=True)
    gaps.append(box(bn[2], ty-t, on[0], ty+t))
    record_opening('north_circulation_to_living', 'north_circulation',
                   [bn[2], ty+t/2], [on[0], ty+t/2], on[0]-bn[2], 'opening', True)
    opening('passage_opening', 'passage', 'north', .5, .93, 'opening')
    opening('passage_to_south_bedroom', 'passage', 'south', .72, .90)
    opening('north_bedroom_door', 'bedroom_north', 'east', .12, .86)
    opening('outer_north_bedroom_door', 'bedroom_outer_north', 'west', .12, .80)
    opening('wfh_door', 'wfh', 'north', .8, .94)
    opening('outer_lower_bedroom_door', 'bedroom_outer_south', 'north', .12, .93)
    opening('service_wc_door', 'service_wc', 'south', .8, .8)
    opening('service_room_door', 'service_room', 'east', .5, .86)
    opening('kitchen_dry_balcony_door', 'kitchen', 'north', .75, .9)
    opening('north_toilet_door', 'bathroom_north', 'west', .3, .80)
    opening('powder_room_door', 'powder_room', 'south', .7, .80)
    opening('outer_north_toilet_door', 'bathroom_outer_north', 'south', .2, .8)
    opening('south_toilet_door', 'bathroom_south', 'west', .2, .8)
    opening('walk_in_door', 'walk_in', 'north', .5, .8, 'opening')
    opening('outer_south_toilet_door', 'bathroom_outer_south', 'west', .5, .8)
    opening('living_balcony_slider', 'living_dining', 'east', .5, 1.96, 'sliding_door')
    opening('lower_balcony_slider', 'bedroom_south', 'south', .5, 1.56, 'sliding_door')
    opening('kitchen_balcony_slider', 'bedroom_north', 'north', .65, 1.67, 'sliding_door')
    opening('outer_north_balcony_slider', 'bedroom_outer_north', 'east', .5, 2.0, 'sliding_door')
    opening('outer_south_balcony_slider', 'bedroom_outer_south', 'east', .5, 2.0, 'sliding_door')
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
    # Show the separately traced agreement room outlines, without presenting
    # the cropped main arc's completion as observed drawing evidence.
    plan['source_wall_segments'] = [
        {'id': f"agreement_{room['id']}_boundary_{index}", 'start': a, 'end': b,
         'kind': 'source_room_boundary', 'confidence': 'approximate manual agreement raster trace'}
        for room in source['rooms'] if room['id'] != 'balcony_curved'
        for index, (a, b) in enumerate(zip(room['polygon'], room['polygon'][1:] + room['polygon'][:1]))
    ]
    plan['source_footprint'] = deepcopy(source['footprint'])
    plan['footprint'] = {'polygon':[list(p) for p in list(footprint.exterior.coords)[:-1]],
                         'holes':[[list(p) for p in list(ring.coords)[:-1]] for ring in footprint.interiors],
                         'includes_balconies':True, 'modeled_gross_area_m2':footprint.area,
                         'confidence':'dimension-driven rooms; unmeasured connections/curve shape assumed'}
    plan['rooms'] = list(rooms.values())
    plan['wall_segments'], plan['openings'] = walls, openings
    plan['dimension_model'] = VERSION
    plan['coordinate_system'].update({'x': 'right in upright agreement drawing', 'y': 'up in upright agreement drawing',
                                      'origin': 'agreement crop pixel (42, 728); model clear spans and alignments reconstructed separately'})
    plan['dimension_note'] = '1 scene unit = 1 m. Agreement page 35 metric room spans govern this apartment. Wall thickness, heights, exact offsets and cropped main arc completion remain traceable assumptions.'
    room_dimensions = []
    for name, shape in shapes.items():
        x0, y0, x1, y1 = shape.bounds
        room = rooms[name]
        if room['dimension_mode'] == 'clear_rectangle':
            modeled = [x1-x0, y1-y0]
        elif room['span_axis'] == 1:
            modeled = [shape.area/(y1-y0), y1-y0]
        else:
            modeled = [x1-x0, shape.area/(x1-x0)]
        room_dimensions.append({'id': name, 'name': room['name'],
                                'printed': room['dimensions_m'], 'modeled': modeled,
                                'dimension_mode': room['dimension_mode'],
                                'basis': room['geometry_provenance']})
    source_shape = Polygon(source['footprint']['polygon'], source['footprint'].get('holes', []))
    bx0, by0, bx1, by1 = footprint.bounds
    sx0, sy0, sx1, sy1 = source_shape.bounds
    visible_source = unary_union([Polygon(room['source_polygon']) for room in rooms.values() if room['id'] != 'balcony_curved'])
    visible_model = unary_union([shape for name, shape in shapes.items() if name != 'balcony_curved'])
    vxs, vys, vxe, vye = visible_source.bounds
    mxs, mys, mxe, mye = visible_model.bounds
    arc_points = list(shapes['balcony_curved'].exterior.coords)[1:-4]
    modeled_arc_length = LineString(arc_points).length
    plan['scale_audit'] = {
        'units': 'm', 'meters_per_unit': 1,
        'room_dimensions': room_dimensions, 'gross_area_m2': footprint.area,
        'source_trace_gross_area_m2': source_shape.area,
        'scheduled_area_m2': deepcopy(source['area_schedule_m2']),
        'footprint_span_m': [bx1-bx0, by1-by0],
        'source_trace_span_m': [sx1-sx0, sy1-sy0],
        'source_trace_basis': source['footprint']['provenance'],
        'visible_agreement_span_m': [vxe-vxs, vye-vys],
        'modeled_visible_span_m': [mxe-mxs, mye-mys],
        'main_outer_arc_length_m': modeled_arc_length,
        'room_registration_offsets_m': [{
            'id': name,
            'center_offset_xy_m': [shape.centroid.x-Polygon(rooms[name]['source_polygon']).centroid.x,
                                   shape.centroid.y-Polygon(rooms[name]['source_polygon']).centroid.y],
            'basis': 'difference from approximate agreement raster registration; exact offsets are not dimensioned'}
            for name, shape in shapes.items() if name != 'balcony_curved'],
        'notes': ['Agreement printed rectangular clear spans and balcony span/average depth are enforced; source registration is approximate.',
                  'Modeled gross slab area, raster footprint area and printed RERA net-area schedule use different boundaries; discrepancies require review.',
                  'Balcony average depth is interpreted as area divided by its labeled span; the source contour, facade alignment and this interpretation remain provisional.',
                  'The main agreement outer arc is cropped; its completed contour is inferred from the approved comparison drawing and may change footprint width.',
                  'Visible agreement spans and per-room registration offsets expose the change caused by orthogonal reconstruction; do not treat the inferred perimeter as as-built.',
                  'Wall thickness, ceiling height, opening widths/heights and offsets are estimates. No global scaling is applied.']}
    plan['reconstruction_decisions'] = [
        {'id': 'construction_defaults', 'kind': 'assumption',
         'summary': 'Use orthogonal room alignment, 0.15 m partitions and the existing ceiling-height estimate.',
         'basis': 'Printed room dimensions constrain clear spaces; wall build-up, height and exact alignments are not dimensioned.',
         'parameters': {'partition_thickness_m': t, 'room_height_m': plan['room_height_m'], 'orthogonal_alignment': True},
         'status': 'needs-review'},
        *[{'id': name+'_profile', 'kind': 'source-adaptation',
           'summary': 'Source balcony contour adapted to inferred orthogonal facade; exact curve unmeasured.',
           'basis': ('Agreement printed span and average depth; cropped main arc completed from approved comparison prior' if name == 'balcony_curved'
                     else 'Agreement lower-balcony contour, printed span and average depth')+'; profile registration and area/span interpretation need review.',
           'parameters': parameters, 'status': 'needs-review'} for name, parameters in profile_parameters.items()],
        {'id': 'main_arc_completion', 'kind': 'inferred',
         'summary': 'Complete the cropped main agreement balcony arc using the approved comparison contour as a shape prior.',
         'basis': 'Agreement page 35 facade/endpoints and 2.40 m average depth by 11.07 m span; its outer mid-arc is outside the photo. Approved B1-Building-3.pdf contour supplies only an inferred profile.',
         'parameters': {'primary_file': 'Miami PWC House Documents.pdf', 'primary_page': 35,
                        'shape_prior_file': 'B1-Building-3.pdf', 'shape_prior_page': 1,
                        'registered_pixel_span': [86, 373], 'modeled_outer_arc_length_m': modeled_arc_length,
                        'other_floor_comparison_arc_m': 12.57,
                        'other_floor_comparison_file': 'B1-Building-4.pdf',
                        'other_floor_comparison_basis': 'Refuge sheet 64/69; corroboration only, excluded from floor 15 geometry',
                        'comparison_arc_difference_m': modeled_arc_length-12.57,
                        'boundary_status': 'inferred completion, not a fully visible agreement perimeter'},
         'status': 'needs-review'},
        {'id': 'agreement_source_selection', 'kind': 'source-selection',
         'summary': 'Use the demarcated agreement B1-1502 apartment, including its powder room and direct bedroom-to-toilet D.',
         'basis': 'Miami PWC House Documents.pdf page 35 labels the highlighted apartment B1-1502. Approved drawing and furnished brochure are separate comparisons.',
         'parameters': {'metric_source_file': 'Miami PWC House Documents.pdf', 'metric_source_page': 35,
                        'approximate_mandir_width_m': 1.77, 'entry_label_overlap_m': .01,
                        'lower_balcony_average_m': 2.45, 'clipboard_alternative_average_m': 2.46},
         'status': 'needs-review'},
        {'id': 'door_assemblies', 'kind': 'assumption',
         'summary': 'Keep source-backed connections while estimating opening width, height and offset; retain the unmarked walk-in gap as open access.',
         'basis': 'D/SD symbols and visible boundary gaps establish topology. Per-opening provenance records evidence and estimated parameters.',
         'parameters': {'opening_height_m': 2.2, 'placement': 'assumed fractional offset on dimensioned boundary',
                        'outer_bedroom_slider_width_m': 2.0, 'walk_in_access': 'opening without hinged leaf'},
         'status': 'needs-review'},
        {'id': 'north_circulation_wall_repair', 'kind': 'geometry-repair',
         'summary': 'Keep the north circulation clear area inside its sidewalls so bedroom door jambs attach to masonry.',
         'basis': 'Source bedroom boundary and D symbol require a partition around the doorway; previous circulation subtraction erased the sidewalls.',
         'parameters': {'clear_bounds_m': list(circulation.bounds), 'partition_thickness_m': t},
         'status': 'needs-review'},
        {'id': 'scale_reconciliation', 'kind': 'review',
         'summary': 'Expose modeled gross geometry and source area/span differences instead of silently resizing the plan.',
         'basis': 'The printed RERA schedule is not a gross slab specification; reconstructed orthogonal alignment and balcony interpretation change outer extent.',
         'parameters': {'modeled_gross_area_m2': footprint.area, 'source_trace_gross_area_m2': source_shape.area,
                        'scheduled_total_area_m2': source['area_schedule_m2']['total'],
                        'footprint_span_m': [bx1-bx0, by1-by0],
                        'source_trace_span_m': [sx1-sx0, sy1-sy0]},
         'status': 'needs-review'},
    ]
    if plan.get('asset_placements'):
        # Legacy placements are in the input geometry, not agreement raster coordinates.
        relocation_rooms = [dict(room, source_polygon=approved_rooms[room['id']]['polygon'])
                            for room in plan['rooms'] if room['id'] in approved_rooms]
        plan['asset_placements'] = relocate_assets(plan['asset_placements'], relocation_rooms)
    return plan
