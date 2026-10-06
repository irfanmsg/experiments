# Evaluate outline detection on independent plans

The detector has been developed using the B1 reference and synthetic tests. These
do **not** prove that it works on unseen real drawings. This harness is ready for
independently annotated plans; no independent real-plan accuracy result is claimed.

Use drawings you have permission to use. Include unfurnished and furnished plans,
scans and clean exports, different languages/units, curved balconies, open living
spaces, toilets and service areas. Annotate the original images before inspecting
the detector's results. Keep a separate held-out set that is not used to tune rules.
Record source, permission and annotation provenance in each plan's `source` field.
`dataset_kind: "unseen"` is the evaluator's declaration, not an automated guarantee.

Create a JSON manifest beside the images. Pixel coordinates use the original
image's top-left origin, x right and y down. Trace the inside usable room boundary,
closing doorway gaps at the wall line. Do not include furniture as rooms. Trace
curves with enough vertices to preserve their shape. Shared open-plan areas should
be one region unless the source establishes a dividing boundary. Document ambiguous
boundaries in the source field; use the same convention across the dataset.

This schema example is **synthetic**, not a real drawing or benchmark result:

```json
{
  "dataset_kind": "synthetic",
  "plans": [{
    "id": "example-only",
    "image": "images/example.png",
    "source": "Synthetic example; replace with licensed source and annotation provenance",
    "pixels_per_meter": 100,
    "rooms": [
      {"name": "Kitchen", "pixel_polygon": [[10, 10], [410, 10], [410, 310], [10, 310]]},
      {"name": "Balcony", "pixel_polygon": [[410, 10], [510, 40], [540, 200], [410, 310]]}
    ]
  }]
}
```

`pixels_per_meter` is optional and must be established independently from a known
dimension, not copied from the detector. Images must be files within the manifest
directory (including subdirectories). Self-intersecting, non-finite or out-of-image
polygons are rejected. Rasterize PDFs first and annotate those exact raster images.

From the project directory, after the normal `uv sync` setup:

```bash
uv run --no-sync python -m tools.benchmark_outlines /path/to/dataset/manifest.json --output output/outline-baseline.json
```

The command runs the existing local detector with its normal 60-result limit. It
does not submit images to an LLM or alter project files. The output records the Git
revision/dirty state, detector/evaluator/lockfile hashes, library and OCR versions,
manifest and image hashes, and raw predictions. Use a clean committed checkout for
a baseline. Existing report files cannot be overwritten; choose a new filename for
each subsequent run. Preserve the manifest and images alongside the report.

Each plan reports:

- One-to-one matched, missed and spurious rooms, with indexes into annotations and
  saved predictions. A merged region cannot earn credit for two rooms.
- Precision and recall at intersection-over-union (IoU) ≥ 0.5 by default. Change
  the threshold with `--minimum-iou`; compare runs using the same threshold.
- Each matched pair's IoU and approximate symmetric boundary Hausdorff distance in
  original image pixels (Shapely, segment densification 0.1). Lower distance is better.
- Exact name agreement after case/whitespace normalization, reported separately
  from geometry. Naming differences do not prevent a spatial match.
- Absolute relative scale error when both known and detected scales exist. A null
  predicted scale means detection supplied none, not a zero-error calibration.
- Detector warnings and per-plan failures. Any failure makes the command exit 1;
  inspect the saved error rather than silently excluding the plan.

Matching maximizes the number of valid one-to-one matches using augmenting paths,
trying higher-IoU neighbors first. It does not maximize total IoU among equivalent
matchings; inspect overlapping/ambiguous matches in the saved predictions. Mean
matched IoU excludes misses, so always read it alongside recall and room counts.
Boundary distances in pixels are comparable across plans only at equivalent image
scale. This harness measures outlines and scale, not door connectivity, reconstruction
realism or whether an inferred architectural decision is correct.

The evaluator's runnable check uses deliberately shifted and merged rectangles:

```bash
uv run --no-sync pytest -q tests/test_outline_benchmark.py
```

That verifies the scoring and provenance handling. It is not a substitute for a
separate real-plan evaluation, which still requires licensed images and annotations.
