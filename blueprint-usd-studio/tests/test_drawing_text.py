from pathlib import Path
import shutil

import pytest

from app import drawing_text


@pytest.mark.parametrize('text,expected', [
    ('9\'0" x 13\'5"', [2.7432, 4.0894]),
    ('10\'0" × 13\'3"', [3.048, 4.0386]),
    ('14′3″ X 13′3″', [4.3434, 4.0386]),
    ('2.4 M X 1.85 M', [2.4, 1.85]),
    ('240 x 185 cm', [2.4, 1.85]),
    ('2400mm x 1850mm', [2.4, 1.85]),
])
def test_parse_explicit_printed_dimension_pairs(text, expected):
    assert drawing_text.parse_dimension_pair(text) == pytest.approx(expected)


@pytest.mark.parametrize('text', ['100" x 13\'3"', '11\'9" x 14\'14"', '0\'0" x 5\'0"', '3.0 x 4.0', 'large room'])
def test_ambiguous_missing_unit_or_impossible_inches_are_not_silently_repaired(text):
    assert drawing_text.parse_dimension_pair(text) is None


def test_missing_engine_is_actionable(monkeypatch):
    monkeypatch.setattr(drawing_text.shutil, 'which', lambda name: None)
    result = drawing_text.extract_drawing_text(Path('unused.png'))
    assert result['available'] is False
    assert 'tesseract' in result['warnings'][0].lower()


def test_crop_retry_accepts_explicit_units_without_changing_digits():
    dimension = {'text': '100" x 13\'3"', 'confidence': .8, 'dimensions_m': None,
                 'dimension_parts_m': [None, 4.0386], 'status': 'ambiguous'}
    drawing_text._apply_readings(dimension, [{'text': '10\'0" x 13\'3"', 'confidence': .95, 'method':'crop_6x'}])
    assert dimension['dimensions_m'] == pytest.approx([3.048, 4.0386])
    assert dimension['original_text'] == '100" x 13\'3"'
    assert len(dimension['readings']) == 2


def test_crop_retry_keeps_conflicting_digit_readings_ambiguous():
    dimension = {'text': '153" x 11\'9"', 'confidence': .8, 'dimensions_m': None,
                 'dimension_parts_m': [None, 3.5814], 'status': 'ambiguous'}
    drawing_text._apply_readings(dimension, [
        {'text': '15\'3" x 11\'9"', 'confidence': .95, 'method':'crop_6x'},
        {'text': '15\'3" x 14\'9"', 'confidence': .94, 'method':'crop_threshold'},
    ])
    assert dimension['dimensions_m'] is None
    assert dimension['status'] == 'ambiguous' and dimension['conflicting_readings']
    assert len(dimension['readings']) == 3


_PRIVATE = Path(__file__).resolve().parents[1] / 'uploads/b8c1fbd8870c/plan.png'


@pytest.mark.skipif(not _PRIVATE.is_file() or not shutil.which('tesseract'), reason='Optional private drawing and native OCR engine')
def test_actual_drawing_exposes_kitchen_scale_anchor_in_original_pixels():
    result = drawing_text.extract_drawing_text(_PRIVATE)
    assert result['available'] is True
    assert result['engine_version']
    assert result['image_size'] == [1290, 2796]
    assert len(result['room_labels']) >= 8
    kitchen = next(item for item in result['dimensions'] if item.get('room_label', '').lower() == 'kitchen' and item['dimensions_m'])
    assert kitchen['dimensions_m'] == pytest.approx([2.7432, 4.0894])
    x0, y0, x1, y1 = kitchen['bbox']
    assert 200 < x0 < x1 < 350 and 590 < y0 < y1 < 660
    assert any(item['status'] == 'ambiguous' for item in result['dimensions'])
    bedroom = next(item for item in result['dimensions'] if item.get('room_label') == 'Bedroom 3')
    if bedroom['dimensions_m']:
        assert bedroom['dimensions_m'] == pytest.approx([3.048, 4.0386])
    else:
        assert bedroom['dimension_parts_m'][1] == pytest.approx(4.0386)
    assert bedroom['readings']
    lift = next(item for item in result['dimensions'] if item.get('room_label') == 'Lift')
    assert lift.get('literal_dimensions_m') == [24, 1.85]
    assert lift['dimensions_m'] is None or lift['dimensions_m'] == pytest.approx([2.4, 1.85])
