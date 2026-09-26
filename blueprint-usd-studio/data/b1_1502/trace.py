"""Rebuild the B1-1502 metric trace from the approved plan's raster coordinates.

The source PDFs stay outside this repository.  This script contains only the
manually reviewed unit trace, and emits plan.json beside itself.  Metric room
labels come from the drawing; polygon vertices are estimates from its scan.
"""

from __future__ import annotations

import json
from pathlib import Path


# Coordinates below are local to approved_crop.jpg, cut from image pixels
# x=2500..4200 and y=1550..3300 of B1-Building-3.pdf page 1.
# Five printed room dimensions give 59.6..60.9 pixels per metre.  60.4 is
# the median-scale approximation.  The scan has paper folds and mild skew.
PIXELS_PER_METRE = 60.4
ORIGIN_PX = (742, 1681)


def metric(point: tuple[int, int]) -> list[float]:
    return [
        round((point[0] - ORIGIN_PX[0]) / PIXELS_PER_METRE, 3),
        round((ORIGIN_PX[1] - point[1]) / PIXELS_PER_METRE, 3),
    ]


def path(points: list[tuple[int, int]]) -> list[list[float]]:
    return [metric(point) for point in points]


FOOTPRINT_PX = [
    (742, 349), (885, 352), (885, 481), (1191, 499),
    (1191, 610), (1260, 611), (1261, 561), (1417, 568),
    (1418, 641), (1518, 675), (1560, 744), (1599, 833),
    (1628, 923), (1640, 1011), (1633, 1098), (1614, 1182),
    (1575, 1269), (1512, 1354), (1424, 1350), (1419, 1447),
    (1265, 1447), (1265, 1514), (1169, 1514), (1169, 1362),
    (1096, 1362), (1096, 1516), (990, 1619), (755, 1681),
    (755, 1554), (770, 1554), (770, 1226), (897, 1226),
    (897, 1096), (814, 1096), (814, 928), (907, 928),
    (907, 844), (814, 844), (814, 671), (815, 590),
    (742, 590),
]


# id, display name, category, printed dimensions (metres), plan trace pixels,
# and any qualifiers on the printed dimensions.  Named spaces cover the unit;
# hallways are open connections, so small unassigned slivers are intentional.
ROOMS_PX = [
    ("service_wc", "Service toilet", "bathroom", [2.14, 1.22],
     [(744, 352), (881, 354), (880, 427), (743, 426)], None),
    ("service_room", "Service room", "service", [2.14, 2.51],
     [(743, 430), (879, 430), (879, 586), (742, 585)], None),
    ("dry_balcony", "Dry balcony", "balcony", [1.93, 1.70],
     [(883, 486), (991, 492), (990, 592), (881, 588)], None),
    ("kitchen_balcony", "Kitchen balcony", "balcony", [2.98, 1.70],
     [(995, 492), (1185, 500), (1183, 598), (993, 592)], None),
    ("kitchen", "Kitchen", "kitchen", [2.75, 4.12],
     [(817, 599), (979, 603), (978, 844), (817, 841)], None),
    ("bedroom_north", "Bedroom beside kitchen", "bedroom", [3.05, 4.03],
     [(983, 604), (1168, 608), (1166, 850), (980, 846)], None),
    ("bathroom_north", "Toilet beside upper bedroom", "bathroom", [1.39, 2.46],
     [(1173, 608), (1258, 611), (1255, 758), (1171, 756)], None),
    ("bathroom_outer_north", "Outer upper toilet", "bathroom", [2.40, 1.52],
     [(1267, 564), (1417, 568), (1415, 660), (1265, 656)], None),
    ("bedroom_outer_north", "Outer upper bedroom", "bedroom", [3.96, 3.40],
     [(1262, 668), (1501, 681), (1495, 869), (1258, 862)], None),
    ("entry", "Entry lobby", "entry", [1.65, 2.676],
     [(815, 931), (913, 934), (909, 1092), (815, 1088)], None),
    ("living_dining", "Living and dining", "living", [9.83, 4.03],
     [(907, 862), (1251, 865), (1495, 878), (1481, 1109),
      (905, 1093)], "open plan; polygon follows visible bounding walls"),
    ("balcony_curved", "Curved living balcony", "balcony", [2.40, 11.07],
     [(1499, 681), (1518, 675), (1560, 744), (1599, 833),
      (1628, 923), (1640, 1011), (1633, 1098), (1614, 1182),
      (1575, 1269), (1512, 1354), (1472, 1345), (1481, 1109),
      (1495, 878)], "2.40 m is marked average balcony depth"),
    ("passage", "Interior passage", "corridor", [1.78, 2.13],
     [(901, 1099), (998, 1102), (998, 1221), (898, 1221)], None),
    ("wfh", "Work from home room", "work", [3.05, 3.58],
     [(1002, 1106), (1185, 1110), (1185, 1324), (1000, 1320)],
     "called theatre/den on agreement copy"),
    ("bedroom_outer_south", "Outer lower bedroom", "bedroom", [4.65, 3.65],
     [(1191, 1113), (1479, 1118), (1472, 1337), (1189, 1328)], None),
    ("bathroom_outer_south", "Outer lower toilet", "bathroom", [2.38, 1.52],
     [(1268, 1349), (1417, 1351), (1416, 1442), (1266, 1441)], None),
    ("walk_in", "Walk-in closet", "closet", [1.45, 2.90],
     [(1174, 1343), (1264, 1350), (1264, 1509), (1174, 1504)], None),
    ("bathroom_south", "Lower internal toilet", "bathroom", [1.52, 2.90],
     [(1001, 1327), (1095, 1332), (1094, 1504), (1000, 1499)], None),
    ("bedroom_south", "Lower internal bedroom", "bedroom", [3.58, 4.55],
     [(778, 1230), (998, 1233), (999, 1498), (778, 1500)], None),
    ("balcony_south", "Lower bedroom balcony", "balcony", [3.58, 2.45],
     [(755, 1554), (779, 1503), (990, 1504), (990, 1619),
      (755, 1681)], "2.45 m is marked average balcony depth"),
]


# Only visible/structural wall runs are listed.  Door gaps are kept open where
# visible; most individual leaf widths are not dimensioned in the PDF.
# Heights/thicknesses are visualization assumptions, never measured source data.
WALLS_PX = [
    ("service_toilet_divider", (742, 429), (827, 430), "partition", 0.15),
    ("service_kitchen_upper", (879, 430), (879, 489), "partition", 0.15),
    ("service_kitchen_lower", (879, 541), (879, 585), "partition", 0.15),
    ("dry_balcony_divider", (992, 492), (991, 594), "partition", 0.15),
    ("kitchen_north_left", (814, 595), (882, 597), "partition", 0.15),
    ("kitchen_north_right", (940, 599), (980, 600), "partition", 0.15),
    ("kitchen_bedroom", (980, 603), (978, 844), "partition", 0.15),
    ("bedroom_toilet_upper", (1169, 608), (1170, 756), "partition", 0.15),
    ("bedroom_east_above_door", (1170, 756), (1167, 788), "partition", 0.15),
    ("bedroom_east_below_door", (1167, 840), (1167, 853), "partition", 0.15),
    ("north_toilet_south", (1170, 756), (1207, 758), "partition", 0.15),
    ("north_toilet_east", (1258, 611), (1257, 666), "partition", 0.15),
    ("outer_north_toilet_south", (1317, 663), (1417, 668), "partition", 0.15),
    ("upper_bedroom_south", (980, 850), (1167, 853), "partition", 0.15),
    ("outer_upper_bedroom_south_1", (1258, 865), (1346, 868), "partition", 0.15),
    ("outer_upper_bedroom_south_2", (1408, 871), (1495, 876), "partition", 0.15),
    ("outer_upper_bedroom_west", (1257, 666), (1254, 807), "partition", 0.15),
    ("living_south_left", (905, 1093), (959, 1096), "partition", 0.15),
    ("living_south_mid", (1015, 1099), (1138, 1101), "partition", 0.15),
    ("living_south_right", (1251, 1106), (1482, 1112), "partition", 0.15),
    ("passage_wfh", (999, 1104), (1000, 1304), "partition", 0.15),
    ("wfh_bedroom", (1187, 1112), (1186, 1293), "partition", 0.15),
    # This bedroom opens directly from the passage beside the fire lift.
    ("south_bedroom_bath", (999, 1328), (999, 1500), "partition", 0.15),
    ("wfh_bath", (1000, 1325), (1096, 1328), "partition", 0.15),
    ("walkin_bedroom", (1171, 1336), (1263, 1345), "partition", 0.15),
    ("walkin_bath", (1265, 1345), (1265, 1509), "partition", 0.15),
    ("outer_lower_bedroom_bath", (1267, 1347), (1417, 1349), "partition", 0.15),
    ("living_balcony_glazing_upper", (1496, 682), (1493, 905), "glazed_exterior", 0.10),
    ("living_balcony_glazing_mid", (1489, 1023), (1483, 1162), "glazed_exterior", 0.10),
    ("living_balcony_glazing_lower", (1479, 1251), (1472, 1344), "glazed_exterior", 0.10),
    ("south_balcony_glazing_left", (779, 1500), (853, 1501), "glazed_exterior", 0.10),
    ("south_balcony_glazing_right", (947, 1502), (990, 1504), "glazed_exterior", 0.10),
    ("kitchen_balcony_glazing", (994, 592), (1070, 594), "glazed_exterior", 0.10),
    ("curved_balcony_guard_1", (1518, 675), (1560, 744), "balcony_guard", 0.08),
    ("curved_balcony_guard_2", (1560, 744), (1599, 833), "balcony_guard", 0.08),
    ("curved_balcony_guard_3", (1599, 833), (1628, 923), "balcony_guard", 0.08),
    ("curved_balcony_guard_4", (1628, 923), (1640, 1011), "balcony_guard", 0.08),
    ("curved_balcony_guard_5", (1640, 1011), (1633, 1098), "balcony_guard", 0.08),
    ("curved_balcony_guard_6", (1633, 1098), (1614, 1182), "balcony_guard", 0.08),
    ("curved_balcony_guard_7", (1614, 1182), (1575, 1269), "balcony_guard", 0.08),
    ("curved_balcony_guard_8", (1575, 1269), (1512, 1354), "balcony_guard", 0.08),
    ("south_balcony_guard_1", (755, 1681), (990, 1619), "balcony_guard", 0.08),
    ("south_balcony_guard_2", (990, 1619), (990, 1504), "balcony_guard", 0.08),
]


# Shared stair/lift core and external room edges of the agreement's red trace.
# Balcony parapets follow the perimeter only where a full-height wall would
# incorrectly close the terrace.  Full-height glazing is traced above.
BOUNDARY_WALLS_PX = [
    ("service_top_exterior", (742, 349), (885, 352), "exterior", 0.20),
    ("service_east_exterior", (885, 352), (885, 481), "exterior", 0.20),
    ("service_balcony_guard", (885, 481), (1191, 499), "balcony_guard", 0.08),
    ("balcony_duct_edge", (1191, 499), (1191, 610), "exterior", 0.20),
    ("north_toilet_notch_1", (1191, 610), (1260, 611), "exterior", 0.20),
    ("north_toilet_notch_2", (1260, 611), (1261, 561), "exterior", 0.20),
    ("north_toilet_outer_1", (1261, 561), (1417, 568), "exterior", 0.20),
    ("north_toilet_outer_2", (1417, 568), (1418, 641), "exterior", 0.20),
    ("north_balcony_transition", (1418, 641), (1518, 675), "balcony_guard", 0.08),
    ("south_balcony_transition", (1512, 1354), (1424, 1350), "balcony_guard", 0.08),
    ("south_toilet_outer_1", (1424, 1350), (1419, 1447), "exterior", 0.20),
    ("south_toilet_outer_2", (1419, 1447), (1265, 1447), "exterior", 0.20),
    ("walkin_outer_1", (1265, 1447), (1265, 1514), "exterior", 0.20),
    ("walkin_outer_2", (1265, 1514), (1169, 1514), "exterior", 0.20),
    ("south_void_east", (1169, 1514), (1169, 1362), "exterior", 0.20),
    ("south_void_north", (1169, 1362), (1096, 1362), "exterior", 0.20),
    ("south_void_west", (1096, 1362), (1096, 1516), "exterior", 0.20),
    ("south_void_diagonal", (1096, 1516), (990, 1619), "balcony_guard", 0.08),
    ("south_balcony_west_guard", (755, 1681), (755, 1554), "balcony_guard", 0.08),
    ("south_balcony_north_guard", (755, 1554), (770, 1554), "balcony_guard", 0.08),
    ("south_party_1", (770, 1554), (770, 1226), "party_wall", 0.20),
    ("south_party_2", (770, 1226), (897, 1226), "party_wall", 0.20),
    ("south_party_3", (897, 1226), (897, 1096), "party_wall", 0.20),
    ("entry_party_south", (897, 1096), (814, 1096), "party_wall", 0.20),
    ("entry_party_west_lower", (814, 1096), (814, 1020), "party_wall", 0.20),
    ("entry_party_west_upper", (814, 964), (814, 928), "party_wall", 0.20),
    ("entry_party_north", (814, 928), (907, 928), "party_wall", 0.20),
    ("lv_duct_east", (907, 928), (907, 844), "party_wall", 0.20),
    ("lv_duct_north", (907, 844), (814, 844), "party_wall", 0.20),
    ("kitchen_party_west", (814, 844), (814, 671), "party_wall", 0.20),
    ("gc_party_east", (814, 671), (815, 590), "party_wall", 0.20),
    ("gc_party_north", (815, 590), (742, 590), "party_wall", 0.20),
    ("service_party_west", (742, 590), (742, 349), "party_wall", 0.20),
]


# The original page identifies doors (D) and sliders (SD), but their openings
# are not dimensioned.  Widths and placements below are trace estimates.
OPENINGS_PX = [
    ("service_wc_door", "door", (827, 430), (879, 430), "service_wc", 0.86),
    ("service_room_door", "door", (879, 489), (879, 541), "service_room", 0.86),
    ("kitchen_dry_balcony_door", "door", (882, 597), (940, 599), "dry_balcony", 0.96),
    ("north_toilet_door", "door", (1207, 758), (1255, 760), "bathroom_north", 0.79),
    ("outer_north_toilet_door", "door", (1265, 660), (1317, 663), "bathroom_outer_north", 0.86),
    ("main_entry", "door", (814, 964), (814, 1020), "entry", 0.93),
    ("north_bedroom_door", "door", (1167, 788), (1167, 840), "bedroom_north", 0.86),
    ("outer_north_bedroom_door", "door", (1346, 868), (1408, 871), "bedroom_outer_north", 1.03),
    ("passage_to_south_bedroom", "opening", (897, 1226), (998, 1231), "bedroom_south", 1.67),
    ("passage_opening", "opening", (959, 1096), (1015, 1099), "passage", 0.93),
    ("wfh_door", "door", (1138, 1101), (1195, 1104), "wfh", 0.94),
    ("outer_lower_bedroom_door", "door", (1195, 1104), (1251, 1106), "bedroom_outer_south", 0.93),
    ("living_balcony_slider", "sliding_door", (1493, 905), (1489, 1023), "balcony_curved", 1.96),
    ("lower_balcony_slider", "sliding_door", (853, 1501), (947, 1502), "balcony_south", 1.56),
    ("kitchen_balcony_slider", "sliding_door", (1070, 594), (1171, 598), "kitchen_balcony", 1.67),
]


def polygon_area(points: list[list[float]]) -> float:
    return abs(sum(
        points[i][0] * points[(i + 1) % len(points)][1]
        - points[(i + 1) % len(points)][0] * points[i][1]
        for i in range(len(points))
    )) / 2


def main() -> None:
    rooms = []
    for ident, name, category, dimensions, pixels, note in ROOMS_PX:
        room = {
            "id": ident,
            "name": name,
            "category": category,
            "polygon": path(pixels),
            "dimensions_m": dimensions,
            "confidence": "printed dimensions; approximate raster geometry",
            "dimension_provenance": "printed label on approved sheet",
            "geometry_provenance": "manual trace of approved raster, checked against agreement outline",
            "geometry_uncertainty_m": 0.15 if category != "balcony" else 0.25,
        }
        if note:
            room["dimension_note"] = note
        rooms.append(room)

    walls = []
    for ident, start, end, kind, thickness in WALLS_PX + BOUNDARY_WALLS_PX:
        walls.append({
            "id": ident,
            "start": metric(start),
            "end": metric(end),
            "kind": kind,
            "confidence": "approximate raster trace",
            "height_m": 1.10 if kind == "balcony_guard" else 2.80,
            "thickness_m": thickness,
            "geometry_provenance": "manual trace of approved raster",
            "geometry_uncertainty_m": 0.20,
            "height_thickness_provenance": "visualization assumption; not specified by the plan",
        })

    openings = []
    for ident, typ, start, end, space_id, width in OPENINGS_PX:
        openings.append({
            "id": ident,
            "type": typ,
            "start": metric(start),
            "end": metric(end),
            "center": metric(((start[0] + end[0]) // 2, (start[1] + end[1]) // 2)),
            "space_id": space_id,
            "width_m": width,
            "free_opening": True,
            "confidence": "estimated from D/SD symbol",
            "width_provenance": "estimated from scanned D/SD symbol; not dimensioned",
            "geometry_uncertainty_m": 0.20,
        })

    footprint = path(FOOTPRINT_PX)
    plan = {
        "schema_version": "1.0",
        "id": "b1_1502",
        "name": "PWC Miami B1-1502",
        "units": "m",
        "room_height_m": 2.80,
        "height_status": "assumed from visualization; not on approved drawing",
        "coordinate_system": {
            "x": "right in upright approved drawing",
            "y": "up in upright approved drawing",
            "origin": "approved crop pixel (742, 1681), near south-west balcony corner",
            "z": "floor plane; elevation and storey height not given in source",
        },
        "source": {
            "approved_plan": "/home/ovqa/Repos/PWC_Flat_Blueprints/B1-Building-3.pdf#page=1",
            "agreement_highlight": "/home/ovqa/Repos/PWC_Flat_Blueprints/Miami PWC House Documents.pdf#page=35",
            "area_schedule": "/home/ovqa/Repos/PWC_Flat_Blueprints/B1-Building-1.pdf#page=1",
            "approved_crop": "approved_crop.jpg",
            "agreement_unit_crop": "agreement_unit_crop.jpg",
            "approved_sheet_number": "63/69",
            "approved_sheet_date": "2024-04-22",
            "approved_plan_scale": "1:100 (printed); raster re-calibrated with dimensions",
            "floor": 15,
            "unit": "02",
        },
        "calibration": {
            "approved_image_size_px": [4962, 3658],
            "crop_image_size_px": [1700, 1750],
            "crop_origin_in_approved_image_px": [2500, 1550],
            "origin_in_crop_px": list(ORIGIN_PX),
            "pixels_per_metre": PIXELS_PER_METRE,
            "reference_dimensions": [
                {"space": "kitchen", "printed_m": 2.75, "raster_span_px": 164, "axis": "x"},
                {"space": "kitchen", "printed_m": 4.12, "raster_span_px": 250, "axis": "y"},
                {"space": "bedroom_outer_south", "printed_m": 4.65, "raster_span_px": 283, "axis": "x"},
                {"space": "bedroom_south", "printed_m": 4.55, "raster_span_px": 273, "axis": "y"},
                {"space": "living_dining", "printed_m": 9.83, "raster_span_px": 590, "axis": "x"},
            ],
            "scan_uncertainty": "folds and mild scan skew; vertex positions approximately ±0.15–0.25 m",
        },
        "area_schedule_m2": {
            "carpet": 172.00,
            "balcony": 32.72,
            "dry_balcony": 3.05,
            "total": 207.77,
            "provenance": "printed RERA schedule on B1-Building-1.pdf",
        },
        "footprint": {
            "polygon": footprint,
            "includes_balconies": True,
            "confidence": "agreement outline corroborated; approximate raster trace",
            "geometry_provenance": "agreement unit red outline registered to approved sheet",
            "geometry_uncertainty_m": 0.20,
            "traced_area_m2": round(polygon_area(footprint), 2),
        },
        "rooms": rooms,
        "wall_segments": walls,
        "openings": openings,
        "unmeasured": [
            "floor elevation", "ceiling height", "wall build-up and true thickness",
            "door widths", "window/slider widths", "structural column sizes",
            "facade glass specification", "balcony railing height",
        ],
    }
    source = Path(__file__).with_name("raster_trace.json")
    source.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n")
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from app.dimensioned_b1 import build_dimensioned_plan
    plan = build_dimensioned_plan(plan)
    target = Path(__file__).with_name("plan.json")
    target.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {target} ({len(rooms)} rooms; modeled gross footprint {plan['footprint']['modeled_gross_area_m2']:.2f} m²)")


if __name__ == "__main__":
    main()
