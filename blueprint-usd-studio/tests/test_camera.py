import json
import itertools
from pathlib import Path

import numpy as np
import pytest
from pxr import Gf, Usd, UsdGeom, UsdPhysics

from app.usd_builder import build_usd
from streaming.camera import CameraController
from streaming.prepare_scene import prepare_scene


def test_overview_is_still_and_zoom_cannot_cross_target():
    camera = CameraController([7, 11, 1], 30, 'Z')
    np.testing.assert_allclose(camera.matrix(0), camera.matrix(100))
    camera.zoom(1000)
    assert camera.state()['radius'] == 1.5
    assert np.isfinite(camera.matrix()).all()
    camera.set_view('plan')
    # Plan X is screen-right, Y is screen-up; no reflected/rotated blueprint.
    matrix = camera.matrix()
    assert matrix[0, 0] == pytest.approx(1)
    assert matrix[1, 1] == pytest.approx(1, abs=.001)


def test_eye_level_is_inside_selected_room_and_reset_restores_overview():
    room = {'id':'living', 'min':[0,0,0], 'max':[10,4,0],
            'eye':[1.8,1.12,1.6], 'look_at':[8.5,2.6,1.35]}
    camera = CameraController([5,2,1], 20, 'Z', [room])
    home = camera.matrix()
    camera.set_view('interior', 'living')
    np.testing.assert_allclose(camera.matrix()[3,:3], room['eye'])
    camera.zoom(1)
    assert np.linalg.norm(camera.matrix()[3,:3] - room['eye']) == pytest.approx(.25, abs=.001)
    with pytest.raises(ValueError):
        camera.set_view('room', 'missing')
    camera.set_view('overview')
    np.testing.assert_allclose(home, camera.matrix())


def test_building_fits_camera_and_rooms_survive_preparation(tmp_path):
    plan = json.loads((Path(__file__).parents[1] / 'data/b1_1502/plan.json').read_text())
    build_usd(plan, tmp_path/'flat.usda')
    scene = prepare_scene(tmp_path/'flat.usda', tmp_path/'stream.usda', 1280, 720)
    assert scene['up_axis'] == 'Z'
    assert len(scene['rooms']) == 21
    assert scene['walls'] == plan['source_wall_segments'] and scene['walls']
    assert all(wall['kind'] == 'source_room_boundary' for wall in scene['walls'])
    for room in scene['rooms']:
        assert room['modeled_dimensions'] == pytest.approx(room['dimensions'], abs=2e-6)
    assert next(r for r in scene['rooms'] if r['id']=='living_dining')['dimensions'] == [9.83,4.03]
    camera = CameraController(scene['target'], scene['radius'], scene['up_axis'], scene['rooms'], scene['plan_radius'])
    for view in ['overview', 'plan']:
        camera.set_view(view)
        matrix = camera.matrix()
        if view == 'plan':
            assert matrix[3, 2] > scene['bounds_max'][2]
            assert -matrix[2, 2] < -.999999
        world_to_camera = Gf.Matrix4d(matrix.tolist()).GetInverse()
        for point in itertools.product(*zip(scene['bounds_min'],scene['bounds_max'])):
            local = world_to_camera.Transform(Gf.Vec3d(*point))
            assert local[2] < 0
            assert abs(local[0]/local[2]) < 36/56
            assert abs(local[1]/local[2]) < (36/56)*720/1280
    stage = Usd.Stage.Open(str(tmp_path/'stream.usda'))
    assert not stage.GetPrimAtPath('/World/Environment')  # Keep authored lighting, no duplicate dome.


def test_traced_doors_are_framed_without_filling_passage(tmp_path):
    plan = json.loads((Path(__file__).parents[1] / 'data/b1_1502/plan.json').read_text())
    build_usd(plan, tmp_path/'flat.usda')
    stage = Usd.Stage.Open(str(tmp_path/'flat.usda'))
    lintel = UsdGeom.Cube(stage.GetPrimAtPath('/World/Building/Openings/main_entry/Piece_000'))
    center = lintel.GetPrim().GetAttribute('xformOp:translate').Get()
    size = lintel.GetPrim().GetAttribute('xformOp:scale').Get()
    assert center[2] - size[2]/2 == pytest.approx(2.2)
    assert stage.GetPrimAtPath('/World/Building/Openings/service_wc_door')
    assert stage.GetPrimAtPath('/World/Building/Openings/north_toilet_door')


def test_stream_expands_nested_instances_without_changing_source_or_geometry(tmp_path):
    source_path = tmp_path / 'instanced.usda'
    source = Usd.Stage.CreateNew(str(source_path))
    UsdGeom.SetStageUpAxis(source, 'Z')
    UsdGeom.SetStageMetersPerUnit(source, 1)
    world = UsdGeom.Xform.Define(source, '/World')
    source.SetDefaultPrim(world.GetPrim())
    cube = UsdGeom.Cube.Define(source, '/Shape')
    cube.CreateSizeAttr(2)
    UsdPhysics.CollisionAPI.Apply(cube.GetPrim())
    UsdGeom.Xform.Define(source, '/Assembly')
    nested = source.DefinePrim('/Assembly/Nested')
    nested.GetReferences().AddInternalReference('/Shape')
    nested.SetInstanceable(True)
    cabinet = UsdGeom.Xform.Define(source, '/World/Assets/Cabinet')
    cabinet.AddTranslateOp().Set(Gf.Vec3d(5, 10, 0))
    cabinet.GetPrim().GetReferences().AddInternalReference('/Assembly')
    cabinet.GetPrim().SetInstanceable(True)
    source.GetRootLayer().Save()
    original_bytes = source_path.read_bytes()

    prepare_scene(source_path, tmp_path / 'stream.usda', 1280, 720)
    stream = Usd.Stage.Open(str(tmp_path / 'stream.usda'))
    model = stream.GetPrimAtPath('/World/Model')
    assert not any(prim.IsInstance() for prim in Usd.PrimRange(model))
    assert stream.GetPrimAtPath('/World/Model/Assets/Cabinet/Nested').HasAPI(UsdPhysics.CollisionAPI)
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
    before = cache.ComputeWorldBound(world.GetPrim()).ComputeAlignedBox()
    after = cache.ComputeWorldBound(model).ComputeAlignedBox()
    assert list(after.GetMin()) == pytest.approx(list(before.GetMin()))
    assert list(after.GetMax()) == pytest.approx(list(before.GetMax()))
    assert source_path.read_bytes() == original_bytes
    assert Usd.Stage.Open(str(source_path)).GetPrimAtPath('/World/Assets/Cabinet').IsInstance()
