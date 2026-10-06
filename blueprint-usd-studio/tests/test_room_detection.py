"""Room suggestions require structural boundaries, not furniture outlines."""
import cv2
import numpy as np
from pathlib import Path

import pytest
from shapely.geometry import Point, Polygon, box

from app.vision import suggest_rooms


def test_furniture_does_not_become_rooms_or_cut_holes_in_room_geometry(tmp_path):
    image = np.full((700, 1000, 3), 255, dtype=np.uint8)
    for x in (80, 540):
        cv2.rectangle(image, (x, 100), (x+350, 570), (30, 30, 30), 12)
        cv2.rectangle(image, (x+80, 280), (x+230, 490), (30, 30, 30), 2)
        cv2.rectangle(image, (x+85, 290), (x+145, 335), (30, 30, 30), 2)
        cv2.rectangle(image, (x+165, 290), (x+225, 335), (30, 30, 30), 2)
        cv2.rectangle(image, (x+8, 140), (x+65, 235), (30, 30, 30), 2)
    path = tmp_path / 'furnished.png'
    cv2.imwrite(str(path), image)
    suggestions = suggest_rooms(path)
    assert len(suggestions) == 2
    for x in (80, 540):
        room = next(Polygon(item['pixel_polygon']) for item in suggestions
                    if Polygon(item['pixel_polygon']).covers(Point(x+180, 400)))
        assert room.covers(Point(x+30, 180)), 'Cabinet line must not replace the room wall'
        assert room.area > 140000


def test_furniture_only_is_not_a_floor_plan(tmp_path):
    image = np.full((700, 1000, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (100, 100), (280, 350), (20, 20, 20), 2)
    cv2.rectangle(image, (110, 110), (170, 160), (20, 20, 20), 2)
    cv2.circle(image, (560, 360), 100, (20, 20, 20), 2)
    path = tmp_path / 'furniture.png'
    cv2.imwrite(str(path), image)
    assert suggest_rooms(path) == []


def test_simple_two_rooms_and_concave_outline_keep_their_boundaries(tmp_path):
    image = np.full((800, 1000, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (80, 100), (350, 450), (0, 0, 0), 8)
    polygon = np.array([[500, 100], [850, 100], [850, 260], [690, 260], [690, 480], [500, 480]])
    cv2.polylines(image, [polygon], True, (0, 0, 0), 8)
    path = tmp_path / 'rooms.png'
    cv2.imwrite(str(path), image)
    suggestions = suggest_rooms(path)
    assert len(suggestions) == 2
    assert any(Polygon(item['pixel_polygon']).covers(Point(180, 200)) for item in suggestions)
    corner_room = next(Polygon(item['pixel_polygon']) for item in suggestions
                       if Polygon(item['pixel_polygon']).covers(Point(550, 150)))
    assert not corner_room.covers(Point(790, 400)), 'Never replace a concave room with its bounding rectangle'


def test_complex_outline_is_not_replaced_by_rectangle(tmp_path):
    image = np.full((900, 1200, 3), 255, dtype=np.uint8)
    polygon = np.array([[100, 100], [500, 100], [500, 180], [420, 180],
                        [420, 260], [500, 260], [500, 340], [420, 340],
                        [420, 420], [500, 420], [500, 500], [420, 500],
                        [420, 580], [500, 580], [500, 660], [100, 660]])
    cv2.polylines(image, [polygon], True, (0, 0, 0), 10)
    path = tmp_path / 'complex.png'
    cv2.imwrite(str(path), image)
    suggestions = suggest_rooms(path)
    assert len(suggestions) == 1
    shape = Polygon(suggestions[0]['pixel_polygon'])
    assert shape.covers(Point(200, 200))
    assert not any(shape.covers(Point(460, y)) for y in (220, 380, 540))


_UPLOADED_PLAN = Path(__file__).resolve().parents[1] / 'uploads/b8c1fbd8870c/plan.png'


@pytest.mark.skipif(not _UPLOADED_PLAN.is_file(), reason='Optional local QA: private upload is not committed')
def test_uploaded_furnished_plan_does_not_return_beds_or_kitchen_counters():
    # Bounds checked against the uploaded drawing, not inferred by the detector.
    furniture = [box(415, 532, 528, 650), box(866, 650, 980, 765),
                 box(799, 1257, 913, 1370), box(148, 1389, 260, 1506),
                 box(156, 454, 210, 689)]
    for suggestion in suggest_rooms(_UPLOADED_PLAN):
        shape = Polygon(suggestion['pixel_polygon'])
        assert all(shape.intersection(item).area / shape.area < .7 for item in furniture)
