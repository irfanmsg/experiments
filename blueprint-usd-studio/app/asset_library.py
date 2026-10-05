"""Curated local SimReady library; source pack remains outside this repository."""

from __future__ import annotations

import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASSET_ROOT = Path.home() / "Repos" / "OmniverseAssets"


def _read_catalog(filename: str, root: Path, overlay: Path | None, structure_types: list[str]) -> list[dict]:
    path = ROOT / "data" / filename
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    base = overlay if overlay and overlay.is_dir() else root / Path(data["asset_root"]).name
    base = base.absolute()
    result = []
    for asset in data.get("assets", []):
        full_path = (base / asset["usd_path"]).absolute()
        if not full_path.is_relative_to(root) or not full_path.resolve().is_relative_to(root):
            raise ValueError("Invalid SimReady catalog path")
        if full_path.is_file():
            result.append({**asset, "usd_path": str(full_path), "structure_types": asset.get("structure_types", structure_types)})
    return result


def catalog() -> dict:
    root = Path(os.environ.get("BLUEPRINT_STUDIO_ASSET_ROOT", DEFAULT_ASSET_ROOT)).expanduser().resolve()
    furniture = _read_catalog("simready_catalog.json", root, root / "SimReady_Furniture_Misc_01_overlay", ["home", "office", "showroom", "other"])
    warehouse = _read_catalog("simready_warehouse_catalog.json", root, None, ["factory", "showroom", "other"])
    return {"asset_root": str(root), "assets": furniture + warehouse}


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
    agreement = bool(plan and plan.get('source', {}).get('primary_crop') == 'agreement_unit_crop.jpg')
    if agreement:
        from .geometry import bbox
        rooms = {room['id']: room for room in plan['rooms']}
        if not {'living_dining', 'wfh', 'entry', 'balcony_curved'} <= rooms.keys():
            return []
        x0, y0, x1, y1 = bbox([rooms['living_dining']['polygon']])
        living_x, dining_x, middle_y = x1 - 2.5, x0 + 2.38, (y0 + y1) / 2
        dx0, dy0, dx1, dy1 = bbox([rooms['wfh']['polygon']])
        ex0, ey0, ex1, ey1 = bbox([rooms['entry']['polygon']])
        balcony = rooms['balcony_curved']['polygon']
        planter_x = sum(p[0] for p in balcony) / len(balcony)
        planter_y = sum(p[1] for p in balcony) / len(balcony)
        choices = [
            ('living_sofa', 'Crestwood Sofa', [living_x, y1-.65, .008], -90),
            ('living_table', 'Appleseed Coffee Table', [living_x, y0+1.55, .008], 90),
            ('living_armchair', 'Armchair', [living_x-1.6, y0+1.55, .012], -90),
            ('living_armchair_east', 'Armchair', [living_x+1.5, y0+1.55, .012], 90),
            ('dining_table', 'Dellwood Dining Table', [dining_x, middle_y, .008], 90),
            ('dining_chair_n1', 'Dellwood Dining Chair', [dining_x-.5, middle_y+.96, .008], -90),
            ('dining_chair_n2', 'Dellwood Dining Chair', [dining_x+.5, middle_y+.96, .008], -90),
            ('dining_chair_s1', 'Dellwood Dining Chair', [dining_x-.5, middle_y-.96, .008], 90),
            ('dining_chair_s2', 'Dellwood Dining Chair', [dining_x+.5, middle_y-.96, .008], 90),
            ('dining_chair_w', 'Dellwood Dining Chair', [dining_x-1.38, middle_y, .008], 0),
            ('dining_chair_e', 'Dellwood Dining Chair', [dining_x+1.38, middle_y, .008], 180),
            ('den_sofa', 'Crestwood Sofa', [dx0+.65, (dy0+dy1)/2, .008], 180),
            ('den_cabinet', 'Cabinet', [dx1-.25, (dy0+dy1)/2, .008], 0),
            ('entry_cabinet', 'Cabinet', [(ex0+ex1)/2, ey1-.60, .008], 0),
            ('balcony_planter', 'Small Garden Planter', [planter_x, planter_y, .01], 0),
        ]
    result = []
    for identifier, name, position, rotation in choices:
        item = by_name.get(name)
        if not item or not Path(item["usd_path"]).is_file():
            continue
        result.append({"id": identifier, "name": name, "asset_path": item["usd_path"], "position": position, "rotation_deg": rotation,
                       "provenance": "Furniture grouping and wall placement guided by Layout.jpeg; exact offsets and models are assumed; 0.55 m doorway clearance is a visualization assumption; NVIDIA physical sizes retained" if agreement else "illustrative starter layout; placed in traced B1-1502 rooms"})
    if plan and plan.get('dimension_model') and not agreement:
        from .dimensioned_b1 import relocate_assets
        result = relocate_assets(result, plan['rooms'])
    return result
