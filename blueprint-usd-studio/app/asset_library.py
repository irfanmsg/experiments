"""Curated local SimReady library; source pack remains outside this repository."""

from __future__ import annotations

import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALLOWED = Path(os.environ.get("BLUEPRINT_STUDIO_ASSET_ROOT", "/home/ovqa/Repos/OmniverseAssets")).expanduser().resolve()
OVERLAY = ALLOWED / "SimReady_Furniture_Misc_01_overlay"


def _read_catalog(filename: str, overlay: Path | None, structure_types: list[str]) -> list[dict]:
    path = ROOT / "data" / filename
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    base = overlay if overlay and overlay.is_dir() else ALLOWED / Path(data["asset_root"]).name
    base = base.absolute()
    result = []
    for asset in data.get("assets", []):
        full_path = (base / asset["usd_path"]).absolute()
        if not full_path.is_relative_to(ALLOWED) or not full_path.resolve().is_relative_to(ALLOWED):
            raise ValueError("Invalid SimReady catalog path")
        if full_path.is_file():
            result.append({**asset, "usd_path": str(full_path), "structure_types": asset.get("structure_types", structure_types)})
    return result


def catalog() -> dict:
    furniture = _read_catalog("simready_catalog.json", OVERLAY, ["home", "office", "showroom", "other"])
    warehouse = _read_catalog("simready_warehouse_catalog.json", None, ["factory", "showroom", "other"])
    return {"asset_root": str(ALLOWED), "assets": furniture + warehouse}


def b1_starter_furniture(plan=None) -> list[dict]:
    by_name = {item["name"]: item for item in catalog()["assets"] if "home" in item["structure_types"]}
    choices = [
        ("living_sofa", "Crestwood Sofa", [10.2, 10.35, 0.008], -90),
        ("living_table", "Appleseed Coffee Table", [10.2, 11.7, 0.008], 90),
        ("living_armchair", "Armchair", [8.1, 12.4, 0.012], 0),
        ("dining_table", "Dellwood Dining Table", [5.1, 11.5, 0.008], 90),
        ("dining_chair_n1", "Dellwood Dining Chair", [4.65, 12.35, 0.008], -90),
        ("dining_chair_n2", "Dellwood Dining Chair", [5.55, 12.35, 0.008], -90),
        ("dining_chair_s1", "Dellwood Dining Chair", [4.65, 10.8, 0.008], 90),
        ("dining_chair_s2", "Dellwood Dining Chair", [5.55, 10.8, 0.008], 90),
        ("wfh_desk", "Desk", [5.7, 6.8, 0.008], 90),
        ("wfh_chair", "Dellwood Dining Chair", [5.7, 7.65, 0.008], -90),
        ("entry_cabinet", "Cabinet", [3.05, 12.8, 0.01], 0),
        ("balcony_planter", "Small Garden Planter", [13.8, 11.6, 0.01], 0),
    ]
    result = []
    for identifier, name, position, rotation in choices:
        item = by_name.get(name)
        if not item or not Path(item["usd_path"]).is_file():
            continue
        result.append({"id": identifier, "name": name, "asset_path": item["usd_path"], "position": position, "rotation_deg": rotation, "provenance": "illustrative starter layout; placed in traced B1-1502 rooms"})
    if plan and plan.get('dimension_model'):
        from .dimensioned_b1 import relocate_assets
        result = relocate_assets(result, plan['rooms'])
    return result
