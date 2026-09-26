"""Index representative warehouse props from NVIDIA's SimReady Warehouse 01 pack."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("PXR_USDC_EMIT_DEPRECATION_WARNINGS", "0")
from pxr import Usd, UsdGeom  # noqa: E402


SELECTION = [
    ("Aluminum Step Stand", "Factory access", "aluminumstepstand_a01"),
    ("Bulk Storage Rack", "Storage", "bulkstoragerack_a01"),
    ("Dock Board", "Loading", "dockboard_a01"),
    ("Heavy Duty Steel Shelving", "Storage", "heavydutysteelshelving_a01"),
    ("Industrial Steel Shelving", "Storage", "industrialsteelshelving_a01"),
    ("Open Industrial Shelving", "Storage", "openindustrialsteelshelving_a01"),
    ("Wire Shelving", "Storage", "wireshelving_a01"),
    ("Metal Fencing", "Safety", "metalfencing_a1"),
    ("Long Ramp", "Factory access", "ramplong_a1"),
    ("Short Ramp", "Factory access", "rampshort_a1"),
    ("Recycled Wood Pallet", "Handling", "recycledwoodpallet_a01"),
    ("Stationary Work Platform", "Factory access", "stationaryworkplatform_a01"),
    ("Tilt and Roll Ladder", "Factory access", "tiltandrollladder_a01"),
    ("Tire Rack System", "Storage", "tireracksystem_a01"),
]


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    base = Path(os.environ.get("BLUEPRINT_STUDIO_ASSET_ROOT", "/home/ovqa/Repos/OmniverseAssets"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-root", type=Path, default=base / "SimReady_Warehouse_01_overlay")
    parser.add_argument("--output", type=Path,
                        default=project / "data/simready_warehouse_catalog.json")
    args = parser.parse_args()
    asset_root = args.asset_root.resolve()
    props = asset_root / "Assets/simready_content/common_assets/props"

    assets = []
    purposes = [UsdGeom.Tokens.default_, UsdGeom.Tokens.render]
    for name, category, slug in SELECTION:
        path = props / slug / f"{slug}.usd"
        if not path.is_file():
            raise FileNotFoundError(path)
        stage = Usd.Stage.Open(str(path))
        if not stage:
            raise RuntimeError(f"Could not open USD asset: {path}")
        prim = stage.GetDefaultPrim()
        if not prim:
            raise RuntimeError(f"No default prim: {path}")
        bounds = UsdGeom.BBoxCache(Usd.TimeCode.Default(), purposes)
        size = bounds.ComputeWorldBound(prim).ComputeAlignedBox().GetSize()
        scale = UsdGeom.GetStageMetersPerUnit(stage)
        xyz = [round(float(axis * scale), 3) for axis in size]
        if any(axis <= 0 for axis in xyz):
            raise RuntimeError(f"Invalid bounds for {path}: {xyz}")
        assets.append({
            "name": name,
            "category": category,
            "usd_path": str(path.relative_to(asset_root)),
            "size_xyz_m": xyz,
        })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"asset_root": str(asset_root), "assets": assets},
                                      indent=2) + "\n")
    print(f"Indexed {len(assets)} warehouse assets in {args.output}")


if __name__ == "__main__":
    main()
