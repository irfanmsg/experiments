#!/usr/bin/env python3
"""Regenerate the reviewed B1-1502 OpenUSD deliverables."""

from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from pxr import Usd

from app.asset_library import b1_starter_furniture
from app.usd_builder import build_style_variants


ROOT = Path(__file__).resolve().parent
source = ROOT / "data/b1_1502/plan.json"
plan = json.loads(source.read_text())
plan["structure_type"] = "home"
destination = ROOT / "output/b1-1502"
result = build_style_variants(plan, destination)
stage = Usd.Stage.Open(str(destination / "contemporary.usda"))
binary = destination / "B1-1502.usd"
stage.Export(str(binary))
placements = b1_starter_furniture(plan)
if placements:
    from app.usd_builder import build_usd
    furnished_plan = {**plan, "asset_placements": placements}
    furnished_text = destination / "B1-1502-furnished.usda"
    build_usd(furnished_plan, furnished_text, "contemporary")
    Usd.Stage.Open(str(furnished_text)).Export(str(destination / "B1-1502-furnished.usd"))
with ZipFile(destination / "B1-1502-style-pack.zip", "w", compression=ZIP_DEFLATED) as archive:
    archive.write(destination / "all_styles.usda", "all_styles.usda")
    for style in result["styles"]:
        archive.write(destination / f"{style}.usda", f"{style}.usda")
print(f"B1-1502 USD: {binary}")
print(f"B1-1502 style pack: {destination / 'B1-1502-style-pack.zip'}")
print(f"Styles: {', '.join(result['styles'])}")
if placements:
    print(f"SimReady furnished scene: {destination / 'B1-1502-furnished.usd'} ({len(placements)} objects)")
