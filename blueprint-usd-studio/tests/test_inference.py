"""Mocked Hub calls only: geometry, consent, transport and credential boundaries."""
import asyncio
import base64
import io
import json
import urllib.error

import pytest
from fastapi import HTTPException
from PIL import Image
from starlette.requests import Request

from app import inference

KEY = 'test-private-key-never-reflect'


def request(body=None, *, scheme='https', peer='10.1.2.3', headers=None):
    raw = json.dumps(body).encode() if body is not None else b''
    async def receive():
        return {'type': 'http.request', 'body': raw, 'more_body': False}
    entries = {'authorization': 'Bearer ' + KEY, **(headers or {})}
    return Request({'type': 'http', 'method': 'POST', 'scheme': scheme,
                    'server': ('studio.example', 443), 'client': (peer, 12345),
                    'path': '/', 'query_string': b'',
                    'headers': [(key.encode(), value.encode()) for key,value in entries.items()]}, receive)


def room(**overrides):
    return {'name': 'Living', 'polygon': [[.1,.1],[.7,.1],[.7,.5],[.1,.5]],
            'basis': 'Visible external walls; furniture excluded', 'assumptions': ['Open entry edge inferred'], **overrides}


def test_outline_request_sends_only_scaled_primary_image_and_returns_reviewable_evidence(tmp_path, monkeypatch):
    from app import main
    monkeypatch.setattr(main, 'UPLOADS', tmp_path)
    folder = tmp_path / 'sample'; folder.mkdir()
    Image.new('RGB', (3000, 1500), 'white').save(folder / 'plan.png')
    (folder / 'plan.json').write_text('{"untouched":true}')
    (folder / 'private-supporting-file.txt').write_text('never send supporting material')
    calls = []
    def hub(endpoint, token, payload=None):
        calls.append(endpoint)
        assert token == KEY
        assert endpoint == 'chat/completions'
        assert payload['model'] == 'vision-model'
        content = payload['messages'][0]['content']
        assert len(content) == 2 and content[0]['text'] == inference.PROMPT
        encoded = content[1]['image_url']['url'].split(',', 1)[1]
        image = Image.open(io.BytesIO(base64.b64decode(encoded)))
        assert image.size == (2048, 1024)
        assert KEY not in json.dumps(payload)
        assert 'never send supporting material' not in json.dumps(payload)
        return {'model':'vision-model-revision-2', 'choices': [{'message': {'content': json.dumps({'rooms': [room()]})}}]}
    monkeypatch.setattr(inference, '_hub_json', hub)
    result = asyncio.run(inference.outlines('sample', request({'model':'vision-model', 'consent': True})))
    assert calls == ['chat/completions']
    assert result['suggestions'][0]['pixel_polygon'] == [[300,150],[2100,150],[2100,750],[300,750]]
    assert result['suggestions'][0]['ai_generated'] is True
    assert result['suggestions'][0]['confidence'] == 'needs-review'
    assert result['suggestions'][0]['inference']['assumptions'] == ['Open entry edge inferred']
    assert result['trace']['image_dimensions'] == [3000,1500]
    assert result['trace']['sent_dimensions'] == [2048,1024]
    assert len(result['trace']['image_sha256']) == 64
    assert result['trace']['prompt_version'] == inference.PROMPT_VERSION
    assert result['trace']['model_reported'] == 'vision-model-revision-2'
    assert result['trace']['client']['library'] == 'Python urllib.request'
    assert KEY not in json.dumps(result)
    assert (folder / 'plan.json').read_text() == '{"untouched":true}'
    assert sorted(p.name for p in folder.iterdir()) == ['plan.json','plan.png','private-supporting-file.txt']


@pytest.mark.parametrize('scheme,peer,allowed', [('https','10.1.2.3',True),
    ('http','127.0.0.1',True), ('http','::1',True), ('http','10.1.2.3',False),
    ('http','localhost',False), ('http','127.0.0.1.evil',False)])
def test_transport_uses_actual_peer_not_forwarded_headers(scheme, peer, allowed):
    req = request(scheme=scheme, peer=peer, headers={'x-forwarded-proto':'https', 'x-forwarded-for':'127.0.0.1'})
    assert inference.config(req)['secure_transport'] is allowed
    if allowed:
        assert inference._token(req) == KEY
    else:
        with pytest.raises(HTTPException) as error:
            inference._token(req)
        assert error.value.status_code == 400
        assert KEY not in error.value.detail


@pytest.mark.parametrize('body', [{'model':'vision'}, {'model':'vision','consent':'true'},
    {'model':'vision','consent':1}, {'model':'','consent':True}, {'model':'x\nsecret','consent':True},
    {'model':KEY,'consent':True}, ['not an object'], {'model':'vision','consent':True, 'excess':'x'*4096}])
def test_invalid_request_never_calls_provider(monkeypatch, body):
    monkeypatch.setattr(inference, '_hub_json', lambda *args: pytest.fail('Should not contact Hub'))
    with pytest.raises(HTTPException) as error:
        asyncio.run(inference.outlines('sample', request(body)))
    assert error.value.status_code in {400,413}
    assert KEY not in error.value.detail


@pytest.mark.parametrize('polygon', [
    [[0,0],[1,1],[0,1],[1,0]], [[0,0],[0,0],[0,0]], [[-.1,0],[1,0],[1,1]],
    [[0,0],[1.1,0],[1,1]], [[False,0],[1,0],[1,1]], [[float('nan'),0],[1,0],[1,1]],
    [[float('inf'),0],[1,0],[1,1]], [[0,0],[1,0]], [[0,0,0],[1,0],[1,1]],
    [[0,0]]*129,
])
def test_invalid_geometry_is_rejected(polygon):
    with pytest.raises(HTTPException) as error:
        inference.validate_proposals(json.dumps({'rooms':[room(polygon=polygon)]}), (100,100), {})
    assert error.value.status_code == 502


def test_overlaps_room_limits_and_excessive_text_are_rejected():
    for rooms in ([room(), room(name='Duplicate')], [room()]*61,
                  [room(name='X'*121)], [room(basis='X'*1001)], [room(assumptions=['X']*13)]):
        with pytest.raises(HTTPException):
            inference.validate_proposals(json.dumps({'rooms':rooms}), (100,100), {})
    adjacent = [room(polygon=[[0,0],[.5,0],[.5,1],[0,1]]), room(name='Kitchen',polygon=[[.5,0],[1,0],[1,1],[.5,1]])]
    assert len(inference.validate_proposals(json.dumps({'rooms':adjacent}), (100,100), {})) == 2
    assert inference.validate_proposals('{"rooms":[]}', (100,100), {}) == []


def test_models_sanitized_and_token_not_reflected(monkeypatch):
    def hub(endpoint, token, payload=None):
        assert endpoint == 'models' and token == KEY and payload is None
        return {'data':[{'id':'vision/a'}, {'id':'vision/a'}, {'id':KEY}, {'id':'bad\nname'}, {'id':'text/b'}]}
    monkeypatch.setattr(inference, '_hub_json', hub)
    assert asyncio.run(inference.models(request())) == {'models':['text/b','vision/a']}


@pytest.mark.parametrize('status', [301,401,403,429,500])
def test_upstream_errors_are_redacted(monkeypatch, status):
    class Opener:
        def open(self, req, timeout):
            assert req.full_url == inference.BASE_URL + 'models'
            assert req.get_header('Authorization') == 'Bearer ' + KEY
            raise urllib.error.HTTPError('https://example/' + KEY, status, KEY, {}, io.BytesIO(KEY.encode()))
    monkeypatch.setattr(inference.urllib.request, 'build_opener', lambda handler: Opener())
    with pytest.raises(HTTPException) as error:
        inference._hub_json('models', KEY)
    assert KEY not in error.value.detail
    assert error.value.status_code == (401 if status in {401,403} else 429 if status == 429 else 502)


@pytest.mark.parametrize('raw', [b'not json', json.dumps({'key':KEY}).encode(), b'x'*(inference.MAX_RESPONSE_BYTES+1)])
def test_bad_or_secret_provider_bodies_are_not_reflected(monkeypatch, raw):
    class Opener:
        def open(self, req, timeout):
            return io.BytesIO(raw)
    monkeypatch.setattr(inference.urllib.request, 'build_opener', lambda handler: Opener())
    with pytest.raises(HTTPException) as error:
        inference._hub_json('models', KEY)
    assert KEY not in error.value.detail


def test_redirects_are_disabled():
    handler = inference._NoRedirect()
    assert handler.redirect_request(None, None, 307, '', {}, 'https://untrusted.example') is None


def test_escaped_credentials_rejected_after_each_json_layer(monkeypatch):
    escaped = ''.join('\\u%04x' % ord(char) for char in KEY)
    class Opener:
        def open(self, req, timeout):
            return io.BytesIO(('{' + '"name":"' + escaped + '"}').encode())
    monkeypatch.setattr(inference.urllib.request, 'build_opener', lambda handler: Opener())
    with pytest.raises(HTTPException) as error:
        inference._hub_json('models', KEY)
    assert KEY not in error.value.detail
    content = json.dumps({'rooms':[room(basis=KEY)]}).replace(KEY, escaped)
    monkeypatch.setattr(inference, '_image', lambda project: ((100,100),(100,100),'hash',b'image'))
    monkeypatch.setattr(inference, '_hub_json', lambda *args: {'choices':[{'message':{'content':content}}]})
    with pytest.raises(HTTPException) as error:
        asyncio.run(inference.outlines('sample', request({'model':'vision','consent':True})))
    assert error.value.status_code == 502
    assert KEY not in error.value.detail


@pytest.mark.parametrize('value', ['Bearer "quoted-token"', 'Bearer token,', 'Bearer first,second',
    'Bearer token with spaces', 'Bearer token=middle', 'Bearer', 'Basic abc'])
def test_non_token68_credentials_rejected_before_provider(monkeypatch, value):
    monkeypatch.setattr(inference, '_hub_json', lambda *args: pytest.fail('Invalid credential reached Hub'))
    with pytest.raises(HTTPException) as error:
        asyncio.run(inference.models(request(headers={'authorization':value})))
    assert error.value.status_code == 401
    assert value not in error.value.detail


def test_token68_credential_punctuation_and_padding_are_valid():
    token = 'abc.ABC_123-~+/=='
    assert inference._token(request(headers={'authorization':'Bearer ' + token})) == token
