# Interior schemes from the saved Design collection

The user explicitly requested Instagram browser references for generating styles. The existing signed-in desktop browser successfully opened the exact saved collection. Three representative posts were inspected; this is not an exhaustive collection audit.

Implement three coherent, illustrative schemes using the existing USD builder:

- `saved_linen_timber`: Linen & light timber, from `DclJJ7wmeQX`.
- `saved_evening_lounge`: Warm evening lounge, from `Dce9CWFqgnn`.
- `saved_botanical_cane`: Botanical cane & terracotta, from `DYi4XJVod1V`.

Keep documented floor classes, room dimensions, door access and real asset size. Add metric rugs, curtains, art, modeled lamps and real lights, plants and small decor; change scene-local upholstery and cabinetry finishes. Trace exact design references and every unprinted size/placement/light choice as illustrative. Reference images are not measured apartment geometry and their authenticity is not established.

Reuse existing helpers and radio controls. Separate complete interior schemes from finish presets. Capture previews from this actual layout in the GPU renderer and bind them to the saved plan fingerprint; clear stale previews after edits.

- [x] Renderer agent: schemes, fitted decor, trace and meaningful geometry/material checks.
- [x] Frontend agent: grouped choices, features/references, actual scene thumbnails and edit invalidation.
- [x] Root: preview API, current-plan fingerprint guard, editor/4K Playwright and visual inspection.
- [x] Root: checkpoint commit with Irfan author identity and leave the selected scheme running.

Verified 6 October 2026: 58 automated tests pass. All three schemes decoded at 3840×2160 with physics enabled in Playwright; orbit, first drag after blur, top/room/eye-level views, zoom, reset, full screen and mobile layout passed. Reviewed rendered living, kitchen, bedroom and bathroom views. Three distinct actual-layout PNG previews load in the editor, keyboard selection works, and unsaved edits invalidate previews without altering the saved plan. Editor furniture placement/export retains physical dimensions.

Native RTX ignores the authored double-sided flag for this ceiling use. A small GPU probe verified the native visibility column; the viewer switches ceiling visibility with camera mode. Ceiling infill and room lighting remain explicitly assumed. Deleting rooms referenced by a scheme returns an actionable error before overwriting an existing export.
