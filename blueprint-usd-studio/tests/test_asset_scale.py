"""Referenced USD units and pivots must not change real furniture dimensions."""

import json

import pytest
from pxr import Gf, Usd, UsdGeom, UsdPhysics

from app.usd_builder import build_usd


@pytest.mark.parametrize("units,axis", [(1.0, "Z"), (0.01, "Z"), (1.0, "Y"), (0.01, "Y")])
@pytest.mark.parametrize("reset", [False, True])
def test_asset_dimensions_units_axis_and_floor_anchor(tmp_path, monkeypatch, units, axis, reset):
    monkeypatch.setenv("BLUEPRINT_STUDIO_ASSET_ROOT", str(tmp_path))
    asset_path = tmp_path / "asset.usda"
    source = Usd.Stage.CreateNew(str(asset_path))
    UsdGeom.SetStageMetersPerUnit(source, units)
    UsdGeom.SetStageUpAxis(source, axis)
    root = UsdGeom.Xform.Define(source, "/Furniture")
    source.SetDefaultPrim(root.GetPrim())
    root.AddTranslateOp().Set(Gf.Vec3d(4 / units, 5 / units, 6 / units))
    rotation = Gf.Vec3f(0, 180, 0) if axis == "Y" else Gf.Vec3f(0, 0, 180)
    root.AddRotateXYZOp().Set(rotation)
    root.AddScaleOp().Set(Gf.Vec3f(2, 2, 2))
    root.SetResetXformStack(reset)
    shape = UsdGeom.Cube.Define(source, "/Furniture/Body")
    shape.CreateSizeAttr(1)
    size = [0.5 / units, 1 / units, 1.5 / units]
    if axis == "Y":
        size[1], size[2] = size[2], size[1]
    UsdGeom.Xformable(shape).AddScaleOp().Set(Gf.Vec3f(*size))
    UsdPhysics.CollisionAPI.Apply(shape.GetPrim())
    source.GetRootLayer().Save()
    plan = {
        "name": "Metric reference", "units": "m",
        "footprint": {"polygon": [[0, 0], [10, 0], [10, 10], [0, 10]]},
        "asset_placements": [{"id": "furniture", "asset_path": str(asset_path),
                              "position": [2, 3, 0.008]}],
    }
    report = build_usd(plan, tmp_path / "building.usda")
    stage = Usd.Stage.Open(report["usd_path"])
    placement = stage.GetPrimAtPath("/World/Assets/furniture")
    model = stage.GetPrimAtPath("/World/Assets/furniture/Model")
    bound = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_]).ComputeWorldBound(model).ComputeAlignedBox()
    assert list(bound.GetSize()) == pytest.approx([1, 2, 3])
    assert bound.GetMin()[2] == pytest.approx(0.008)
    # Keep the source's root operations and its collision geometry intact.
    assert model.GetAttribute("xformOp:translate").Get() == Gf.Vec3d(4 / units, 5 / units, 6 / units)
    assert model.GetAttribute("xformOp:rotateXYZ").Get() == rotation
    assert model.GetAttribute("xformOp:scale").Get() == Gf.Vec3f(2, 2, 2)
    assert stage.GetPrimAtPath(str(model.GetPath()) + "/Body").HasAPI(UsdPhysics.CollisionAPI)
    assert placement.GetCustomDataByKey("sourceUnits") == units
    assert placement.GetCustomDataByKey("sourceUpAxis") == axis
    assert placement.GetCustomDataByKey("unitScale") == units
    assert placement.GetCustomDataByKey("sourceRootReset") == reset
    assert "bottom" in placement.GetCustomDataByKey("floorAnchor")
    assert report["asset_imports"][0]["size_xyz_m"] == pytest.approx([1, 2, 3])
    assert report["asset_imports"][0]["bottom_m"] == pytest.approx(0.008)


@pytest.mark.parametrize("units", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_asset_units_are_rejected(tmp_path, monkeypatch, units):
    monkeypatch.setenv("BLUEPRINT_STUDIO_ASSET_ROOT", str(tmp_path))
    path = tmp_path / "bad_units.usda"
    source = Usd.Stage.CreateNew(str(path))
    source.SetMetadata("metersPerUnit", units)
    cube = UsdGeom.Cube.Define(source, "/Asset")
    source.SetDefaultPrim(cube.GetPrim())
    source.GetRootLayer().Save()
    plan = {"footprint": {"polygon": [[0, 0], [6, 0], [6, 5], [0, 5]]},
            "asset_placements": [{"id": "bad", "asset_path": str(path)}]}
    with pytest.raises(ValueError, match="metersPerUnit must be positive and finite"):
        build_usd(plan, tmp_path / "building.usda")


def test_referenced_geometry_root_keeps_its_type(tmp_path, monkeypatch):
    monkeypatch.setenv("BLUEPRINT_STUDIO_ASSET_ROOT", str(tmp_path))
    path = tmp_path / "cube.usda"
    source = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageMetersPerUnit(source, 0.01)
    UsdGeom.SetStageUpAxis(source, "Z")
    cube = UsdGeom.Cube.Define(source, "/Cube")
    cube.CreateSizeAttr(100)
    source.SetDefaultPrim(cube.GetPrim())
    source.GetRootLayer().Save()
    plan = {"footprint": {"polygon": [[0, 0], [6, 0], [6, 5], [0, 5]]},
            "asset_placements": [{"id": "cube", "asset_path": str(path), "physics_mode": "none"}]}
    report = build_usd(plan, tmp_path / "building.usda")
    stage = Usd.Stage.Open(report["usd_path"])
    assert stage.GetPrimAtPath("/World/Assets/cube/Model").IsA(UsdGeom.Cube)
    assert report["asset_imports"][0]["size_xyz_m"] == pytest.approx([1, 1, 1])


@pytest.mark.parametrize("geometry_root", [False, True])
def test_fallback_collision_proxy_matches_transformed_asset(tmp_path, monkeypatch, geometry_root):
    monkeypatch.setenv("BLUEPRINT_STUDIO_ASSET_ROOT", str(tmp_path))
    path = tmp_path / "transformed.usda"
    source = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageMetersPerUnit(source, 0.01)
    UsdGeom.SetStageUpAxis(source, "Z")
    if geometry_root:
        body = UsdGeom.Cube.Define(source, "/Asset")
        root = UsdGeom.Xformable(body)
    else:
        root = UsdGeom.Xform.Define(source, "/Asset")
        body = UsdGeom.Cube.Define(source, "/Asset/Body")
    body.CreateSizeAttr(100)
    source.SetDefaultPrim(root.GetPrim())
    root.AddTranslateOp().Set(Gf.Vec3d(400, 500, 600))
    root.AddScaleOp().Set(Gf.Vec3f(2, 2, 2))
    source.GetRootLayer().Save()
    plan = {"footprint": {"polygon": [[0, 0], [10, 0], [10, 10], [0, 10]]},
            "asset_placements": [{"id": "test", "asset_path": str(path), "position": [1, 2, 0]}]}
    stage = Usd.Stage.Open(build_usd(plan, tmp_path / "building.usda")["usd_path"])
    model = stage.GetPrimAtPath("/World/Assets/test/Model")
    visual = model if geometry_root else stage.GetPrimAtPath(str(model.GetPath()) + "/Body")
    proxy = stage.GetPrimAtPath(str(model.GetPath()) + "/CollisionProxy")
    assert proxy and proxy.HasAPI(UsdPhysics.CollisionAPI)
    purposes = [UsdGeom.Tokens.default_]
    visual_box = UsdGeom.BBoxCache(Usd.TimeCode.Default(), purposes).ComputeWorldBound(visual).ComputeAlignedBox()
    proxy_box = UsdGeom.BBoxCache(Usd.TimeCode.Default(), purposes, False, True).ComputeWorldBound(proxy).ComputeAlignedBox()
    assert list(proxy_box.GetMin()) == pytest.approx(list(visual_box.GetMin()))
    assert list(proxy_box.GetMax()) == pytest.approx(list(visual_box.GetMax()))


def test_physics_variant_root_reset_is_normalized_after_selection(tmp_path, monkeypatch):
    monkeypatch.setenv("BLUEPRINT_STUDIO_ASSET_ROOT", str(tmp_path))
    path = tmp_path / "variant_reset.usda"
    source = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageMetersPerUnit(source, 0.01)
    UsdGeom.SetStageUpAxis(source, "Z")
    root = UsdGeom.Xform.Define(source, "/Asset")
    source.SetDefaultPrim(root.GetPrim())
    body = UsdGeom.Cube.Define(source, "/Asset/Body")
    body.CreateSizeAttr(100)
    variants = root.GetPrim().GetVariantSets().AddVariantSet("PhysicsVariant")
    for name, reset in [("None", False), ("RigidBody", True)]:
        variants.AddVariant(name)
        variants.SetVariantSelection(name)
        with variants.GetVariantEditContext():
            root.SetResetXformStack(reset)
            if reset:
                UsdPhysics.CollisionAPI.Apply(body.GetPrim())
                UsdPhysics.RigidBodyAPI.Apply(root.GetPrim())
    variants.SetVariantSelection("None")
    source.GetRootLayer().Save()
    plan = {"footprint": {"polygon": [[0, 0], [10, 0], [10, 10], [0, 10]]},
            "asset_placements": [{"id": "test", "asset_path": str(path), "position": [1, 2, 0.008]}]}
    report = build_usd(plan, tmp_path / "building.usda")
    stage = Usd.Stage.Open(report["usd_path"])
    model = stage.GetPrimAtPath("/World/Assets/test/Model")
    bound = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_]).ComputeWorldBound(model).ComputeAlignedBox()
    assert list(bound.GetSize()) == pytest.approx([1, 1, 1])
    assert bound.GetMin()[2] == pytest.approx(0.008)
    assert model.GetVariantSet("PhysicsVariant").GetVariantSelection() == "RigidBody"
    assert report["asset_imports"][0]["source_root_reset"] is True


def test_opening_assemblies_keep_assumptions_and_passages_visible(tmp_path):
    def opening(identifier, kind, y, **extra):
        return {"id": identifier, "type": kind, "start": [1, y], "end": [2, y],
                "width_m": 1.0, "height_m": 2.2, "free_opening": True,
                "connects": ["bedroom", "bathroom"], "provenance": {"basis": "inferred"}, **extra}
    decisions = [{"id": "bath_access", "basis": "assumed"}]
    audit = {"units": "m", "gross_area_m2": 9999, "footprint_span_m": [100, 100]}
    plan = {"name": "Opening assembly", "units": "m", "room_height_m": 3,
            "footprint": {"polygon": [[0, 0], [6, 0], [6, 6], [0, 6]]},
            "wall_segments": [], "reconstruction_decisions": decisions, "scale_audit": audit,
            "openings": [opening("door", "door", 1), opening("slider", "sliding_door", 2),
                         opening("passage", "opening", 3), opening("full_height", "opening", 4, no_header=True)]}
    stage = Usd.Stage.Open(build_usd(plan, tmp_path / "openings.usda")["usd_path"])
    world = stage.GetDefaultPrim()
    assert json.loads(world.GetCustomDataByKey("reconstructionDecisions")) == decisions
    exported_audit = json.loads(world.GetCustomDataByKey("scaleAudit"))
    assert exported_audit["units"] == "m"
    assert exported_audit["gross_area_m2"] == 36
    assert exported_audit["footprint_span_m"] == [6, 6]
    door = stage.GetPrimAtPath("/World/Building/Openings/door")
    assert json.loads(door.GetCustomDataByKey("connects")) == ["bedroom", "bathroom"]
    assert json.loads(door.GetCustomDataByKey("provenance")) == {"basis": "inferred"}
    assert door.GetCustomDataByKey("widthM") == 1.0
    assert door.GetCustomDataByKey("heightM") == 2.2
    assert stage.GetPrimAtPath("/World/Building/Openings/door/Leaf")
    assert not stage.GetPrimAtPath("/World/Building/Openings/door/Leaf").HasAPI(UsdPhysics.CollisionAPI)
    assert stage.GetPrimAtPath("/World/Building/Openings/slider/Glass_0")
    assert not stage.GetPrimAtPath("/World/Building/Openings/passage/Leaf")
    full = stage.GetPrimAtPath("/World/Building/Openings/full_height")
    assert full and not list(full.GetChildren())


@pytest.mark.parametrize('axis', ['Y', 'Z'])
def test_user_resize_is_separate_from_native_units_and_floor_anchor(tmp_path, monkeypatch, axis):
    monkeypatch.setenv('BLUEPRINT_STUDIO_ASSET_ROOT', str(tmp_path))
    path = tmp_path / 'centimetres.usda'
    source = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageMetersPerUnit(source, .01)
    UsdGeom.SetStageUpAxis(source, axis)
    cube = UsdGeom.Cube.Define(source, '/Asset')
    source.SetDefaultPrim(cube.GetPrim())
    cube.CreateSizeAttr(100)
    cube.AddTranslateOp().Set(Gf.Vec3d(0,0,200))
    source.GetRootLayer().Save()
    history = [{'action':'resize', 'basis':'User supplied dimensions'}]
    plan = {'footprint':{'polygon':[[0,0],[10,0],[10,10],[0,10]]}, 'asset_placements':[
        {'id':'resize', 'asset_path':str(path), 'position':[2,3,.4], 'rotation_deg':90,
         'scale_xyz':[2,3,.5], 'edit_history':history, 'asset_kind':'Imported USD (SimReady not verified)'}]}
    report = build_usd(plan, tmp_path / 'scene.usda')
    stage = Usd.Stage.Open(report['usd_path'])
    prim = stage.GetPrimAtPath('/World/Assets/resize')
    box = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default']).ComputeWorldBound(prim).ComputeAlignedBox()
    assert list(box.GetSize()) == pytest.approx([3,2,.5])
    assert box.GetMin()[2] == pytest.approx(.4)
    assert report['asset_imports'][0]['source_size_xyz_m'] == pytest.approx([1,1,1])
    assert report['asset_imports'][0]['size_xyz_m'] == pytest.approx([2,3,.5])
    assert report['asset_imports'][0]['edit_history'] == history
    assert prim.GetCustomDataByKey('simReady') is False
    assert prim.GetCustomDataByKey('unitScale') == .01
