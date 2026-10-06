"""Synthetic evaluator checks are not evidence of accuracy on unseen real plans."""
import json

from PIL import Image
import pytest

from tools.benchmark_outlines import evaluate, load_manifest, run


def test_benchmark_counts_split_merge_errors_and_preserves_baseline_evidence(tmp_path, monkeypatch):
    # One good outline, one merged pair, and a spurious furniture-sized outline.
    rect = lambda x, y, w, h: [[x, y], [x+w, y], [x+w, y+h], [x, y+h]]
    plan = {'id': 'synthetic-demo', 'image': 'plan.png', 'source': 'Synthetic metric unit test',
            'pixels_per_meter': 10,
            'rooms': [{'name': name, 'pixel_polygon': points} for name, points in [
                ('Kitchen', rect(0, 0, 10, 10)), ('Bedroom', rect(20, 0, 10, 10)),
                ('Toilet', rect(30, 0, 10, 10))]]}
    predictions = [{'name': name, 'pixel_polygon': points} for name, points in [
        ('kitchen', rect(1, 0, 10, 10)), ('Bedroom / toilet', rect(20, 0, 20, 10)),
        ('Bed', rect(50, 0, 3, 3))]]
    analysis = {'suggestions': predictions, 'scale_proposal': {'pixels_per_meter': 11},
                'drawing_text': {'engine_version': 'test-only'}, 'warnings': []}
    result = evaluate(plan, analysis)
    assert result['matched'] == 2
    assert len(result['missed']) == 1, 'A merged proposal cannot count as two detected rooms'
    assert result['spurious'] == [2]
    assert result['precision'] == result['recall'] == pytest.approx(2/3)
    assert result['matches'][0]['iou'] == pytest.approx(90/110)
    assert result['matches'][0]['boundary_hausdorff_px'] == pytest.approx(1)
    assert result['matches'][0]['name_exact_match'] is True
    assert result['matches'][1]['name_exact_match'] is False
    assert result['scale']['absolute_relative_error'] == pytest.approx(.1)
    Image.new('RGB', (100, 100), 'white').save(tmp_path/'plan.png')
    path = tmp_path/'manifest.json'
    path.write_text(json.dumps({'dataset_kind': 'synthetic', 'plans': [plan]}))
    monkeypatch.setattr('app.vision.analyze_drawing', lambda image: analysis)
    baseline = run(path)
    assert baseline['dataset_kind'] == 'synthetic'
    assert len(baseline['git_revision']) == 40
    assert len(baseline['manifest_sha256']) == 64
    assert len(baseline['plans'][0]['image_sha256']) == 64
    assert baseline['plans'][0]['predictions'] == predictions
    assert baseline['plans'][0]['matched'] == 2
    # Data validation must reject corrupt coordinates and escaping image paths.
    plan['rooms'][0]['pixel_polygon'][0][0] = float('nan')
    path.write_text(json.dumps({'dataset_kind': 'synthetic', 'plans': [plan]}))
    with pytest.raises(ValueError, match='finite'):
        load_manifest(path)
    plan['image'] = '../plan.png'
    path.write_text(json.dumps({'dataset_kind': 'synthetic', 'plans': [plan]}))
    with pytest.raises(ValueError, match='inside'):
        load_manifest(path)
