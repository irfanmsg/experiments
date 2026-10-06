"""Room suggestions require structural boundaries, not furniture outlines."""
import cv2
import numpy as np
from pathlib import Path

import pytest
from shapely.geometry import Point, Polygon, box

from app.vision import suggest_rooms
from app import vision


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


def test_labels_dimensions_and_walls_recover_rooms_across_open_doorways(tmp_path):
    image = np.full((800, 1000, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (100, 100), (720, 620), (20, 20, 20), 10)
    cv2.line(image, (410, 100), (410, 390), (20, 20, 20), 10)
    cv2.line(image, (410, 490), (410, 620), (20, 20, 20), 10)
    cv2.rectangle(image, (140, 180), (270, 360), (20, 20, 20), 2)
    path = tmp_path / 'labeled.png'
    cv2.imwrite(str(path), image)
    labels = [{'name': name, 'text': name, 'bbox': [x-40, 390, x+40, 410], 'confidence': .95}
              for name, x in [('Bedroom 1', 240), ('Bedroom 2', 560)]]
    text = {'available': True, 'room_labels': labels, 'dimensions': [
        {'text': '3 m x 5.1 m', 'dimensions_m': [3, 5.1], 'bbox': [x-40, 415, x+40, 435],
         'room_label': name, 'room_label_bbox': label['bbox'], 'confidence': .95}
        for label, (name, x) in zip(labels, [('Bedroom 1', 240), ('Bedroom 2', 560)])], 'warnings': []}
    report = vision.analyze_drawing(path, text_data=text)
    suggestions = report['suggestions']
    assert {item['label'] for item in suggestions} == {'Bedroom 1', 'Bedroom 2'}
    for item in suggestions:
        shape = Polygon(item['pixel_polygon'])
        assert 145000 < shape.area < 165000
        assert item['wall_evidence'] and item['dimension_evidence']
        assert item['inferred_boundaries'], 'Record the doorway closure instead of claiming an observed wall'
        assert item['pixel_openings'], 'Doorway gaps must remain open in a reconstructed wall'
        gap = next(gap for gap in item['pixel_openings'] if 70 < gap['width_px'] < 110)
        assert abs(gap['pixel_center'][0]-410) < 12
        assert 420 < gap['pixel_center'][1] < 460
        assert gap['type'] == 'opening' and gap['confidence'] == 'needs-review'
    scale = report['scale_proposal']
    assert 97 < scale['pixels_per_meter'] < 103
    assert len(scale['observations']) >= 2
    assert scale['review_note'] and 'relative_error' in scale['observations'][0]


def test_ocr_label_alone_cannot_create_room_or_calibrate_from_furniture(tmp_path):
    image = np.full((800, 1000, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (200, 200), (400, 450), (20, 20, 20), 2)
    path = tmp_path / 'label-without-walls.png'
    cv2.imwrite(str(path), image)
    text = {'available': True, 'room_labels': [{'name': 'Bedroom', 'bbox': [240, 300, 350, 330], 'confidence': .9}],
            'dimensions': [{'text': '2m x 3m', 'dimensions_m': [2, 3], 'bbox': [240, 340, 350, 360], 'confidence': .9}], 'warnings': []}
    report = vision.analyze_drawing(path, text_data=text)
    assert not report['suggestions']
    assert report['scale_proposal'] is None


@pytest.mark.skipif(not _UPLOADED_PLAN.is_file(), reason='Optional local QA: private upload is not committed')
def test_uploaded_plan_reconstructs_room_extent_and_reports_scale_outliers():
    report = vision.analyze_drawing(_UPLOADED_PLAN)
    rooms = {item['name']: Polygon(item['pixel_polygon']) for item in report['suggestions'] if item.get('name')}
    bedroom = rooms['Bedroom 3']
    assert all(bedroom.covers(Point(*xy)) for xy in [(470, 590), (570, 675)])
    assert not any(bedroom.covers(Point(*xy)) for xy in [(250, 600), (670, 653), (490, 370)])
    assert 50000 < bedroom.area < 100000
    kitchen = rooms['Kitchen']
    assert all(kitchen.covers(Point(*xy)) for xy in [(270, 620), (184, 610)])
    assert not kitchen.covers(Point(470, 590))
    assert kitchen.area > 45000
    scale = report['scale_proposal']
    assert 70 < scale['pixels_per_meter'] < 77
    assert scale['max_relative_error'] <= .075
    assert len({item['room_name'] for item in scale['observations']}) >= 2
    assert scale['excluded_observations']
    for i, shape in enumerate(rooms.values()):
        for other in list(rooms.values())[i+1:]:
            assert shape.intersection(other).area / min(shape.area, other.area) <= .03


def test_repeated_room_names_do_not_borrow_another_labels_dimensions(tmp_path):
    image = np.full((800, 1000, 3), 255, dtype=np.uint8)
    for x in (100, 500):
        cv2.rectangle(image, (x, 100), (x+300, 610), (20, 20, 20), 10)
    path = tmp_path / 'duplicate-labels.png'
    cv2.imwrite(str(path), image)
    labels = [{'name': 'Toilet', 'bbox': [x, 340, x+80, 365], 'confidence': .95} for x in (210, 610)]
    text = {'room_labels': labels, 'dimensions': [
        {'text': '3m x 5m', 'dimensions_m': [3, 5], 'room_label': 'Toilet',
         'room_label_bbox': labels[0]['bbox'], 'confidence': .95}], 'warnings': []}
    report = vision.analyze_drawing(path, text_data=text)
    assert len(report['suggestions']) == 2
    right = next(item for item in report['suggestions'] if Polygon(item['pixel_polygon']).covers(Point(650, 350)))
    assert right['dimension_evidence'] == {}
    assert report['scale_proposal'] is None, 'One room alone must not become independent calibration evidence'


@pytest.mark.skipif(not (_UPLOADED_PLAN.is_file() and (_UPLOADED_PLAN.parents[2] / 'output/qa/labeled-room-final.json').is_file()),
                    reason='Optional local QA: private upload and OCR evidence are not committed')
def test_grouped_room_covers_label_without_missing_boundary_warning():
    import json
    evidence = json.loads((_UPLOADED_PLAN.parents[2] / 'output/qa/labeled-room-final.json').read_text())
    report = vision.analyze_drawing(_UPLOADED_PLAN, text_data=evidence['drawing_text'])
    assert any(item['name'] == 'Dining / Living' for item in report['suggestions'])
    assert not any(warning.startswith('Dining: no sufficiently supported room boundary') for warning in report['warnings'])
    servant = next(item for item in report['suggestions'] if item['name'] == 'Servant Room')
    assert servant['max_dimension_relative_error'] > .075
    assert any(warning.startswith('Toilet: no sufficiently supported room boundary') for warning in report['warnings'])
