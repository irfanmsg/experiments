# B1-1502 dimensioned plan

`plan.json` contains the meter-based reconstruction. `raster_trace.json`
preserves the original approximate pixel trace for source comparisons.
Run `python data/b1_1502/trace.py` from the project root to rebuild both.

The approved source is `B1-Building-3.pdf`, PDF page 1, sheet 63/69 dated
22 April 2024. The agreement outline identifies B1-1502. The room dimensions
in that approved sheet drive the clear room boundaries, independently of
raster calibration. Walls sit outside those boundaries; shared solids and
openings are generated from room adjacency.

There are 18 rectangular spaces and two irregular balconies. Rectangles use
the printed clear width and length. Irregular balconies use the labelled span
and average depth (area divided by span), with a provisional curve/slope.
The exact curve, wall thickness, height and relative alignment are not
established by the room labels. The layout uses 0.15 m partitions and 2.8 m
wall height as assumptions, clearly distinct from the constrained dimensions.

Pages 32–35 of `Sales Presenter Mergred Web.pdf` were reviewed. Page 32 shows
the detailed type-02/05 apartment in feet/inches; page 33 is the typical floor.
Pages 34 and 35 describe first/refuge floors, not floor 15. See
[source_comparison.json](source_comparison.json) for unit conversions and
source differences. The approved metric values remain primary.

The 172.00 + 32.72 + 3.05 = 207.77 m² source schedule is retained, not used
as a scaling factor. The generated gross footprint is about 222.45 m² and
includes assumed wall construction and balcony geometry. It is not equivalent
to the source net-area schedule. Matching total area alone cannot validate
individual room dimensions.

`approved_crop.jpg`, `agreement_unit_crop.jpg`, and `trace_overlay.jpg` remain
source images. The live **Source drawing** view shows the original raster
trace over the scan. The editor shows the corrected geometry on a 1-meter
grid; it does not pretend that a single pixel scale registers the corrected
layout onto the distorted scan.
