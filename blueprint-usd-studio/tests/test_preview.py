import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from app import main


def test_rendered_previews_are_bound_to_the_saved_layout(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'OUTPUT', tmp_path)
    directory = tmp_path / 'project' / 'previews'
    directory.mkdir(parents=True)
    plan = {'rooms': [{'polygon': [[0, 0], [3, 0], [3, 4], [0, 4]]}]}
    digest = hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    sys.path.insert(0, str(Path(__file__).parents[1] / 'streaming'))
    from run import _save_rendered_preview
    frame = np.array([[[200, 100, 50, 255]]], dtype=np.uint8)
    _save_rendered_preview({'preview_path': str(directory / 'contemporary.png'), 'plan_fingerprint': digest}, frame)
    assert Image.open(directory / 'contemporary.png').getpixel((0, 0)) == (200, 100, 50)
    saved = json.loads((directory / 'manifest.json').read_text())
    assert saved['plan_sha256'] == digest
    saved['styles'].append('../invalid')
    (directory / 'manifest.json').write_text(json.dumps(saved))
    assert main._preview_urls('project', plan) == {'contemporary': '/api/projects/project/preview/contemporary'}
    plan['rooms'][0]['polygon'][1][0] += .1
    assert main._preview_urls('project', plan) == {}
