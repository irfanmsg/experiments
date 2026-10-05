"""Small, dependency-free geometry helpers for traced floor plans."""

from __future__ import annotations

import math
import re
from typing import Iterable


def safe_name(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_]", "_", str(value)).strip("_")
    if not name:
        name = "Item"
    return f"N_{name}" if name[0].isdigit() else name


def polygon_area(points: Iterable[Iterable[float]]) -> float:
    xy = [tuple(map(float, point[:2])) for point in points]
    if len(xy) < 3:
        return 0.0
    return abs(sum(xy[i][0] * xy[(i + 1) % len(xy)][1] - xy[(i + 1) % len(xy)][0] * xy[i][1] for i in range(len(xy))) / 2)


def signed_area(points: list[tuple[float, float]]) -> float:
    return sum(points[i][0] * points[(i + 1) % len(points)][1] - points[(i + 1) % len(points)][0] * points[i][1] for i in range(len(points))) / 2


def triangulate(points: Iterable[Iterable[float]]) -> list[tuple[int, int, int]]:
    """Ear-clip a simple polygon; raises if the trace self-intersects."""
    xy = [tuple(map(float, point[:2])) for point in points]
    if len(xy) < 3:
        raise ValueError("A floor outline needs at least three corners")
    if len(xy) > 3 and xy[0] == xy[-1]:
        xy.pop()
    if len(xy) < 3 or abs(signed_area(xy)) < 1e-8:
        raise ValueError("A floor outline has zero area")
    order = list(range(len(xy)))
    if signed_area(xy) < 0:
        order.reverse()
    faces: list[tuple[int, int, int]] = []
    while len(order) > 3:
        ear_found = False
        for k in range(len(order)):
            a, b, c = order[k - 1], order[k], order[(k + 1) % len(order)]
            ax, ay = xy[a]
            bx, by = xy[b]
            cx, cy = xy[c]
            cross = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
            if cross <= 1e-9:
                continue
            blocked = False
            for p in order:
                if p in (a, b, c):
                    continue
                px, py = xy[p]
                u = ((bx - px) * (cy - py) - (by - py) * (cx - px)) / cross
                v = ((cx - px) * (ay - py) - (cy - py) * (ax - px)) / cross
                w = 1 - u - v
                if min(u, v, w) >= -1e-9:
                    blocked = True
                    break
            if not blocked:
                faces.append((a, b, c))
                order.pop(k)
                ear_found = True
                break
        if not ear_found:
            raise ValueError("Could not triangulate outline; check for crossing edges")
    faces.append(tuple(order))
    return faces


def segment_length(a: Iterable[float], b: Iterable[float]) -> float:
    aa, bb = list(a), list(b)
    return math.hypot(float(bb[0]) - float(aa[0]), float(bb[1]) - float(aa[1]))


def bbox(polygons: Iterable[Iterable[Iterable[float]]]) -> tuple[float, float, float, float]:
    pts = [(float(p[0]), float(p[1])) for poly in polygons for p in poly]
    if not pts:
        raise ValueError("No geometry in plan")
    return min(x for x, _ in pts), min(y for _, y in pts), max(x for x, _ in pts), max(y for _, y in pts)


def measured_scale_audit(plan: dict) -> dict:
    """Remeasure current geometry while retaining the source comparison evidence."""
    audit = dict(plan.get('scale_audit') or {})
    if not audit:
        return audit
    rows = []
    for room in plan.get('rooms', []):
        modeled = []
        try:
            x0, y0, x1, y1 = bbox([room['polygon']])
            modeled = [x1-x0, y1-y0]
            if room.get('dimension_mode') == 'average_depth':
                axis = int(room['span_axis'])
                modeled[1-axis] = polygon_area(room['polygon']) / modeled[axis]
        except (KeyError, ValueError, TypeError, IndexError, ZeroDivisionError):
            modeled = []
        rows.append({'id': room.get('id'), 'name': room.get('name'),
                     'printed': room.get('dimensions_m', []), 'modeled': modeled,
                     'dimension_mode': room.get('dimension_mode', 'raster')})
    audit['room_dimensions'] = rows
    footprint = plan.get('footprint', {})
    try:
        x0, y0, x1, y1 = bbox([footprint['polygon']])
        audit['footprint_span_m'] = [x1-x0, y1-y0]
        audit['gross_area_m2'] = polygon_area(footprint['polygon']) - sum(
            polygon_area(hole) for hole in footprint.get('holes', []))
    except (KeyError, ValueError, TypeError, IndexError):
        audit['footprint_span_m'], audit['gross_area_m2'] = [], None
    if 'room_registration_offsets_m' in audit:
        from shapely.geometry import Polygon
        audit['room_registration_offsets_m'] = []
        for room in plan.get('rooms', []):
            if room.get('id') == 'balcony_curved' or not room.get('source_polygon'):
                continue
            current, source = Polygon(room['polygon']).centroid, Polygon(room['source_polygon']).centroid
            audit['room_registration_offsets_m'].append({
                'id': room.get('id'), 'center_offset_xy_m': [current.x-source.x, current.y-source.y],
                'basis': 'difference from approximate agreement raster registration; exact offsets are not dimensioned'})
    if 'modeled_visible_span_m' in audit:
        try:
            x0, y0, x1, y1 = bbox([room['polygon'] for room in plan.get('rooms', [])
                                  if room.get('id') != 'balcony_curved'])
            audit['modeled_visible_span_m'] = [x1-x0, y1-y0]
        except (KeyError, ValueError, TypeError, IndexError):
            audit['modeled_visible_span_m'] = []
    if 'main_outer_arc_length_m' in audit:
        balcony = next((room for room in plan.get('rooms', []) if room.get('id') == 'balcony_curved'), {})
        # The registered B1 profile keeps the outer arc between its inboard returns.
        points = balcony.get('polygon', [])[1:-3]
        audit['main_outer_arc_length_m'] = sum(segment_length(a, b) for a, b in zip(points, points[1:])) if len(points) > 1 else None
    audit['static_source_evidence_fields'] = [key for key in (
        'source_trace_gross_area_m2', 'source_trace_span_m', 'visible_agreement_span_m', 'scheduled_area_m2') if key in audit]
    return audit


def validate_plan(plan: dict) -> list[str]:
    errors: list[str] = []
    if plan.get("units", "m") != "m":
        errors.append("Only metre-based plans are supported")
    rooms = plan.get("rooms", [])
    footprint = plan.get("footprint", {}).get("polygon", [])
    if not rooms and not footprint:
        errors.append("Outline at least one room or the structure perimeter")
    for room in rooms:
        try:
            triangulate(room["polygon"])
        except (KeyError, ValueError, TypeError) as exc:
            errors.append(f"Room {room.get('name', room.get('id', '?'))}: {exc}")
    if footprint:
        try:
            triangulate(footprint)
        except (ValueError, TypeError) as exc:
            errors.append(f"Perimeter: {exc}")
    for room in rooms:
        mode = room.get('dimension_mode')
        if mode not in {'clear_rectangle', 'average_depth'}:
            continue
        try:
            from shapely.geometry import Polygon
            shape = Polygon(room['polygon'])
            x0, y0, x1, y1 = shape.bounds
            printed = list(map(float, room['dimensions_m']))
            if mode == 'clear_rectangle':
                actual = [x1-x0, y1-y0]
                if abs(shape.area-actual[0]*actual[1]) > 1e-6:
                    raise ValueError('clear dimensions require a rectangular room boundary')
            else:
                axis = room['span_axis']
                span = (y1-y0) if axis == 1 else (x1-x0)
                actual = [shape.area/span, span] if axis == 1 else [span, shape.area/span]
            if len(printed) != 2 or any(abs(a-b) > 1e-6 for a,b in zip(actual,printed)):
                raise ValueError(f'modeled meters {actual} do not match printed meters {printed}')
        except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
            errors.append(f"Room {room.get('id', '?')}: {exc}")
    for wall in plan.get("wall_segments", []):
        if segment_length(wall.get("start", (0, 0)), wall.get("end", (0, 0))) < 0.005:
            errors.append(f"Wall {wall.get('id', '?')} is shorter than 5 mm")
    return errors
