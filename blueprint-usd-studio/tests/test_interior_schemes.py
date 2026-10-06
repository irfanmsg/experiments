"""Saved design cues dress the home without changing its measured construction."""
import json
from pathlib import Path

import pytest
from pxr import Usd, UsdGeom, UsdLux
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from app.asset_library import b1_starter_furniture
from app.usd_builder import INTERIOR_SCHEMES, PALETTES, build_usd


@pytest.mark.parametrize('style,removed', [('saved_linen_timber', 'living_dining'),
                                         ('saved_botanical_cane', 'wfh'),
                                         ('saved_linen_timber', 'bedroom_north')])
def test_deleted_scheme_rooms_fail_before_overwriting_an_export(tmp_path, style, removed):
    plan = json.loads((Path(__file__).parents[1] / 'data/b1_1502/plan.json').read_text())
    plan['rooms'] = [room for room in plan['rooms'] if room['id'] != removed]
    output = tmp_path / 'existing.usda'
    output.write_text('previous export')
    with pytest.raises(ValueError, match='Restore those rooms or choose a finish preset'):
        build_usd(plan, output, style)
    assert output.read_text() == 'previous export'


def test_reference_schemes_preserve_scale_and_add_real_dressing_and_lights(tmp_path):
    plan = json.loads((Path(__file__).parents[1] / 'data/b1_1502/plan.json').read_text())
    plan['asset_placements'] = b1_starter_furniture(plan)
    baseline = build_usd(plan, tmp_path / 'baseline.usda', 'home_specification')
    original = Usd.Stage.Open(baseline['usd_path'])
    rooms = {room['id']: Polygon(room['polygon']) for room in plan['rooms']}
    doors = unary_union([LineString([o['start'], o['end']]).buffer(.55, cap_style=2) for o in plan['openings']])
    signatures = set()
    assert {'indian_contemporary', 'bohemian'} <= INTERIOR_SCHEMES.keys()
    assert len(INTERIOR_SCHEMES) == 5
    for name in INTERIOR_SCHEMES:
        report = build_usd(plan, tmp_path / (name+'.usda'), name)
        stage = Usd.Stage.Open(report['usd_path'])
        assert UsdGeom.GetStageMetersPerUnit(stage) == 1 and UsdGeom.GetStageUpAxis(stage) == 'Z'
        assert report['asset_imports'] == baseline['asset_imports']
        assert PALETTES[name]['is_design_scheme'] and not PALETTES[name]['requires_reference']
        assert PALETTES[name]['reference_urls']
        for room in plan['rooms']:
            path = '/World/Spaces/'+room['id']
            assert stage.GetPrimAtPath(path).GetCustomDataByKey('floorFinish') == original.GetPrimAtPath(path).GetCustomDataByKey('floorFinish')
            assert UsdGeom.Mesh(stage.GetPrimAtPath(path+'/Floor')).GetPointsAttr().Get() == UsdGeom.Mesh(original.GetPrimAtPath(path+'/Floor')).GetPointsAttr().Get()
        fixtures = [(str(p.GetPath()), p.GetCustomDataByKey('fixtureType')) for p in stage.Traverse() if p.GetCustomDataByKey('assumedFixture')]
        assert fixtures == [(str(p.GetPath()), p.GetCustomDataByKey('fixtureType')) for p in original.Traverse() if p.GetCustomDataByKey('assumedFixture')]
        decor = [p for p in stage.Traverse() if p.GetCustomDataByKey('interiorDecor')]
        kinds = {p.GetCustomDataByKey('decorType') for p in decor}
        assert {'rug', 'curtains', 'art', 'plant', 'lamp', 'media_console', 'book_accents', 'cushions'} <= kinds
        cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render'])
        original_cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render'])
        furniture_footprints = []
        for asset in plan['asset_placements']:
            path = '/World/Assets/'+asset['id']
            actual = cache.ComputeWorldBound(stage.GetPrimAtPath(path)).ComputeAlignedBox()
            expected = original_cache.ComputeWorldBound(original.GetPrimAtPath(path)).ComputeAlignedBox()
            assert list(actual.GetMin()) == pytest.approx(list(expected.GetMin()), abs=1e-7)
            assert list(actual.GetMax()) == pytest.approx(list(expected.GetMax()), abs=1e-7)
            low, high = actual.GetMin(), actual.GetMax()
            furniture_footprints.append(box(low[0], low[1], high[0], high[1]))
        for prim in decor:
            bound = cache.ComputeWorldBound(prim).ComputeAlignedBox()
            low, high = bound.GetMin(), bound.GetMax()
            footprint = box(low[0], low[1], high[0], high[1])
            if prim.GetCustomDataByKey('clearanceRole') == 'floor':
                assert rooms[prim.GetCustomDataByKey('roomId')].buffer(1e-6).covers(footprint), prim.GetPath()
                assert footprint.intersection(doors).area < 1e-7, prim.GetPath()
                if prim.GetCustomDataByKey('decorType') != 'rug':
                    assert all(footprint.intersection(furniture).area < 1e-7 for furniture in furniture_footprints), prim.GetPath()
            assert 'assumed' in prim.GetCustomDataByKey('provenance')
        lights = [p for p in Usd.PrimRange(stage.GetPrimAtPath('/World/Interiors')) if p.HasAPI(UsdLux.LightAPI)]
        assert len(lights) >= 2 and all(UsdLux.LightAPI(p).GetIntensityAttr().Get() > 0 for p in lights)
        ceiling = stage.GetPrimAtPath('/World/Interiors/Ceilings/living_dining')
        mesh = UsdGeom.Mesh(ceiling)
        assert ceiling and not mesh.GetDoubleSidedAttr().Get()
        assert all(point[2] == pytest.approx(plan['room_height_m']) for point in mesh.GetPointsAttr().Get())
        decisions = report['presentation_decisions']
        assert any(d.get('source', {}).get('url') in PALETTES[name]['reference_urls'] for d in decisions)
        assert json.loads(stage.GetDefaultPrim().GetCustomDataByKey('presentationDecisions')) == decisions
        assert stage.GetDefaultPrim().GetCustomDataByKey('isDesignScheme')
        assert not any(d.get('status') == 'not-placed' and d.get('interior_scheme') == name for d in decisions)
        signatures.add(tuple((str(p.GetPath()), p.GetTypeName()) for p in Usd.PrimRange(stage.GetPrimAtPath('/World/Interiors'))))
    assert len(signatures) == len(INTERIOR_SCHEMES)
