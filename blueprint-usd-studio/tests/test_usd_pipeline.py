"""Checks against a documented flat and a small arbitrary plan."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pxr import Usd, UsdGeom, UsdPhysics

from app.geometry import polygon_area, triangulate, validate_plan
from app.usd_builder import build_style_variants, build_usd


ROOT = Path(__file__).resolve().parents[1]


def test_b1_1502_area_and_authoritative_room_dimensions(tmp_path):
    plan = json.loads((ROOT / "data/b1_1502/plan.json").read_text())
    assert not validate_plan(plan)
    assert plan["source"]["unit"] == "02" and plan["source"]["floor"] == 15
    assert abs(polygon_area(plan["footprint"]["polygon"]) - plan["area_schedule_m2"]["total"]) < 0.5
    rooms = {room["id"]: room for room in plan["rooms"]}
    assert rooms["living_dining"]["dimensions_m"] == [9.83, 4.03]
    assert rooms["kitchen"]["dimensions_m"] == [2.75, 4.12]
    assert rooms["bedroom_outer_south"]["dimensions_m"] == [4.65, 3.65]

    report = build_usd(plan, tmp_path / "b1-1502.usda", "contemporary")
    stage = Usd.Stage.Open(report["usd_path"])
    assert UsdGeom.GetStageMetersPerUnit(stage) == 1.0
    assert UsdGeom.GetStageUpAxis(stage) == UsdGeom.Tokens.z
    assert str(stage.GetDefaultPrim().GetPath()) == "/World"
    assert stage.GetPrimAtPath("/World/Spaces/living_dining").GetCustomDataByKey("printedDimensionsM") == "[9.83, 4.03]"
    assert sum(prim.HasAPI(UsdPhysics.CollisionAPI) for prim in stage.Traverse()) >= len(plan["wall_segments"])
    assert report["height_status"].startswith("assumed")


def test_office_styles_preserve_geometry_and_doors_have_clear_opening(tmp_path):
    plan = {
        "id": "sample-office", "name": "Small office", "structure_type": "office", "units": "m",
        "room_height_m": 3.2, "height_status": "measured",
        "footprint": {"polygon": [[0, 0], [6, 0], [6, 5], [0, 5]]},
        "rooms": [{"id": "main", "name": "Work area", "polygon": [[0, 0], [6, 0], [6, 5], [0, 5]], "dimensions_m": [6, 5]}],
        "wall_segments": [{"id": "front", "start": [0, 0], "end": [6, 0], "thickness_m": 0.18, "kind": "outer"}],
        "openings": [{"id": "entry", "wall_id": "front", "type": "door", "center": [3, 0], "width_m": 1.0}],
    }
    output = build_style_variants(plan, tmp_path)
    assert set(output["styles"]) == {"open_office", "warm_office", "executive_office"}
    stage = Usd.Stage.Open(output["variants_path"])
    variant = stage.GetDefaultPrim().GetVariantSets().GetVariantSet("architecturalStyle")
    assert set(variant.GetVariantNames()) == set(output["styles"])
    for style in variant.GetVariantNames():
        variant.SetVariantSelection(style)
        assert stage.GetPrimAtPath("/World/Building/FloorSlab")
        assert len([p for p in stage.Traverse() if str(p.GetPath()).startswith("/World/Building/Walls/front/Piece_")]) == 4


def test_concave_floor_triangulation_preserves_area():
    outline = [[0, 0], [4, 0], [4, 2], [2, 2], [2, 4], [0, 4]]
    faces = triangulate(outline)
    assert len(faces) == len(outline) - 2
    area = sum(polygon_area([outline[index] for index in face]) for face in faces)
    assert area == pytest.approx(polygon_area(outline))


def test_simready_placements_compose_vendor_colliders_and_proxy_fallback(tmp_path):
    catalog = json.loads((ROOT / "data/simready_catalog.json").read_text())
    asset_root = Path("/home/ovqa/Repos/OmniverseAssets/SimReady_Furniture_Misc_01_overlay")
    if not asset_root.is_dir():
        asset_root = Path(catalog["asset_root"])
    assets = {item["name"]: asset_root / item["usd_path"] for item in catalog["assets"]}
    needed = ("Crestwood Sofa", "Desk", "Serving Bowl", "Armchair")
    if not all(assets[name].is_file() for name in needed):
        pytest.skip("SimReady furniture pack is not installed")

    plan = {
        "name": "Furniture collision test", "structure_type": "home", "units": "m",
        "room_height_m": 3.0,
        "footprint": {"polygon": [[0, 0], [6, 0], [6, 5], [0, 5]]},
        "asset_placements": [
            {"id": "sofa", "asset_path": str(assets["Crestwood Sofa"]),
             "position": [1, 1, 0]},
            {"id": "desk", "asset_path": str(assets["Desk"]),
             "position": [3, 1, 0]},
            {"id": "bowl", "asset_path": str(assets["Serving Bowl"]),
             "position": [4, 3, 1], "physics_mode": "dynamic", "mass_kg": 0.35},
            {"id": "decor", "asset_path": str(assets["Armchair"]),
             "position": [2, 3, 0], "physics_mode": "none"},
        ],
    }
    report = build_usd(plan, tmp_path / "furnished.usda")
    stage = Usd.Stage.Open(report["usd_path"])

    def colliders(model):
        return [p for p in Usd.PrimRange(model, Usd.TraverseInstanceProxies())
                if p.HasAPI(UsdPhysics.CollisionAPI)]

    sofa = stage.GetPrimAtPath("/World/Assets/sofa/Model")
    assert sofa.GetVariantSet("PhysicsVariant").GetVariantSelection() == "RigidBody"
    assert len(colliders(sofa)) >= 1
    assert UsdPhysics.RigidBodyAPI(sofa).GetRigidBodyEnabledAttr().Get() is False
    assert stage.GetPrimAtPath("/World/Assets/sofa").GetCustomDataByKey("colliderSource") == "simReadyVariant"
    assert not stage.GetPrimAtPath("/World/Assets/sofa/Model/CollisionProxy")

    desk = stage.GetPrimAtPath("/World/Assets/desk/Model")
    proxy = stage.GetPrimAtPath("/World/Assets/desk/Model/CollisionProxy")
    assert len(colliders(desk)) == 1 and proxy.HasAPI(UsdPhysics.CollisionAPI)
    assert UsdGeom.Imageable(proxy).GetVisibilityAttr().Get() == UsdGeom.Tokens.invisible
    assert stage.GetPrimAtPath("/World/Assets/desk").GetCustomDataByKey("colliderSource") == "boundsProxy"
    assert UsdPhysics.RigidBodyAPI(desk).GetRigidBodyEnabledAttr().Get() is False

    bowl = stage.GetPrimAtPath("/World/Assets/bowl/Model")
    assert len(colliders(bowl)) >= 1
    assert UsdPhysics.RigidBodyAPI(bowl).GetRigidBodyEnabledAttr().Get() is True
    assert UsdPhysics.MassAPI(bowl).GetMassAttr().Get() == pytest.approx(0.35)

    decor = stage.GetPrimAtPath("/World/Assets/decor/Model")
    assert decor.GetVariantSet("PhysicsVariant").GetVariantSelection() == "None"
    assert colliders(decor) == []
