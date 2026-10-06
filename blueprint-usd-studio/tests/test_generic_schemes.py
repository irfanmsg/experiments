"""Design schemes respect unrelated room geometry and skip unsafe placements."""
import copy
import json

import pytest
from pxr import Gf, Usd, UsdGeom, UsdLux
from shapely.geometry import LineString, Polygon, box

from app.usd_builder import INTERIOR_SCHEMES, build_style_variants, build_usd


def test_all_schemes_dress_an_unrelated_concave_home_without_changing_scale(tmp_path):
    plan = {'name': 'Courtyard home', 'structure_type': 'home', 'units': 'm',
            'room_height_m': 2.9, 'rooms': [
                {'id': 'family-42', 'category': 'living', 'polygon':
                 [[20, 10], [27, 10], [27, 13], [24, 13], [24, 16], [20, 16]]},
                {'id': 'sleep-west', 'category': 'bedroom', 'polygon':
                 [[28, 10], [32, 10], [32, 14], [28, 14]]}],
            'openings': [{'id': 'entry', 'type': 'door', 'start': [20, 12],
                          'end': [20, 13], 'space_id': 'family-42', 'width_m': 1.0}]}
    before = copy.deepcopy(plan)
    report = build_style_variants(plan, tmp_path)
    assert set(INTERIOR_SCHEMES) <= report['styles'].keys()
    assert 'home_specification' not in report['styles']
    rooms = {room['id']: Polygon(room['polygon']) for room in plan['rooms']}
    signatures = set()
    for style in INTERIOR_SCHEMES:
        result = report['styles'][style]
        stage = Usd.Stage.Open(result['usd_path'])
        assert UsdGeom.GetStageMetersPerUnit(stage) == 1
        assert result['bounds_m'] == [20, 10, 32, 16]
        assert result['asset_imports'] == []
        assert json.loads(stage.GetDefaultPrim().GetCustomDataByKey('libraryTrace')) == result['runtime_trace']
        actions = {action['id']: action for action in result['runtime_trace']['actions']}
        assert actions['usd_authoring']['status'] == 'executed'
        assert actions['asset_import']['observed_calls'] == 0
        assert actions['physics_step']['observed_calls'] == 0
        assert not any(p.GetCustomDataByKey('assumedFixture') for p in stage.Traverse())
        decor = [p for p in stage.Traverse() if p.GetCustomDataByKey('interiorDecor')]
        assert {'rug', 'lamp', 'plant'} <= {p.GetCustomDataByKey('decorType') for p in decor}
        cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render'])
        for prim in decor:
            bounds = cache.ComputeWorldBound(prim).ComputeAlignedBox()
            low, high = bounds.GetMin(), bounds.GetMax()
            footprint = box(low[0], low[1], high[0], high[1])
            assert rooms[prim.GetCustomDataByKey('roomId')].covers(footprint)
            assert not footprint.intersects(LineString([[20, 12], [20, 13]]).buffer(.55))
            assert 0 <= low[2] < high[2] <= 2.9
            assert 'assumed' in prim.GetCustomDataByKey('provenance').lower()
        assert any(p.HasAPI(UsdLux.LightAPI) for p in Usd.PrimRange(stage.GetPrimAtPath('/World/Interiors')))
        decisions = result['presentation_decisions']
        assert json.loads(stage.GetDefaultPrim().GetCustomDataByKey('presentationDecisions')) == decisions
        assert any(d.get('parameters', {}).get('placement_basis') for d in decisions)
        signatures.add(tuple((str(p.GetPath()), p.GetTypeName()) for p in Usd.PrimRange(stage.GetPrimAtPath('/World/Interiors'))))
    assert len(signatures) == 5
    assert plan == before


@pytest.mark.parametrize('rooms', [[], [{'id': 'narrow', 'polygon': [[0, 0], [.2, 0], [.2, 3], [0, 3]]}]])
def test_sparse_plan_keeps_scheme_and_records_skipped_decor(tmp_path, rooms):
    plan = {'structure_type': 'home', 'rooms': rooms,
            'footprint': {'polygon': [[0, 0], [.2, 0], [.2, 3], [0, 3]]}}
    for style in INTERIOR_SCHEMES:
        report = build_usd(plan, tmp_path / (style+'.usda'), style)
        stage = Usd.Stage.Open(report['usd_path'])
        assert stage.GetDefaultPrim().GetCustomDataByKey('isDesignScheme')
        assert not any(p.GetCustomDataByKey('interiorDecor') for p in stage.Traverse())
        assert any(d['status'] == 'not-placed' for d in report['presentation_decisions'])


def test_specified_finishes_still_require_the_b1_reference(tmp_path):
    with pytest.raises(ValueError, match='demarcated agreement reference'):
        build_usd({'rooms': []}, tmp_path / 'specified.usda', 'home_specification')


def test_generic_decor_avoids_assets_and_voids_and_preserves_asset_metres(tmp_path, monkeypatch):
    monkeypatch.setenv('BLUEPRINT_STUDIO_ASSET_ROOT', str(tmp_path))
    asset_path = tmp_path / 'table.usda'
    asset = Usd.Stage.CreateNew(str(asset_path))
    UsdGeom.SetStageMetersPerUnit(asset, .01)
    UsdGeom.SetStageUpAxis(asset, 'Z')
    cube = UsdGeom.Cube.Define(asset, '/Table')
    cube.CreateSizeAttr(1)
    UsdGeom.Xformable(cube).AddScaleOp().Set(Gf.Vec3f(200, 150, 80))
    asset.SetDefaultPrim(cube.GetPrim())
    asset.GetRootLayer().Save()
    polygon = [[0, 0], [7, 0], [7, 7], [0, 7]]
    plan = {'rooms': [{'id': 'lounge', 'polygon': polygon}],
            'footprint': {'polygon': polygon, 'holes': [[[1, 1], [3, 1], [3, 3], [1, 3]]]},
            'asset_placements': [{'id': 'my_table', 'asset_path': str(asset_path),
                                  'position': [3.5, 3.5, 0], 'rotation_deg': 25}]}
    result = build_usd(plan, tmp_path / 'dressed.usda', 'bohemian')
    stage = Usd.Stage.Open(result['usd_path'])
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render'])
    furniture = cache.ComputeWorldBound(stage.GetPrimAtPath('/World/Assets/my_table')).ComputeAlignedBox()
    furniture_xy = box(*list(furniture.GetMin())[:2], *list(furniture.GetMax())[:2])
    assert result['asset_imports'][0]['size_xyz_m'] == pytest.approx([2, 1.5, .8])
    assert next(action for action in result['runtime_trace']['actions'] if action['id'] == 'asset_import')['status'] == 'executed'
    assert furniture.GetMin()[2] == pytest.approx(0)
    decor = [p for p in stage.Traverse() if p.GetCustomDataByKey('interiorDecor')]
    assert decor
    footprints = []
    for prim in decor:
        bounds = cache.ComputeWorldBound(prim).ComputeAlignedBox()
        shape = box(*list(bounds.GetMin())[:2], *list(bounds.GetMax())[:2])
        assert not shape.intersects(furniture_xy)
        assert not shape.intersects(box(1, 1, 3, 3))
        assert all(not shape.intersects(other) for other in footprints)
        footprints.append(shape)
