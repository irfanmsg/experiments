# B1-1502 worked example

This fixture exercises Blueprint Studio's measured reconstruction and evidence-review workflow. It is not the product's only intended layout. The current model is **`b1-agreement-dimensions-v3`**: 21 spaces and 24 openings, in metres with Z up.

## Source authority

**Miami PWC House Documents.pdf, page 35, Annexure G** is the primary geometry source because it specifically demarcates B1-1502. **Page 28, Annexure F** supplies the finish schedule. The approved typical-floor drawing (`B1-Building-3.pdf`, sheet 63/69) is a comparison source, not the controlling apartment layout. It differs in the powder room and some door connections; revision supersession and the actual built state remain unverified.

The [reference manifest](reference_manifest.json) records the supplied documents and images, checksums, page references, roles and unresolved questions. [Source comparisons](source_comparison.json) retain differences from the furnished brochure and convert its feet/inches measurements explicitly. The eleven construction-folder images include eight construction exteriors and three builder site-model views; their tower/unit identity and metric calibration are unknown. See [the photo review](../../docs/construction-photo-review.md).

## Geometry and assumptions

Printed agreement dimensions constrain the clear spans of 19 rectangular spaces and the labelled span/average depth of two irregular balconies. The powder room is included, and the toilet beside the upper bedroom connects directly to that bedroom. Walls sit outside clear room boundaries, shared wall solids are deduplicated and door openings cut through them.

One USD unit equals one metre. Room dimensions do not change when the raster calibration changes. The kitchen, for example, remains 2.75 × 4.12 m. Furniture imports retain physical size when source units and up-axis are converted.

Wall thickness (0.15 m), height (2.8 m), relative offsets and some alignments remain assumptions. The cropped main balcony arc is completed using the approved comparison contour as an explicitly recorded prior. It is not an exact surveyed perimeter.

The source area schedule is **172.00 + 32.72 + 3.05 = 207.77 m²**. The current inferred gross footprint is approximately **224.02 m²**, while the agreement raster trace is approximately **211.51 m²**. These measures use different boundaries and uncertain registration. The model does not globally shrink rooms to make them agree. The editor's live scale audit recomputes measurements from the current geometry.

Specified flooring categories remain separate from decorative choices: wood in the master bedroom, vitrified tile in other dry spaces and matte tile in wet spaces. Exact fixture models, colours, tile selection, lighting and decorative placement remain illustrative. [The interior reference ledger](../../docs/interior-references.md) records style observations and proposed applications.

## Files and regeneration

- `plan.json` contains the dimension-driven model and reconstruction metadata.
- `raster_trace.json` preserves the earlier approximate pixel trace for comparison.
- `agreement_unit_crop.jpg` is the active source image; `approved_crop.jpg` and `trace_overlay.jpg` retain earlier comparison material.
- `reference_manifest.json`, `source_comparison.json` and `construction_photo_review.json` preserve source roles and review evidence.

Run from the project root:

```bash
.venv/bin/python data/b1_1502/trace.py
.venv/bin/python build_b1_1502.py
```

The trace script rebuilds fixture data; the build script exports USD and a style pack under `output/b1-1502/`. In the application, **Review reconstruction assumptions**, **Source drawing** and **Download reconstruction trace** expose the measurements, opening evidence and inferred decisions. The source comparison does not imply that one pixel scale can register a dimension-corrected model perfectly onto a distorted scan.

Unedited older raster/v1 examples migrate to v3 with furniture moved relative to its room, preserving object size and rotation. Saved v2 examples remain preserved with an older-reconstruction notice. Modified older geometry is protected from automatic replacement; open a fresh example to compare the corrected reconstruction.
