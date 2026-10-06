"""Offline outline evaluation. Run from the repository: python -m tools.benchmark_outlines."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import subprocess

from PIL import Image
from shapely import hausdorff_distance
from shapely.geometry import Polygon


def positive_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def polygon(points):
    if not isinstance(points, list) or not 3 <= len(points) <= 10000:
        raise ValueError('A polygon needs 3–10000 pixel points')
    for point in points:
        if (not isinstance(point, list) or len(point) != 2 or any(
                isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in point)):
            raise ValueError('Polygon points must be finite [x, y] numbers')
    shape = Polygon(points)
    if not shape.is_valid or shape.area <= 0:
        raise ValueError('Polygon must be simple and have positive area')
    return shape


def load_manifest(path):
    path = Path(path).resolve()
    manifest = json.loads(path.read_text())
    if not isinstance(manifest, dict) or manifest.get('dataset_kind') not in ('unseen', 'development', 'synthetic'):
        raise ValueError('dataset_kind must be unseen, development, or synthetic')
    plans = manifest.get('plans')
    if not isinstance(plans, list) or not 1 <= len(plans) <= 1000:
        raise ValueError('Provide 1–1000 plans')
    ids = set()
    for plan in plans:
        if not isinstance(plan, dict):
            raise ValueError('Each plan must be an object')
        if not isinstance(plan.get('id'), str) or not plan['id'].strip() or plan['id'] in ids:
            raise ValueError('Each plan needs a unique nonempty id')
        ids.add(plan['id'])
        if not isinstance(plan.get('source'), str) or not plan['source'].strip():
            raise ValueError('Each plan needs source/provenance information')
        relative = Path(plan['image'])
        image = (path.parent / relative).resolve()
        if relative.is_absolute() or not image.is_relative_to(path.parent) or not image.is_file():
            raise ValueError('Images must be existing files inside the manifest directory')
        with Image.open(image) as opened:
            width, height = opened.size
        rooms = plan.get('rooms')
        if not isinstance(rooms, list) or not 1 <= len(rooms) <= 500:
            raise ValueError('Provide 1–500 ground-truth rooms per plan')
        for room in rooms:
            if not isinstance(room, dict):
                raise ValueError('Each room must be an object')
            if not isinstance(room.get('name'), str) or not room['name'].strip():
                raise ValueError('Each ground-truth room needs a name')
            left, top, right, bottom = polygon(room['pixel_polygon']).bounds
            if left < 0 or top < 0 or right > width or bottom > height:
                raise ValueError('Ground-truth polygon extends outside the original image')
        if 'pixels_per_meter' in plan and not positive_number(plan['pixels_per_meter']):
            raise ValueError('pixels_per_meter must be a finite positive number')
    return manifest


def evaluate(plan, analysis, minimum_iou=.5):
    """Maximum-cardinality one-to-one matches above an IoU threshold; names do not guide matching."""
    if not positive_number(minimum_iou) or minimum_iou > 1:
        raise ValueError('minimum_iou must be in (0, 1]')
    expected = [polygon(room['pixel_polygon']) for room in plan['rooms']]
    proposals = analysis['suggestions']
    predicted = [polygon(room['pixel_polygon']) for room in proposals]
    overlaps = [[a.intersection(b).area / a.union(b).area for b in predicted] for a in expected]
    neighbors = [sorted((j for j, score in enumerate(row) if score >= minimum_iou),
                        key=lambda j: (-row[j], j)) for row in overlaps]
    assigned = {}

    def match(i, visited):
        for j in neighbors[i]:
            if j in visited:
                continue
            visited.add(j)
            if j not in assigned or match(assigned[j], visited):
                assigned[j] = i
                return True
        return False

    for i in range(len(expected)):
        match(i, set())
    matches = []
    for j, i in sorted(assigned.items(), key=lambda item: item[1]):
        name = proposals[j].get('name', proposals[j].get('label', ''))
        matches.append({'ground_truth_index': i, 'prediction_index': j,
                        'ground_truth_name': plan['rooms'][i]['name'], 'predicted_name': name,
                        'name_exact_match': name.strip().casefold() == plan['rooms'][i]['name'].strip().casefold(),
                        'iou': overlaps[i][j],
                        'boundary_hausdorff_px': float(hausdorff_distance(expected[i].boundary, predicted[j].boundary, densify=.1))})
    scale = (analysis.get('scale_proposal') or {}).get('pixels_per_meter')
    if scale is not None and not positive_number(scale):
        raise ValueError('Detector returned an invalid scale')
    known = plan.get('pixels_per_meter')
    return {'expected': len(expected), 'predicted': len(predicted), 'matched': len(matches),
            'missed': [i for i in range(len(expected)) if i not in assigned.values()],
            'spurious': [j for j in range(len(predicted)) if j not in assigned], 'matches': matches,
            'precision': len(matches)/len(predicted) if predicted else None,
            'recall': len(matches)/len(expected),
            'mean_matched_iou': sum(m['iou'] for m in matches)/len(matches) if matches else None,
            'scale': {'expected_pixels_per_meter': known, 'predicted_pixels_per_meter': scale,
                      'absolute_relative_error': abs(scale/known-1) if scale and known else None},
            'warnings': analysis.get('warnings', [])}


def sha256(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def run(manifest_path, minimum_iou=.5):
    from app.vision import analyze_drawing

    manifest_path = Path(manifest_path).resolve()
    manifest = load_manifest(manifest_path)
    root = Path(__file__).resolve().parents[1]
    git = lambda *args: subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'dataset_kind': manifest['dataset_kind'],
              'manifest_sha256': sha256(manifest_path), 'git_revision': git('rev-parse', 'HEAD'),
              'git_dirty': bool(git('status', '--porcelain')), 'minimum_iou': minimum_iou, 'detector_max_results': 60,
              'file_sha256': {str(p.relative_to(root)): sha256(p) for p in
                              [Path(__file__).resolve(), root/'app/vision.py', root/'app/drawing_text.py', root/'uv.lock'] if p.exists()},
              'versions': {name: importlib.metadata.version(name) for name in ('numpy', 'opencv-python-headless', 'shapely', 'Pillow')},
              'plans': []}
    for plan in manifest['plans']:
        image = manifest_path.parent / plan['image']
        result = {'id': plan['id'], 'source': plan['source'], 'image': plan['image'], 'image_sha256': sha256(image)}
        try:
            analysis = analyze_drawing(image)
            result.update(evaluate(plan, analysis, minimum_iou))
            result['ocr_version'] = analysis.get('drawing_text', {}).get('engine_version')
            result['predictions'] = analysis['suggestions']
        except Exception as error:
            result['error'] = f'{type(error).__name__}: {error}'
        report['plans'].append(result)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--output', type=Path, required=True, help='New JSON report; existing files are never overwritten')
    parser.add_argument('--minimum-iou', type=float, default=.5)
    args = parser.parse_args()
    if not positive_number(args.minimum_iou) or args.minimum_iou > 1:
        parser.error('--minimum-iou must be in (0, 1]')
    if args.output.exists():
        parser.error('Output already exists; choose a new baseline filename')
    try:
        report = run(args.manifest, args.minimum_iou)
        with args.output.open('x') as output:
            json.dump(report, output, indent=2, allow_nan=False)
            output.write('\n')
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.error(str(error))
    raise SystemExit(1 if any('error' in p for p in report['plans']) else 0)


if __name__ == '__main__':
    main()
