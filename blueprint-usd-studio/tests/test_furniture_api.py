import copy

from fastapi.testclient import TestClient

from app import main


def test_furnishing_requires_scale_and_returns_proposal_without_changing_plan(monkeypatch):
    plan = {'units': 'm', 'rooms': [{'id': 'living', 'name': 'Living',
                                  'polygon': [[0, 0], [8, 0], [8, 6], [0, 6]]}]}
    monkeypatch.setattr(main, '_read_plan', lambda project: copy.deepcopy(plan))
    monkeypatch.setattr(main, 'catalog', lambda: {'assets': []})
    client = TestClient(main.app)
    endpoint = '/api/projects/test/suggest-furniture'
    for calibration in [None, {}, {'pixels_per_meter': -10}, {'pixels_per_meter': 'invalid'}]:
        plan['calibration'] = calibration
        assert client.post(endpoint).status_code == 400
    plan['calibration'] = {'pixels_per_meter': 100}
    before = copy.deepcopy(plan)
    response = client.post(endpoint)
    assert response.status_code == 200
    assert response.json()['placements'] == []
    assert all(item['status'] == 'skipped' for item in response.json()['decisions'])
    assert plan == before
