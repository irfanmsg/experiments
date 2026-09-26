"""Build the app's curated furniture gallery from the installed SimReady pack."""

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("PXR_USDC_EMIT_DEPRECATION_WARNINGS", "0")
from pxr import Usd, UsdGeom  # noqa: E402


SELECTION = [
    ("Crestwood Sofa", "Living room", "crestwood_sofa"),
    ("Armchair", "Living room", "armchair"),
    ("Appleseed Coffee Table", "Living room", "appleseed_coffeetable"),
    ("Dellwood Dining Table", "Dining", "dellwood_diningtable"),
    ("Dellwood Dining Chair", "Dining", "dellwood_diningchair"),
    ("Bar Stool", "Dining", "bar_stool"),
    ("Desk", "Study", "desk_01"),
    ("Cabinet", "Storage", "cabinet_b01"),
    ("Corner Shelf", "Storage", "cornershelf_square"),
    ("Small Garden Planter", "Decor", "gardenplanter_small"),
    ("Serving Bowl", "Kitchen", "serving_bowl"),
]


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--asset-root",
        type=Path,
        default=Path("/home/ovqa/Repos/OmniverseAssets/SimReady_Furniture_Misc_01"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=project / "data" / "simready_catalog.json",
    )
    args = parser.parse_args()
    asset_root = args.asset_root.resolve()
    props = asset_root / "Assets/simready_content/common_assets/props"

    assets = []
    cache = UsdGeom.BBoxCache(
        Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render]
    )
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
        scale = UsdGeom.GetStageMetersPerUnit(stage)
        size = cache.ComputeWorldBound(prim).ComputeAlignedBox().GetSize()
        xyz = [round(float(axis * scale), 3) for axis in size]
        if any(axis <= 0 for axis in xyz):
            raise RuntimeError(f"Invalid bounds for {path}: {xyz}")
        assets.append(
            {
                "name": name,
                "category": category,
                "usd_path": str(path.relative_to(asset_root)),
                "size_xyz_m": xyz,
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({"asset_root": str(asset_root), "assets": assets}, indent=2) + "\n"
    )
    print(f"Indexed {len(assets)} assets in {args.output}")


if __name__ == "__main__":
    main()
