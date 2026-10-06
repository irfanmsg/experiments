import json

import pytest
from pxr import Usd, UsdGeom, UsdPhysics

from app.usd_builder import build_usd


@pytest.mark.parametrize('kind,no_header,expected_bounds', [
    ('opening', True, []),
    ('opening', False, [(2.1, 3.0)]),
    ('door', False, [(2.1, 3.0), (.02, 2.08)]),
])
def test_full_width_opening_has_no_leaf_and_only_an_optional_header(tmp_path, kind, no_header, expected_bounds):
    plan = {'units':'m', 'structure_type':'office', 'room_height_m':3,
            'footprint':{'polygon':[[0, 0], [4, 0], [4, 3], [0, 3]]},
            'wall_segments':[{'id':'front', 'start':[0, 0], 'end':[4, 0]}],
            'openings':[{'wall_id':'front', 'type':kind, 'center':[2, 0],
                         'width_m':4, 'height_m':2.1, 'no_header':no_header}]}
    report = build_usd(plan, tmp_path / 'scene.usda', 'open_office')
    stage = Usd.Stage.Open(report['usd_path'])
    pieces = list(stage.GetPrimAtPath('/World/Building/Walls/front').GetChildren())
    assert len(pieces) == len(expected_bounds)
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render'])
    for prim, (bottom, top) in zip(pieces, expected_bounds):
        bounds = cache.ComputeWorldBound(prim).ComputeAlignedBox()
        assert bounds.GetMin()[2] == pytest.approx(bottom, abs=1e-6)
        assert bounds.GetMax()[2] == pytest.approx(top)
        if bottom > 2:
            assert bounds.GetMin()[0] == pytest.approx(0)
            assert bounds.GetMax()[0] == pytest.approx(4)
            assert prim.HasAPI(UsdPhysics.CollisionAPI)
        else:
            assert not prim.HasAPI(UsdPhysics.CollisionAPI)


def test_inferred_gap_cuts_the_matching_one_based_derived_wall(tmp_path):
    plan = {'units':'m', 'room_height_m':3,
            'footprint':{'polygon':[[0, 0], [4, 0], [4, 3], [0, 3]]},
            'openings':[{'wall_id':'wall_1', 'type':'opening', 'center':[2, 0],
                         'width_m':1, 'no_header':True}]}
    stage = Usd.Stage.Open(build_usd(plan, tmp_path / 'gap.usda')['usd_path'])
    pieces = list(stage.GetPrimAtPath('/World/Building/Walls/wall_1').GetChildren())
    assert len(pieces) == 2
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default','render'])
    for piece in pieces:
        bounds = cache.ComputeWorldBound(piece).ComputeAlignedBox()
        assert bounds.GetMax()[0] <= 1.5 or bounds.GetMin()[0] >= 2.5
        assert bounds.GetMin()[2] == pytest.approx(0)
        assert bounds.GetMax()[2] == pytest.approx(3)


def test_inferred_room_keeps_printed_dimensions_separate_from_modeled_geometry(tmp_path):
    evidence = {'text': "7'0\" x 9'0\"", 'bbox': [10, 20, 70, 40], 'confidence': .91}
    plan = {'units':'m', 'rooms':[{'id':'reviewed', 'name':'Reviewed room',
            'polygon':[[0, 0], [2, 0], [2, 3], [0, 3]], 'dimensions_m':[2, 3],
            'printed_dimensions_m':[2.1336, 2.7432], 'source_evidence': evidence}]}
    stage = Usd.Stage.Open(build_usd(plan, tmp_path / 'evidence.usda')['usd_path'])
    room = stage.GetPrimAtPath('/World/Spaces/reviewed')
    assert json.loads(room.GetCustomDataByKey('printedDimensionsM')) == [2.1336, 2.7432]
    assert json.loads(room.GetCustomDataByKey('sourceEvidence')) == evidence
    assert room.GetCustomDataByKey('tracedAreaM2') == pytest.approx(6)
