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


def test_explicit_generated_resize_preserves_source_shape_and_building():
    stage = Usd.Stage.CreateInMemory()
    obj = UsdGeom.Xform.Define(stage, '/World/Interiors/Chair')
    obj.GetPrim().SetCustomDataByKey('interiorDecor', True)
    obj.AddTranslateOp().Set(Gf.Vec3d(1, 2, 0))
    obj.AddScaleOp().Set(Gf.Vec3d(2, 3, 4))
    UsdGeom.Cube.Define(stage, '/World/Interiors/Chair/Shape').CreateSizeAttr(1)
    wall = UsdGeom.Cube.Define(stage, '/World/Building/Wall')
    plan = {'object_overrides': {'bohemian': {str(obj.GetPath()): {'scale_xyz': [1.5, .5, 2]}}}}
    result = apply_object_edits(stage, plan, 'bohemian')[0]
    assert result['source_size_xyz_m'] == pytest.approx([2, 3, 4])
    assert result['local_size_xyz_m'] == pytest.approx([3, 1.5, 8])
    assert wall.GetSizeAttr().Get() == 2
    assert stage.GetPrimAtPath('/World/Interiors/Chair/Shape').GetAttribute('size').Get() == 1
    assert apply_object_edits(stage, plan, 'bohemian')[0]['local_size_xyz_m'] == pytest.approx([3, 1.5, 8])


@pytest.mark.parametrize('change', [{'scale_xyz':[0,1,1]}, {'scale_xyz':[-1,1,1]},
    {'scale_xyz':[1,2]}, {'scale_xyz':[True,1,1]}, {'scale_xyz':[1,float('inf'),1]},
    {'position':[0,float('nan'),0]}, {'rotation_deg':'90'}])
def test_transform_validation_for_saved_imports_and_procedural_edits(change):
    from app.editable_objects import validate_asset_edits
    assert validate_asset_edits({'asset_placements':[change]})
    assert validate_asset_edits({'object_overrides':{'classic':{'/World/Object':change}}})
