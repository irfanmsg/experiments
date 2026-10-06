import pytest
from pxr import Gf, Usd, UsdGeom

from app.editable_objects import apply_object_edits


def test_generated_object_edits_preserve_size_and_architecture():
    stage = Usd.Stage.CreateInMemory()
    obj = UsdGeom.Xform.Define(stage, '/World/Interiors/Rug')
    obj.GetPrim().SetCustomDataByKey('interiorDecor', True)
    obj.AddTranslateOp().Set(Gf.Vec3d(1, 2, .01))
    UsdGeom.Cube.Define(stage, '/World/Interiors/Rug/Shape').CreateSizeAttr(1)
    wall = UsdGeom.Cube.Define(stage, '/World/Building/Wall')
    plan = {'object_overrides': {'bohemian': {'/World/Interiors/Rug': {
        'position': [4, 5, .01], 'rotation_deg': 90}}}}
    result = apply_object_edits(stage, plan, 'bohemian')
    assert result[0]['position'] == [4, 5, .01]
    assert result[0]['rotation_deg'] == 90
    assert result[0]['asset_kind'] == 'Procedural USD'
    assert stage.GetPrimAtPath('/World/Interiors/Rug/Shape').GetAttribute('size').Get() == 1
    assert wall.GetSizeAttr().Get() == 2
    plan['object_overrides']['bohemian']['/World/Interiors/Rug'] = {'removed': True}
    assert apply_object_edits(stage, plan, 'bohemian') == []
    assert not obj.GetPrim().IsActive()


def test_invalid_edit_is_rejected():
    stage = Usd.Stage.CreateInMemory()
    obj = UsdGeom.Xform.Define(stage, '/World/Fixtures/Bed')
    obj.GetPrim().SetCustomDataByKey('assumedFixture', True)
    with pytest.raises(ValueError, match='finite'):
        apply_object_edits(stage, {'object_overrides': {'classic': {
            str(obj.GetPath()): {'position': [0, float('nan'), 0]}}}}, 'classic')
