import hashlib
from io import BytesIO
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
import pymupdf

from app import source_files


def test_supporting_sources_preserve_bytes_roles_and_plan_and_reject_bad_uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(source_files, 'UPLOADS', tmp_path)
    project = tmp_path / 'reviewed-home'
    project.mkdir()
    plan = project / 'plan.json'
    plan.write_text('{"rooms": []}')
    application = FastAPI()
    application.include_router(source_files.router)
    client = TestClient(application)
    endpoint = '/api/projects/reviewed-home/sources'
    assert client.get(endpoint).json()['sources'] == []
    image = BytesIO()
    Image.new('RGB', (4, 3), 'green').save(image, 'PNG')
    data = image.getvalue()
    response = client.post(endpoint, files={'file': ('../wall.png', data, 'image/png')},
                           data={'role': 'photo', 'notes': 'North wall; dimensions unverified'})
    assert response.status_code == 200, response.text
    entry = response.json()['sources'][0]
    assert entry['original_name'] == 'wall.png'
    assert entry['role'] == 'photo' and entry['notes'] == 'North wall; dimensions unverified'
    assert entry['size_bytes'] == len(data) and entry['sha256'] == hashlib.sha256(data).hexdigest()
    assert entry['status'] == source_files.STATUS
    assert str(tmp_path) not in response.text
    download = client.get(entry['download_url'])
    assert download.content == data
    assert 'attachment;' in download.headers['content-disposition']
    assert download.headers['x-content-type-options'] == 'nosniff'
    # A plan autosave cannot erase supporting evidence.
    plan.write_text('{"rooms": [], "name": "Reviewed again"}')
    assert source_files.source_manifest('reviewed-home')['sources'] == [entry]
    with pymupdf.open() as document:
        document.new_page()
        pdf = document.tobytes()
    response = client.post(endpoint, files={'file': ('measurement.pdf', pdf)}, data={'role': 'measurement'})
    assert response.status_code == 200, response.text
    assert len(response.json()['sources']) == 2
    assert client.get(response.json()['sources'][-1]['download_url']).content == pdf
    before = (project / 'sources/index.json').read_bytes()
    for filename, body, fields, expected in [
        ('empty.pdf', b'', {}, 400), ('bad.pdf', b'not a pdf', {}, 400),
        ('bad.png', b'not an image', {}, 400), ('photo.jpg', data, {}, 400),
        ('payload.html', b'<script/>', {}, 400), ('photo.png', data, {'role': 'unknown'}, 422),
        ('photo.png', data, {'notes': 'x'*2001}, 422),
    ]:
        response = client.post(endpoint, files={'file': (filename, body)}, data=fields)
        assert response.status_code == expected, (filename, response.text)
    monkeypatch.setattr(source_files, 'MAX_BYTES', 5)
    assert client.post(endpoint, files={'file': ('large.png', data)}).status_code == 413
    monkeypatch.setattr(source_files, 'MAX_BYTES', 200*1024*1024)
    monkeypatch.setattr(source_files, 'MAX_FILES', 2)
    assert client.post(endpoint, files={'file': ('extra.png', data)}).status_code == 409
    assert (project / 'sources/index.json').read_bytes() == before
    assert not list((project / 'sources').glob('*.part'))
    assert len(list((project / 'sources').glob('*.png'))) == 1
    assert json.loads(plan.read_text()) == {'rooms': [], 'name': 'Reviewed again'}
    assert client.get('/api/projects/missing/sources').status_code == 404
    assert client.get('/api/projects/INVALID/sources').status_code == 400
    assert client.get(endpoint + '/invalid').status_code == 404
    (tmp_path / 'escaped').symlink_to(project)
    assert client.get('/api/projects/escaped/sources').status_code == 200
    outside = tmp_path.parent / (tmp_path.name + '-outside')
    outside.mkdir()
    (outside / 'plan.json').write_text('{}')
    (tmp_path / 'outside').symlink_to(outside)
    assert client.get('/api/projects/outside/sources').status_code == 404
    (outside / 'escaped.png').write_bytes(data)
    saved_image = project / 'sources' / entry['filename']
    saved_image.unlink()
    saved_image.symlink_to(outside / 'escaped.png')
    assert client.get(entry['download_url']).status_code == 404
    another = tmp_path / 'another'
    another.mkdir()
    (another / 'plan.json').write_text('{}')
    (another / 'sources').symlink_to(outside)
    assert client.get('/api/projects/another/sources').status_code == 400
    index = project / 'sources/index.json'
    index.write_text('{broken')
    assert client.post(endpoint, files={'file': ('photo.png', data)}).status_code == 500
    assert index.read_text() == '{broken'
