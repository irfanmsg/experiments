"""Native OCR of drawing labels and explicit dimension pairs in source pixels."""

import csv
import io
import math
import re
import shutil
import subprocess
import tempfile
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

import cv2


_ROOM = re.compile(r'\b(?:master\s+bedroom|bedroom\s*\d*|kitchen|living|dining|dry\s+balcony|balcony|'
                   r'toilet|bathroom|powder\s+room|servant\s+room|entrance\s+lobby|lobby|passage|'
                   r'theater\s*/?\s*den|theatre\s*/?\s*den|den|mandir|puja|walk\s*in|'
                   r'office|study|store|storage|showroom|warehouse|workshop|utility|laundry|lift|stairs)\b', re.I)
_PUNCTUATION = str.maketrans({'′': "'", '’': "'", '‘': "'", '″': '"', '“': '"', '”': '"'})


def _parts(text):
    return re.split(r'\s*[xX×]\s*', text.translate(_PUNCTUATION).strip())


def _measure(text, shared_unit=None):
    imperial = re.fullmatch(r'(\d{1,3})\s*\'\s*(?:(\d{1,2}(?:\.\d+)?)\s*"?)?', text.strip())
    if imperial:
        feet, inches = float(imperial[1]), float(imperial[2] or 0)
        return (feet*12+inches)*.0254 if inches < 12 and feet*12+inches > 0 else None
    metric = re.fullmatch(r'(\d+(?:\.\d+)?)\s*(mm|cm|m)?', text.strip(), re.I)
    if metric and (unit := (metric[2] or shared_unit)):
        value = float(metric[1])*{'mm': .001, 'cm': .01, 'm': 1}[unit.lower()]
        return value if value > 0 and math.isfinite(value) else None
    return None


def parse_dimension_pair(text):
    """Convert explicit feet/inches or metric pairs; refuse guessed punctuation."""
    parts = _parts(text)
    if len(parts) != 2:
        return None
    suffix = re.search(r'(mm|cm|m)\s*$', parts[1], re.I)
    values = [_measure(part, suffix[1] if suffix else None) for part in parts]
    return values if all(value is not None for value in values) else None


def _original_bbox(rectangle, rotation, width, height, scale):
    x, y, w, h = [float(value)/scale for value in rectangle]
    if rotation == 90:
        return [y, height-x-w, y+h, height-x]
    if rotation == 270:
        return [width-y-h, x, width-y, x+w]
    return [x, y, x+w, y+h]


def _overlap(a, b):
    overlap = max(0, min(a[2], b[2])-max(a[0], b[0]))*max(0, min(a[3], b[3])-max(a[1], b[1]))
    return overlap/max(1, min((a[2]-a[0])*(a[3]-a[1]), (b[2]-b[0])*(b[3]-b[1])))


@lru_cache(maxsize=4)
def _engine_version(engine):
    try:
        result = subprocess.run([engine, '--version'], capture_output=True, text=True, timeout=5, check=True)
        return result.stdout.splitlines()[0].removeprefix('tesseract ').strip()
    except (OSError, subprocess.SubprocessError, IndexError):
        return None


def _apply_readings(dimension, readings):
    original = {'text': dimension['text'], 'confidence': dimension['confidence'], 'method': 'page_ocr'}
    dimension['original_text'] = original['text']
    dimension['readings'] = [original, *readings]
    candidates = []
    signatures = set()
    # Keep the original digits as evidence even when their unit punctuation
    # was unreadable. A crop cannot silently change 14'14 into 14'11.
    for index, reading in enumerate(dimension['readings']):
        parts = _parts(reading['text'])
        values = parse_dimension_pair(reading['text'])
        reading['dimensions_m'] = values
        if (index == 0 or reading['confidence'] >= .75) and len(parts) == 2 and all(re.search(r'\d', part) for part in parts):
            signatures.add(tuple(''.join(re.findall(r'\d', part)) for part in parts))
        if values and reading['confidence'] >= .75 and max(values)/min(values) <= 8:
            candidates.append(reading)
    distinct = {tuple(round(value, 6) for value in reading['dimensions_m']) for reading in candidates}
    dimension['conflicting_readings'] = len(signatures) > 1 or len(distinct) > 1
    if len(distinct) == 1 and not dimension['conflicting_readings']:
        best = max(candidates, key=lambda item: item['confidence'])
        dimension.update(text=best['text'], confidence=best['confidence'], dimensions_m=best['dimensions_m'],
                         dimension_parts_m=best['dimensions_m'], status='read', reading_source=best['method'])
        dimension.pop('warning', None)
    elif dimension['conflicting_readings']:
        dimension['warning'] = 'OCR retries disagree on digits. Preserve the readings and verify the printed caption before using this pair.'


def _retry_captions(original, dimensions, engine):
    height, width = original.shape
    with tempfile.TemporaryDirectory(prefix='drawing-caption-') as directory:
        for dimension in dimensions:
            if dimension['status'] != 'ambiguous' or not dimension.get('room_label'):
                continue
            x0, y0, x1, y1 = dimension['bbox']
            crop = original[max(0, int(y0)-3):min(height, math.ceil(y1)+4),
                            max(0, int(x0)-3):min(width, math.ceil(x1)+4)]
            if not crop.size:
                continue
            if dimension['rotation_deg']:
                crop = cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE if dimension['rotation_deg'] == 90 else cv2.ROTATE_90_COUNTERCLOCKWISE)
            readings = []
            for scale, threshold, psm in ((6, False, '7'), (6, True, '7'), (4, False, '6')):
                image = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
                if threshold:
                    image = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY+cv2.THRESH_OTSU)[1]
                filename = Path(directory) / 'caption.png'
                cv2.imwrite(str(filename), image)
                try:
                    result = subprocess.run([engine, str(filename), 'stdout', '-l', 'eng', '--psm', psm, 'tsv'],
                                            capture_output=True, text=True, check=True, timeout=10)
                except (OSError, subprocess.SubprocessError):
                    continue
                words = [row for row in csv.DictReader(io.StringIO(result.stdout), delimiter='\t', quoting=csv.QUOTE_NONE)
                         if row.get('text', '').strip() and float(row['conf']) >= 0]
                if words:
                    readings.append({'text': ' '.join(word['text'] for word in words),
                                     'confidence': round(sum(float(word['conf']) for word in words)/len(words)/100, 3),
                                     'method': f'crop_{scale}x_{"threshold" if threshold else "gray"}_psm{psm}'})
            _apply_readings(dimension, readings)


def extract_drawing_text(path):
    """Return labels, parsed/ambiguous dimensions and compact native OCR evidence.

    Bounding boxes are [left, top, right, bottom] in the original image. A valid
    dimension is OCR evidence, not confirmed scale; cross-check against walls.
    """
    result = {'available': False, 'engine': 'tesseract', 'engine_version': None, 'image_size': None,
              'room_labels': [], 'dimensions': [], 'raw_lines': [], 'warnings': []}
    engine = shutil.which('tesseract')
    if not engine:
        result['warnings'].append('Native tesseract OCR is unavailable. Install tesseract-ocr and its English language data.')
        return result
    result['engine_version'] = _engine_version(engine)
    original = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if original is None:
        result['warnings'].append('The drawing image could not be read for OCR.')
        return result
    height, width = original.shape
    result['image_size'] = [width, height]
    scale = min(2.0, 6000/max(width, height))
    lines = []
    with tempfile.TemporaryDirectory(prefix='drawing-ocr-') as directory:
        # Rotation recovers vertical room captions; a second contrast pass
        # recovers text lost against textured floor/background graphics.
        for rotation, threshold in ((0, False), (90, False), (270, False), (0, True)):
            view = original
            if rotation:
                view = cv2.rotate(view, cv2.ROTATE_90_CLOCKWISE if rotation == 90 else cv2.ROTATE_90_COUNTERCLOCKWISE)
            if threshold:
                view = cv2.threshold(view, 125, 255, cv2.THRESH_BINARY)[1]
            view = cv2.resize(view, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            filename = Path(directory) / 'ocr.png'
            cv2.imwrite(str(filename), view)
            try:
                completed = subprocess.run([engine, str(filename), 'stdout', '-l', 'eng', '--psm', '11', 'tsv'],
                                           capture_output=True, text=True, timeout=30, check=True)
            except (OSError, subprocess.SubprocessError):
                result['warnings'].append(f'Native OCR failed for the {rotation}-degree pass; check the engine and English language data.')
                continue
            result['available'] = True
            groups = defaultdict(list)
            for row in csv.DictReader(io.StringIO(completed.stdout), delimiter='\t', quoting=csv.QUOTE_NONE):
                if row.get('text', '').strip() and float(row['conf']) >= 0:
                    groups[(row['block_num'], row['par_num'], row['line_num'])].append(row)
            for words in groups.values():
                left, top = min(int(w['left']) for w in words), min(int(w['top']) for w in words)
                right = max(int(w['left'])+int(w['width']) for w in words)
                bottom = max(int(w['top'])+int(w['height']) for w in words)
                line = {'text': ' '.join(w['text'] for w in words),
                        'bbox': _original_bbox([left, top, right-left, bottom-top], rotation, width, height, scale),
                        'confidence': round(sum(float(w['conf']) for w in words)/len(words)/100, 3),
                        'rotation_deg': rotation, 'preprocessing': 'threshold' if threshold else 'grayscale'}
                lines.append(line)
    # Keep observed text, not file paths, commands or environment values.
    result['raw_lines'] = [line for line in lines if line['confidence'] >= .25]
    for line in lines:
        match = _ROOM.search(line['text'])
        if match and line['confidence'] >= .4:
            name = re.sub(r'(?<=[A-Za-z])(?=\d)', ' ', match[0]).title()
            label = {**line, 'name': name, 'label_fraction': len(match[0])/len(line['text'])}
            duplicate = next((old for old in result['room_labels'] if _overlap(old['bbox'], label['bbox']) > .5), None)
            if duplicate is None:
                result['room_labels'].append(label)
            elif (label['label_fraction'], label['confidence']) > (duplicate['label_fraction'], duplicate['confidence']):
                result['room_labels'][result['room_labels'].index(duplicate)] = label
        parts = _parts(line['text'])
        if len(parts) != 2 or not all(re.search(r'\d', part) for part in parts):
            continue
        if line['confidence'] < .25:
            continue
        values = parse_dimension_pair(line['text'])
        dimension = {**line, 'dimensions_m': values, 'status': 'read' if values else 'ambiguous',
                     'dimension_parts_m': [_measure(part) for part in parts]}
        if values is None:
            dimension['warning'] = 'A unit marker or digit is missing/invalid; do not infer a scale from this pair.'
        elif max(values)/min(values) > 8:
            # Missing decimal punctuation can turn 2.4 m into 24 m. Keep the
            # literal reading for review; do not silently repair that digit.
            dimension.update(dimensions_m=None, status='ambiguous', literal_dimensions_m=values,
                             warning='Extreme dimension ratio may indicate a missing decimal. Verify this caption before using it for scale.')
            values = None
        duplicate = next((old for old in result['dimensions'] if _overlap(old['bbox'], dimension['bbox']) > .5), None)
        if duplicate is None:
            result['dimensions'].append(dimension)
        elif (bool(values), dimension['confidence']) > (bool(duplicate['dimensions_m']), duplicate['confidence']):
            result['dimensions'][result['dimensions'].index(duplicate)] = dimension
    for dimension in result['dimensions']:
        x0, y0, x1, y1 = dimension['bbox']
        center = ((x0+x1)/2, (y0+y1)/2)
        nearby = []
        for label in result['room_labels']:
            if label['rotation_deg'] != dimension['rotation_deg']:
                continue
            a, b, c, d = label['bbox']
            distance = math.hypot(center[0]-(a+c)/2, center[1]-(b+d)/2)
            # A caption is normally one text line from its room name. Limit
            # associations so nearby rooms do not borrow each other's scale.
            text_height = (d-b) if dimension['rotation_deg'] == 0 else (c-a)
            if distance <= max(45, text_height*4):
                nearby.append((distance, label))
        if nearby:
            label = min(nearby, key=lambda item: item[0])[1]
            dimension['room_label'] = label['name']
            dimension['room_label_bbox'] = label['bbox']
    _retry_captions(original, result['dimensions'], engine)
    result['room_labels'].sort(key=lambda item: (item['bbox'][1], item['bbox'][0]))
    result['dimensions'].sort(key=lambda item: (item['bbox'][1], item['bbox'][0]))
    if any(item['status'] == 'ambiguous' for item in result['dimensions']):
        result['warnings'].append('Some dimension captions have missing punctuation or impossible digits; they remain ambiguous and cannot establish scale.')
    return result
