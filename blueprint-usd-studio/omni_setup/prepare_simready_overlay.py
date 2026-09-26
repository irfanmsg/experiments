"""Create a local SimReady view with the MDL dependency missing from the pack.

The NVIDIA archive remains untouched. Large asset directories are symlinked into
an adjacent overlay, while its small MDL directory is copied and completed with
the ``baking_annotations.mdl`` module bundled in the installed ovrtx wheel.
"""

from __future__ import annotations

import argparse
import filecmp
import importlib.util
import os
from pathlib import Path
import shutil


PACK_NAME = "SimReady_Furniture_Misc_01"
OVERLAY_NAME = PACK_NAME + "_overlay"
DEFAULT_SAMPLE = Path(
    "Assets/simready_content/common_assets/props/crestwood_sofa/crestwood_sofa.usd"
)


def _link(source: Path, destination: Path) -> None:
    """Add a relative symlink, refusing to replace an unexpected existing item."""
    if not source.exists():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    target = Path(os.path.relpath(source, destination.parent))
    if destination.is_symlink():
        if destination.readlink() != target:
            raise FileExistsError(f"Unexpected existing symlink: {destination}")
        return
    if destination.exists():
        raise FileExistsError(f"Expected a symlink at: {destination}")
    destination.symlink_to(target, target_is_directory=source.is_dir())


def _real_directory(path: Path) -> None:
    if path.is_symlink():
        raise FileExistsError(f"Overlay directory must not be a symlink: {path}")
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise NotADirectoryError(path)


def _copy(source: Path, destination: Path) -> None:
    """Copy once and reject an existing file whose contents differ."""
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        if (destination.is_symlink() or not destination.is_file()
                or not filecmp.cmp(source, destination, shallow=False)):
            raise FileExistsError(f"Unexpected existing file: {destination}")
        return
    shutil.copy2(source, destination)


def _ovrtx_base() -> Path:
    spec = importlib.util.find_spec("ovrtx")
    if spec is None or spec.origin is None:
        raise RuntimeError("ovrtx is not installed; run omni_setup/setup.sh runtime")
    return Path(spec.origin).parent / "bin/library/mdl/Base"


def prepare(source: Path, overlay: Path, ovrtx_base: Path,
            sample_asset: Path = DEFAULT_SAMPLE) -> None:
    source = source.expanduser().resolve(strict=True)
    overlay = Path(os.path.abspath(overlay.expanduser()))
    resolved_location = overlay.parent.resolve(strict=False) / overlay.name
    if (resolved_location == source or source in resolved_location.parents
            or resolved_location in source.parents):
        raise ValueError("Overlay and extracted pack must be separate directories")
    if overlay.is_symlink():
        raise ValueError("Overlay root must not be a symlink")
    if sample_asset.is_absolute() or ".." in sample_asset.parts:
        raise ValueError("Sample asset must be a relative path inside the pack")
    content = source / "Assets/simready_content"
    vendor_materials = content / "materials"
    if not vendor_materials.is_dir():
        raise FileNotFoundError(vendor_materials)

    _real_directory(overlay)
    _real_directory(overlay / "Assets")
    overlay_content = overlay / "Assets/simready_content"
    _real_directory(overlay_content)
    # Keep every vendor dependency available without duplicating the 12 GB pack.
    for child in source.iterdir():
        if child.name != "Assets":
            _link(child, overlay / child.name)
    for child in (source / "Assets").iterdir():
        if child.name != "simready_content":
            _link(child, overlay / "Assets" / child.name)
    for child in content.iterdir():
        if child.name != "materials":
            _link(child, overlay_content / child.name)

    overlay_materials = overlay_content / "materials"
    _real_directory(overlay_materials)
    for item in vendor_materials.iterdir():
        if item.is_file() and item.suffix.lower() == ".mdl":
            _copy(item, overlay_materials / item.name)
        else:
            _link(item, overlay_materials / item.name)
    missing = overlay_materials / "baking_annotations.mdl"
    if not (vendor_materials / missing.name).exists():
        _copy(ovrtx_base / missing.name, missing)

    sample = overlay / sample_asset
    if not sample.is_file():
        raise FileNotFoundError(sample)
    print(f"SimReady overlay ready: {overlay}")
    print(f"Verified sample asset: {sample}")
    print(f"Completed MDL directory: {overlay_materials}")


def main() -> None:
    base = Path(os.environ.get("BLUEPRINT_STUDIO_ASSET_ROOT", "/home/ovqa/Repos/OmniverseAssets"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=base / PACK_NAME)
    parser.add_argument("--overlay", type=Path, default=base / OVERLAY_NAME)
    parser.add_argument("--ovrtx-mdl-base", type=Path, default=None)
    parser.add_argument("--sample-asset", type=Path, default=DEFAULT_SAMPLE)
    args = parser.parse_args()
    prepare(args.source, args.overlay, args.ovrtx_mdl_base or _ovrtx_base(),
            args.sample_asset)


if __name__ == "__main__":
    main()
