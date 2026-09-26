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
    for wall in plan.get("wall_segments", []):
        if segment_length(wall.get("start", (0, 0)), wall.get("end", (0, 0))) < 0.05:
            errors.append(f"Wall {wall.get('id', '?')} is shorter than 5 cm")
    return errors
