import json
from pathlib import Path

import pytest
from pxr import Gf, Usd, UsdGeom, UsdShade
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from app.usd_builder import build_usd, build_style_variants


def test_unrelated_home_does_not_export_b1_finish_preset(tmp_path):
    plan = {'name': 'Uploaded home', 'units': 'm', 'structure_type': 'home',
            'footprint': {'polygon': [[0, 0], [4, 0], [4, 3], [0, 3]]},
            'rooms': [], 'wall_segments': [], 'openings': [], 'asset_placements': []}
    report = build_style_variants(plan, tmp_path)
    assert 'home_specification' not in report['styles']
    assert next(iter(report['styles'])) == 'contemporary'
    with pytest.raises(ValueError, match='require the demarcated agreement'):
        build_usd(plan, tmp_path / 'unrelated.usda', 'home_specification')


def test_specified_home_has_measured_fixtures_clear_doors_and_traceable_finishes(tmp_path):
    plan = json.loads((Path(__file__).parents[1] / 'data/b1_1502/plan.json').read_text())
    report = build_usd(plan, tmp_path / 'home.usda', 'home_specification')
    stage = Usd.Stage.Open(str(tmp_path / 'home.usda'))
    rooms = {room['id']: room for room in plan['rooms']}
    doors = unary_union([
        LineString([opening['start'], opening['end']]).buffer(.55, cap_style=2)
        for opening in plan['openings']
    ])
    transforms = UsdGeom.XformCache()
    leaf_shapes = []
    for prim in stage.Traverse():
        if prim.GetName() != 'Leaf' or not prim.IsA(UsdGeom.Cube):
            continue
        transform = transforms.GetLocalToWorldTransform(prim)
        half = UsdGeom.Cube(prim).GetSizeAttr().Get()/2
        corners = [transform.Transform(Gf.Vec3d(x*half, y*half, 0))
                   for x, y in [(-1, -1), (1, -1), (1, 1), (-1, 1)]]
        leaf_shapes.append(Polygon([(point[0], point[1]) for point in corners]))
    doors = unary_union([doors, *leaf_shapes])
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render'])
    fixtures = [prim for prim in stage.Traverse() if prim.GetCustomDataByKey('assumedFixture')]
    assert fixtures
    occupied = {}
    beds, wardrobes, toilets = set(), set(), set()
    for prim in fixtures:
        room_id = prim.GetCustomDataByKey('roomId')
        kind = prim.GetCustomDataByKey('fixtureType')
        bounds = cache.ComputeWorldBound(prim).ComputeAlignedBox()
        low, high = bounds.GetMin(), bounds.GetMax()
        footprint = box(low[0], low[1], high[0], high[1])
        assert Polygon(rooms[room_id]['polygon']).buffer(1e-6).covers(footprint), prim.GetPath()
        assert footprint.intersection(doors).area < 1e-7, prim.GetPath()
        for other_kind, other in occupied.get(room_id, []):
            assert footprint.intersection(other).area < 1e-7, prim.GetPath()
            if rooms[room_id]['category'] == 'bedroom' and {kind, other_kind} == {'bed', 'wardrobe'}:
                assert footprint.distance(other) >= .60-1e-6, prim.GetPath()
        occupied.setdefault(room_id, []).append((kind, footprint))
        assert 'assumed' in prim.GetCustomDataByKey('provenance').lower()
        if kind == 'bed':
            beds.add(room_id)
            assert sorted([high[0]-low[0], high[1]-low[1]]) == pytest.approx([1.72, 2.14], abs=1e-6)
            assert prim.GetChild('Mattress') and prim.GetChild('Pillow_0')
        elif kind == 'wardrobe':
            wardrobes.add(room_id)
        elif kind == 'wc':
            toilets.add(room_id)
            assert prim.GetChild('Bowl') and prim.GetChild('Cistern')
    bedrooms = {room_id for room_id, room in rooms.items() if room['category'] == 'bedroom'}
    assert beds == bedrooms
    assert bedrooms <= wardrobes
    assert {'service_wc', 'bathroom_north', 'bathroom_outer_north', 'bathroom_south', 'bathroom_outer_south'} <= toilets
    for room_id, room in rooms.items():
        prim = stage.GetPrimAtPath('/World/Spaces/' + room_id)
        finish = prim.GetCustomDataByKey('floorFinish')
        if room_id == 'bedroom_outer_south':
            assert finish == 'wood'
            material, _ = UsdShade.MaterialBindingAPI(prim.GetChild('Floor')).ComputeBoundMaterial()
            assert material.GetPrim().GetName() == 'specified_wood'
        else:
            assert finish != 'wood'
        if room['category'] == 'bathroom' or room_id == 'powder_room':
            dado = prim.GetChild('CeramicDado')
            assert dado and dado.GetCustomDataByKey('heightM') == pytest.approx(2.1336)
            assert stage.GetPrimAtPath('/World/Fixtures/'+room_id+'/WC')
            assert stage.GetPrimAtPath('/World/Fixtures/'+room_id+'/Washbasin')
            if room_id not in {'service_wc', 'powder_room'}:
                assert stage.GetPrimAtPath('/World/Fixtures/'+room_id+'/Shower')
    kitchen = stage.GetPrimAtPath('/World/Fixtures/kitchen')
    names = {prim.GetName() for prim in Usd.PrimRange(kitchen)}
    assert {'Hob', 'Chimney', 'Sink', 'Counter', 'Cabinet_0'} <= names
    for opening in plan['openings']:
        if opening['type'] == 'sliding_door':
            prim = stage.GetPrimAtPath('/World/Building/Openings/' + opening['id'])
            assert prim.GetCustomDataByKey('frameFinish') == 'aluminium'
            material, _ = UsdShade.MaterialBindingAPI(prim.GetChild('Piece_001')).ComputeBoundMaterial()
            assert material.GetPrim().GetName() == 'metal'
    decisions = json.loads(stage.GetDefaultPrim().GetCustomDataByKey('presentationDecisions'))
    assert decisions == report['presentation_decisions']
    assert any(d.get('source', {}).get('pdf_page') == 28 and d['kind'] == 'source-specified' for d in decisions)
    assert any(d['kind'] == 'assumed' and d.get('parameters', {}).get('tile_size_m') == [.6, 1.2] for d in decisions)
    build_usd(plan, tmp_path / 'classic.usda', 'classic')
    classic = Usd.Stage.Open(str(tmp_path / 'classic.usda'))
    assert [(str(prim.GetPath()), prim.GetCustomDataByKey('fixtureType')) for prim in fixtures] == [
        (str(prim.GetPath()), prim.GetCustomDataByKey('fixtureType'))
        for prim in classic.Traverse() if prim.GetCustomDataByKey('assumedFixture')
    ]
    for room_id in rooms:
        path = '/World/Spaces/' + room_id
        assert classic.GetPrimAtPath(path).GetCustomDataByKey('floorFinish') == stage.GetPrimAtPath(path).GetCustomDataByKey('floorFinish')
