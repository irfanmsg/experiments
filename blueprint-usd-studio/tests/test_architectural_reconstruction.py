"""Check connections and evidence, rather than accepting plausible-looking rooms."""
import json
from pathlib import Path

import pytest
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

from app.dimensioned_b1 import build_dimensioned_plan
from app.geometry import validate_plan


ROOT = Path(__file__).parents[1]


def reconstructed():
    source = json.loads((ROOT / 'data/b1_1502/raster_trace.json').read_text())
    return source, build_dimensioned_plan(source)


def walls(plan):
    return unary_union([
        LineString([wall['start'], wall['end']]).buffer(wall['thickness_m'] / 2, cap_style=2)
        for wall in plan['wall_segments'] if wall['kind'] != 'balcony_guard'
    ])


def test_door_frames_join_masonry_without_blocking_the_opening(tmp_path):
    from pxr import Usd, UsdGeom
    from app.usd_builder import build_usd

    _, plan = reconstructed()
    masonry = walls(plan)
    for opening in plan['openings']:
        if opening.get('no_header'):
            continue
        for end in ('start', 'end'):
            assert Point(opening[end]).distance(masonry) < 1e-6, (opening['id'], end)
        assert not masonry.contains(Point(opening['center'])), opening['id']
    bedroom = next(room for room in plan['rooms'] if room['id'] == 'bedroom_north')
    bedroom_bounds = Polygon(bedroom['polygon']).bounds
    assert masonry.covers(Point(bedroom_bounds[2] + .075, bedroom_bounds[3] - .25))
    destination = tmp_path / 'connections.usda'
    build_usd(plan, destination)
    stage = Usd.Stage.Open(str(destination))
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render'])
    exported_walls, jambs = [], []
    for prim in stage.Traverse():
        path = str(prim.GetPath())
        if prim.GetTypeName() != 'Cube':
            continue
        bounds = cache.ComputeWorldBound(prim).ComputeAlignedBox()
        low, high = bounds.GetMin(), bounds.GetMax()
        if not low[2] < 1 < high[2]:
            continue
        shape = box(low[0], low[1], high[0], high[1])
        if path.startswith('/World/Building/Walls/') and '_guard_' not in path:
            exported_walls.append(shape)
        elif path.startswith('/World/Building/Openings/') and prim.GetName() in {'Piece_001', 'Piece_002'}:
            jambs.append((path, shape))
    masonry = unary_union(exported_walls)
    assert jambs
    for path, jamb in jambs:
        assert jamb.distance(masonry) < 1e-6, path
    footprint = Polygon(plan['footprint']['polygon'], plan['footprint'].get('holes', []))
    clear = footprint.difference(unary_union([masonry, *[shape for _, shape in jambs]]))
    components = list(clear.geoms) if hasattr(clear, 'geoms') else [clear]
    entry = Polygon(next(room for room in plan['rooms'] if room['id'] == 'entry')['polygon'])
    reachable = next(component for component in components if component.covers(entry.representative_point()))
    for room in plan['rooms']:
        assert reachable.covers(Polygon(room['polygon']).representative_point()), room['id']


def test_source_bathroom_routes_and_east_sliders_are_open():
    _, plan = reconstructed()
    openings = {opening['id']: opening for opening in plan['openings']}
    expected = {
        'service_wc_door': {'service_wc', 'service_room'},
        'north_toilet_door': {'bathroom_north', 'bedroom_north'},
        'powder_room_door': {'powder_room', 'north_circulation'},
        'outer_north_bedroom_door': {'bedroom_outer_north', 'north_circulation'},
        'outer_north_toilet_door': {'bathroom_outer_north', 'bedroom_outer_north'},
        'south_toilet_door': {'bathroom_south', 'bedroom_south'},
        'outer_south_toilet_door': {'bathroom_outer_south', 'walk_in'},
        'walk_in_door': {'walk_in', 'bedroom_outer_south'},
        'outer_north_balcony_slider': {'bedroom_outer_north', 'balcony_curved'},
        'outer_south_balcony_slider': {'bedroom_outer_south', 'balcony_curved'},
    }
    masonry = walls(plan)
    for identifier, connects in expected.items():
        opening = openings[identifier]
        assert set(opening['connects']) == connects
        assert opening['provenance']['topology'] == 'source-derived'
        a, b = opening['start'], opening['end']
        length = LineString([a, b]).length
        normal = (-(b[1] - a[1]) / length, (b[0] - a[0]) / length)
        center = opening['center']
        route = LineString([
            [center[i] + sign * normal[i] * .11 for i in (0, 1)] for sign in (-1, 1)
        ]).buffer(.2, cap_style=2)
        assert route.intersection(masonry).area < 1e-8, identifier
    assert openings['walk_in_door']['type'] == 'opening'


def test_source_contours_and_printed_dimensions_remain_distinct():
    source, plan = reconstructed()
    assert not validate_plan(plan)
    rooms = {room['id']: room for room in plan['rooms']}
    assert plan['dimension_model'] == 'b1-agreement-dimensions-v3'
    assert plan['source']['primary_crop'] == 'agreement_unit_crop.jpg'
    assert plan['source']['page'] == 35 and plan['image_size'] == [546, 810]
    assert rooms['bathroom_north']['dimensions_m'] == [1.38, 2.46]
    assert rooms['powder_room']['dimensions_m'] == [1.38, 1.38]
    assert rooms['bathroom_outer_south']['dimensions_m'] == [2.43, 1.52]
    assert rooms['passage']['dimensions_m'] == [1.77, 2.00]
    assert rooms['passage']['name'] == 'Mandir'
    assert rooms['wfh']['name'] == 'Theatre / den'
    assert build_dimensioned_plan(plan)['footprint']['polygon'] == plan['footprint']['polygon']
    for room in rooms.values():
        assert 'agreement' in room['dimension_provenance']
        if room['category'] == 'balcony' and room['dimension_mode'] == 'average_depth':
            assert len(room['polygon']) == len(room['source_polygon'])
            assert 'source contour' in room['geometry_provenance']
    # Preserve the traced lower terrace's clipped corner, rather than inventing a rectangle.
    assert len(rooms['balcony_south']['polygon']) == 4
    footprint = Polygon(plan['footprint']['polygon'], plan['footprint'].get('holes', []))
    for identifier in ('living_balcony_slider', 'outer_north_balcony_slider', 'outer_south_balcony_slider'):
        opening = next(o for o in plan['openings'] if o['id'] == identifier)
        assert footprint.buffer(1e-8).covers(Point(opening['center']))


def test_synthesized_parameters_have_reviewable_evidence_and_scale():
    source, plan = reconstructed()
    for opening in plan['openings']:
        trace = opening['provenance']
        assert trace['topology'] in {'source-derived', 'inferred'}
        assert trace['basis'] and trace['source_reference']
        assert trace['width'] in {'scan estimate', 'assumed', 'printed'}
        assert trace['height'] == 'assumed'
        assert trace['placement'] and trace['review_status'] == 'needs-review'
        assert trace['source_reference']['file'] == 'Miami PWC House Documents.pdf'
        assert trace['source_reference']['page'] == 35
        assert trace['source_reference']['image'] == 'agreement_unit_crop.jpg'
        assert trace['source_reference']['image_coordinates_px']
        for x, y in trace['source_reference']['image_coordinates_px'].values():
            assert 0 <= x < 546 and 0 <= y < 810
        assert len(opening['connects']) == 2
    assert any(o.get('no_header') for o in plan['openings'])
    decisions = {decision['id']: decision for decision in plan['reconstruction_decisions']}
    assert {'construction_defaults', 'balcony_curved_profile', 'balcony_south_profile', 'door_assemblies',
            'north_circulation_wall_repair', 'scale_reconciliation', 'main_arc_completion'} <= decisions.keys()
    assert all(decision['status'] == 'needs-review' and decision['basis'] for decision in decisions.values())
    audit = plan['scale_audit']
    assert audit['units'] == 'm' and audit['meters_per_unit'] == 1
    assert audit['scheduled_area_m2'] == source['area_schedule_m2']
    assert audit['gross_area_m2'] == pytest.approx(
        Polygon(plan['footprint']['polygon'], plan['footprint'].get('holes', [])).area)
    assert len(audit['room_dimensions']) == len(plan['rooms'])
    assert audit['notes'] and audit['source_trace_span_m'] and audit['footprint_span_m']
    old = Polygon(next(room for room in source['rooms'] if room['id'] == 'living_dining')['polygon']).bounds
    source['asset_placements'] = [{'id': 'retained', 'position': [(old[0]+old[2])/2, (old[1]+old[3])/2, .6], 'rotation_z_deg': 20}]
    relocated = build_dimensioned_plan(source)
    room = Polygon(next(room for room in relocated['rooms'] if room['id'] == 'living_dining')['polygon'])
    placement = relocated['asset_placements'][0]
    assert placement['position'] == pytest.approx([room.centroid.x, room.centroid.y, .6])
    assert placement['rotation_z_deg'] == 20


def test_scale_audit_remeasures_edited_registration_span_and_balcony_arc():
    from copy import deepcopy
    from app.geometry import measured_scale_audit

    _, plan = reconstructed()
    initial = deepcopy(plan['scale_audit'])
    rooms = {room['id']: room for room in plan['rooms']}
    rooms['service_wc']['polygon'] = [[x-1, y] for x, y in rooms['service_wc']['polygon']]
    balcony = rooms['balcony_curved']
    balcony['polygon'] = [[x*1.1, y*1.1] for x, y in balcony['polygon']]
    audit = measured_scale_audit(plan)
    offsets = {row['id']: row['center_offset_xy_m'] for row in audit['room_registration_offsets_m']}
    original = next(row['center_offset_xy_m'] for row in initial['room_registration_offsets_m'] if row['id'] == 'service_wc')
    assert offsets['service_wc'] == pytest.approx([original[0]-1, original[1]])
    assert audit['modeled_visible_span_m'] == pytest.approx([
        initial['modeled_visible_span_m'][0]+1, initial['modeled_visible_span_m'][1]])
    assert audit['main_outer_arc_length_m'] == pytest.approx(initial['main_outer_arc_length_m']*1.1)
    for key in ('source_trace_gross_area_m2', 'source_trace_span_m', 'visible_agreement_span_m', 'scheduled_area_m2'):
        assert audit[key] == initial[key]
        assert key in audit['static_source_evidence_fields']
    assert plan['scale_audit'] == initial
