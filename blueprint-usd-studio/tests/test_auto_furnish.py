import copy

import pytest
from pxr import Gf, Usd, UsdGeom
from shapely.geometry import LineString, Polygon, box

from app.auto_furnish import furniture_layout
from app.usd_builder import build_usd


@pytest.fixture(autouse=True)
def configured_library(tmp_path, monkeypatch):
    monkeypatch.setenv('BLUEPRINT_STUDIO_ASSET_ROOT', str(tmp_path))


def catalog_asset(tmp_path, name, size, structure='home', offset=(0, 0, 0), axis='Z'):
    path = tmp_path / (name.replace(' ', '_')+'.usda')
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageMetersPerUnit(stage, .01)
    UsdGeom.SetStageUpAxis(stage, axis)
    shape = UsdGeom.Cube.Define(stage, '/Model')
    shape.CreateSizeAttr(1)
    xf = UsdGeom.Xformable(shape)
    xf.AddTranslateOp().Set(Gf.Vec3d(*(n/.01 for n in offset)))
    source_size = [size[0], size[2], size[1]] if axis == 'Y' else size
    xf.AddScaleOp().Set(Gf.Vec3f(*(n/.01 for n in source_size)))
    stage.SetDefaultPrim(shape.GetPrim())
    stage.GetRootLayer().Save()
    return {'name':name, 'category':'Imported', 'usd_path':str(path), 'size_xyz_m':size,
            'structure_types':[structure], 'asset_kind':'Imported USD (SimReady not verified)'}


def plan_for(category='living', structure='home', size=8):
    poly = [[0, 0], [size, 0], [size, size], [0, size]]
    return {'units':'m', 'structure_type':structure, 'room_height_m':3,
            'rooms':[{'id':'space', 'category':category, 'name':category, 'polygon':poly}],
            'footprint':{'polygon':poly}, 'asset_placements':[]}


@pytest.mark.parametrize('axis', ['Y', 'Z'])
def test_suggestions_preserve_real_size_and_compensate_source_pivot(tmp_path, monkeypatch, axis):
    monkeypatch.setenv('BLUEPRINT_STUDIO_ASSET_ROOT', str(tmp_path))
    asset = catalog_asset(tmp_path, 'Sofa', [2, 1, 1], offset=(4, 5, 6), axis=axis)
    plan = plan_for()
    before = copy.deepcopy(plan)
    result = furniture_layout(plan, [asset])
    assert plan == before and len(result['placements']) == 1
    suggestion = result['placements'][0]
    assert suggestion['asset_kind'] == 'Imported USD (SimReady not verified)'
    plan['asset_placements'] = result['placements']
    report = build_usd(plan, tmp_path / 'building.usda')
    assert report['asset_imports'][0]['size_xyz_m'] == pytest.approx([2, 1, 1])
    stage = Usd.Stage.Open(report['usd_path'])
    bound = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default','render']).ComputeWorldBound(stage.GetPrimAtPath('/World/Assets/'+suggestion['id'])).ComputeAlignedBox()
    shape = box(*list(bound.GetMin())[:2], *list(bound.GetMax())[:2])
    assert Polygon(plan['rooms'][0]['polygon']).buffer(-.2).covers(shape)
    assert bound.GetMin()[2] == pytest.approx(0)
    assert result['decisions'] and any(d['status']=='proposed' for d in result['decisions'])


def test_clearances_avoid_openings_walls_holes_and_existing_assets(tmp_path):
    assets = [catalog_asset(tmp_path, 'Sofa', [2, 1, 1]),
              catalog_asset(tmp_path, 'Coffee Table', [1, .8, .5]),
              catalog_asset(tmp_path, 'Armchair', [.8, .8, 1])]
    plan = plan_for()
    plan['footprint']['holes'] = [[[3, 3], [5, 3], [5, 5], [3, 5]]]
    plan['openings'] = [{'type':'door', 'start':[0, 1], 'end':[0, 2], 'width_m':1}]
    plan['wall_segments'] = [{'start':[4, 0], 'end':[4, 2], 'thickness_m':.2}]
    existing = {'id':'kept', 'name':'Sofa', 'asset_path':assets[0]['usd_path'], 'position':[2, 2, 0]}
    plan['asset_placements'] = [existing]
    result = furniture_layout(plan, assets)
    assert result['placements'] and all(p['name']!='Sofa' for p in result['placements'])
    blocked = [box(1, 1.5, 3, 2.5), box(3, 3, 5, 5),
               LineString([[0, 1], [0, 2]]).buffer(.65), LineString([[4, 0], [4, 2]]).buffer(.2)]
    for placement in result['placements']:
        width, depth, _ = placement['size_xyz_m']
        if placement['rotation_deg'] % 180:
            width, depth = depth, width
        x, y = placement['position'][:2]
        rectangle = box(x-width/2, y-depth/2, x+width/2, y+depth/2)
        assert all(not rectangle.intersects(other) for other in blocked)
        blocked.append(rectangle)
    plan['asset_placements'] += result['placements']
    assert not furniture_layout(plan, assets)['placements']


@pytest.mark.parametrize('category,structure,asset_name', [
    ('office','office','Desk'), ('storage','factory','Heavy Duty Steel Shelving'),
    ('showroom','showroom','Display Table')])
def test_building_and_room_type_choose_only_available_matching_assets(tmp_path, category, structure, asset_name):
    asset = catalog_asset(tmp_path, asset_name, [1, 1, 1], structure)
    unrelated = catalog_asset(tmp_path, 'Sofa', [1, 1, 1], 'home')
    result = furniture_layout(plan_for(category, structure), [asset, unrelated])
    assert [item['name'] for item in result['placements']] == [asset_name]


@pytest.mark.parametrize('category', ['balcony', 'bathroom', 'corridor', 'Room 1', 'bedroom'])
def test_unknown_excluded_or_unavailable_roles_have_actionable_skips(tmp_path, category):
    result = furniture_layout(plan_for(category), [catalog_asset(tmp_path, 'Sofa', [2, 1, 1])])
    assert not result['placements']
    assert result['decisions'] and all(d['status']=='skipped' for d in result['decisions'])
    assert all(d['summary'] for d in result['decisions'])


def test_unknown_scale_or_insufficient_space_never_resizes_assets(tmp_path):
    asset = catalog_asset(tmp_path, 'Sofa', [2, 1, 1])
    for plan in [plan_for(size=.5), {**plan_for(), 'units':'px'}]:
        result = furniture_layout(plan, [asset])
        assert not result['placements'] and result['decisions']


@pytest.mark.parametrize('structure,name', [('office','Desk'), ('factory','Wood Pallet'), ('showroom','Display Table')])
def test_single_generic_business_room_uses_an_explicit_starter_assumption(tmp_path, structure, name):
    asset = catalog_asset(tmp_path, name, [1, 1, 1], structure)
    plan = plan_for('room', structure)
    plan['rooms'][0]['name'] = 'Room 1'
    result = furniture_layout(plan, [asset])
    assert len(result['placements']) == 1
    assert 'single' in result['placements'][0]['provenance'].lower()
    assert 'assumed' in result['placements'][0]['provenance'].lower()
    plan['rooms'].append({**plan['rooms'][0], 'id':'other'})
    assert not furniture_layout(plan, [asset])['placements']


def test_existing_model_without_name_is_not_duplicated(tmp_path):
    asset = catalog_asset(tmp_path, 'Sofa', [2, 1, 1])
    plan = plan_for()
    plan['asset_placements'] = [{'id':'user_sofa', 'asset_path':asset['usd_path'], 'position':[3, 3, 0]}]
    assert not furniture_layout(plan, [asset])['placements']


def test_existing_asset_outside_library_is_rejected_before_opening_usd(tmp_path, monkeypatch):
    asset = catalog_asset(tmp_path, 'Sofa', [2, 1, 1])
    monkeypatch.setenv('BLUEPRINT_STUDIO_ASSET_ROOT', str(tmp_path / 'dedicated_library'))
    monkeypatch.setattr(Usd.Stage, 'Open', lambda *args, **kwargs: pytest.fail('outside library USD opened'))
    plan = plan_for()
    plan['asset_placements'] = [{'id':'outside', 'asset_path':asset['usd_path'], 'position':[3, 3, 0]}]
    result = furniture_layout(plan, [asset])
    assert not result['placements']
    assert result['decisions'][0]['role'] == 'existing_assets'


def test_procedural_objects_prevent_duplicate_roles_and_overlapping_suggestions(tmp_path):
    assets = [catalog_asset(tmp_path, 'Bed', [2, 2, 1]),
              catalog_asset(tmp_path, 'Sofa', [2, 1, 1])]
    generated = [{'id':'generated_bed', 'name':'Bed', 'bounds_xy_m':[.5, .5, 2.5, 2.5]}]
    before = copy.deepcopy(generated)
    bedroom = furniture_layout(plan_for('bedroom'), assets, occupied_objects=generated)
    assert not bedroom['placements']
    assert any('already covers this role' in d['summary'] for d in bedroom['decisions'])
    living = furniture_layout(plan_for(), assets, occupied_objects=generated)
    assert len(living['placements']) == 1
    placed = living['placements'][0]
    x, y = placed['position'][:2]
    width, depth = placed['size_xyz_m'][:2]
    if placed['rotation_deg'] % 180:
        width, depth = depth, width
    assert not box(x-width/2, y-depth/2, x+width/2, y+depth/2).intersects(box(.5, .5, 2.5, 2.5).buffer(.25))
    assert generated == before
