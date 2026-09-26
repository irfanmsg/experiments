# B1-1502 traced plan

`plan.json` is a metre-based 2D trace of the 15th-floor unit in B1. Its
coordinates use X to the right and Y upward in the upright architectural
sheet; the floor is Z=0 until an elevation is supplied.

The room labels and dimensions come from `B1-Building-3.pdf`, PDF page 1,
approved sheet 63/69 dated 22 April 2024. The unit boundary is corroborated
by the red B1-1502 outline in `Miami PWC House Documents.pdf`, PDF page 35.
The RERA area schedule on `B1-Building-1.pdf`, PDF page 1 gives 172.00 m²
carpet + 32.72 m² balcony + 3.05 m² dry balcony = 207.77 m² total.
The raster-traced outline measures 207.96 m² at 60.4 pixels/metre.

Room dimension values in JSON are printed source facts. Wall vertices and
door positions are approximate raster traces, typically within 0.15–0.25 m;
the scan has skew and folds. No source here specifies wall thickness, ceiling
height, door width or floor elevation. The 2.80 m visualization height and
individual wall thicknesses are marked as assumptions in the data.
Door and sliding-door symbols are represented as estimated gaps in the wall
runs, with illustrative jambs and lintels. Glazing frames and balcony railings
are illustrative assemblies; the generated scene does not claim exact leaf,
frame, or railing specifications. The September viewer review added omitted
service-toilet, dry-balcony, kitchen, and north-toilet partitions and door gaps.
These measurements should be confirmed on site before construction or fit-out.

`approved_crop.jpg` shows the source geometry. `agreement_unit_crop.jpg`
contains only the marked unit, without the rest of the registered document.
`trace_overlay.jpg` is the original tracing snapshot. The live viewer's
**Drawing + walls** comparison displays the current reconstruction over the scan.
Run `python3 trace.py` to rebuild `plan.json` from the annotated raster
coordinates in that script, then rebuild the USD from the regenerated JSON.
