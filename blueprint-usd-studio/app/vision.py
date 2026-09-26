"""Conservative room suggestions from raster drawings, always user-reviewed."""

from __future__ import annotations

from pathlib import Path


def suggest_rooms(image_path: str | Path, max_results: int = 60) -> list[dict]:
    import cv2
    import numpy as np

    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Could not read plan image")
    height, width = image.shape[:2]
    scale = min(1.0, 2200 / max(height, width))
    work = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else image
    gray = cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)
    # Architectural scans may use blue rather than black ink. A difference
    # from white captures both without committing to a particular hue.
    darkness = 255 - gray
    ink = np.uint8(darkness > 38) * 255
    ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=2)
    free = 255 - ink
    count, labels, stats, _ = cv2.connectedComponentsWithStats(free, connectivity=8)
    work_area = work.shape[0] * work.shape[1]
    candidates = []
    for label in range(1, count):
        x, y, w, h, area = [int(v) for v in stats[label]]
        if x <= 2 or y <= 2 or x + w >= work.shape[1] - 2 or y + h >= work.shape[0] - 2:
            continue
        if area < max(300, work_area * 0.00025) or area > work_area * 0.16:
            continue
        if min(w, h) < 14 or max(w / max(h, 1), h / max(w, 1)) > 10:
            continue
        mask = np.uint8(labels[y:y+h, x:x+w] == label) * 255
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        contour = max(contours, key=cv2.contourArea)[:, 0, :].astype(float)
        if len(contour) < 3:
            continue
        contour[:, 0] += x
        contour[:, 1] += y
        perimeter = cv2.arcLength(contour.astype(np.float32), True)
        simple = cv2.approxPolyDP(contour.astype(np.float32), max(2, perimeter * 0.012), True)[:, 0, :]
        if not (3 <= len(simple) <= 12):
            simple = np.array([[x, y], [x+w, y], [x+w, y+h], [x, y+h]], dtype=float)
        polygon = [[round(float(px / scale), 1), round(float(py / scale), 1)] for px, py in simple]
        candidates.append({"pixel_polygon": polygon, "pixel_area": int(area / scale**2), "confidence": "suggestion", "label": f"Space {len(candidates)+1}"})
    candidates.sort(key=lambda item: item["pixel_area"], reverse=True)
    return candidates[:max_results]
