"""Review evidence remains available alongside the exported geometry."""
import json

from app import main


def test_trace_download_preserves_source_and_inferred_evidence(tmp_path, monkeypatch):
    project = tmp_path / 'scene'
    project.mkdir()
    plan = {'source': {'sheet': 'approved'}, 'dimension_model': 'metric',
            'reconstruction_decisions': [{'id': 'walls', 'status': 'needs-review', 'parameters': {'thickness_m': .15}}],
            'scale_audit': {'meters_per_unit': 1, 'room_dimensions': [{'id': 'room', 'printed': [3, 4], 'modeled': [3, 4]}]},
            'openings': [{'id': 'bath_door', 'connects': ['bedroom', 'bathroom'], 'provenance': {'width': 'assumed'}}],
            'asset_placements': []}
    plan['rooms'] = [{'id': 'room', 'dimensions_m': [3, 4], 'polygon': [[0, 0], [3, 0], [3, 4], [0, 4]]}]
    (project / 'plan.json').write_text(json.dumps(plan))
    monkeypatch.setattr(main, 'UPLOADS', tmp_path)
    monkeypatch.setattr(main, 'OUTPUT', tmp_path)
    export = {'style': 'contemporary', 'asset_imports': [{'id': 'chair', 'source_units_m': .01, 'unit_scale': .01}]}
    (project / 'reconstruction_trace.json').write_text(json.dumps(export))
    response = main.project_reconstruction_trace('scene')
    trace = json.loads(response.body)
    assert trace['decisions'] == plan['reconstruction_decisions']
    assert trace['openings'][0]['provenance']['width'] == 'assumed'
    assert trace['scale_audit']['room_dimensions'][0]['modeled'] == [3, 4]
    assert trace['last_export']['asset_imports'][0]['unit_scale'] == .01
    assert 'attachment' in response.headers['content-disposition']


def test_scale_trace_remeasures_edited_geometry():
    from app.geometry import measured_scale_audit
    plan = {'rooms': [{'id': 'room', 'name': 'Bedroom', 'dimensions_m': [3, 4],
                       'polygon': [[0, 0], [3.2, 0], [3.2, 4], [0, 4]]}],
            'footprint': {'polygon': [[0, 0], [5, 0], [5, 6], [0, 6]],
                          'holes': [[[1, 1], [2, 1], [2, 2], [1, 2]]]},
            'scale_audit': {'room_dimensions': [{'id': 'removed', 'modeled': [100, 100]}],
                            'gross_area_m2': 99, 'scheduled_area_m2': {'total': 25}}}
    audit = measured_scale_audit(plan)
    assert audit['room_dimensions'] == [{'id': 'room', 'name': 'Bedroom', 'printed': [3, 4],
                                        'modeled': [3.2, 4], 'dimension_mode': 'raster'}]
    assert audit['gross_area_m2'] == 29
    assert audit['footprint_span_m'] == [5, 6]
    assert audit['scheduled_area_m2'] == {'total': 25}
    assert plan['scale_audit']['gross_area_m2'] == 99  # Remeasurement does not mutate history.


def test_source_guided_simready_layout_keeps_physical_furniture_inside_rooms(tmp_path):
    from pathlib import Path
    import pytest
    from pxr import Usd, UsdGeom
    from shapely.geometry import LineString, Polygon, box
    from shapely.ops import unary_union
    from app.asset_library import b1_starter_furniture
    from app.usd_builder import build_usd

    plan = json.loads((Path(__file__).parents[1] / 'data/b1_1502/plan.json').read_text())
    plan['asset_placements'] = b1_starter_furniture(plan)
    if not plan['asset_placements']:
        pytest.skip('SimReady furniture is not installed')
    assert len(plan['asset_placements']) == 15
    assert all('Layout.jpeg' in item['provenance'] for item in plan['asset_placements'])
    report = build_usd(plan, tmp_path / 'furnished.usda')
    stage = Usd.Stage.Open(report['usd_path'])
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
    rooms = {room['id']: Polygon(room['polygon']) for room in plan['rooms']}
    door_keepouts = unary_union([
        LineString([opening['start'], opening['end']]).buffer(.55, cap_style=2)
        for opening in plan['openings']
    ])
    for asset in plan['asset_placements']:
        bounds = cache.ComputeWorldBound(stage.GetPrimAtPath('/World/Assets/' + asset['id'])).ComputeAlignedBox()
        minimum, maximum = bounds.GetMin(), bounds.GetMax()
        footprint = box(minimum[0], minimum[1], maximum[0], maximum[1])
        room_id = ('wfh' if asset['id'].startswith('den_') else 'entry' if asset['id'].startswith('entry_')
                   else 'balcony_curved' if asset['id'].startswith('balcony_') else 'living_dining')
        assert rooms[room_id].buffer(.001).covers(footprint), (asset['id'], footprint.bounds)
        assert footprint.intersection(door_keepouts).area < 1e-7, (asset['id'], footprint.bounds)
    chair = next(item for item in report['asset_imports'] if item['id'] == 'living_armchair')
    assert chair['size_xyz_m'][2] == pytest.approx(.855503, abs=.00001)
