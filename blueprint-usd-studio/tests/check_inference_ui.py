"""Hosted browser check with synthetic Hub responses; never contacts the Hub."""
import io
import json
import os
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

BASE = os.environ.get('BLUEPRINT_STUDIO_URL', 'http://10.46.71.211:18001')


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path='/opt/google/chrome/chrome', headless=True, args=['--no-sandbox'])
        page = browser.new_page(viewport={'width': 1500, 'height': 1100})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        image = io.BytesIO()
        Image.new('RGB', (800, 600), 'white').save(image, 'PNG')
        result = page.request.post(BASE + '/api/projects/upload', multipart={'file': {'name':'AI UI test.png', 'mimeType':'image/png', 'buffer':image.getvalue()}})
        assert result.ok, result.status
        project = result.json()['id']
        plan = result.json()['plan']
        plan['calibration'] = {'pixels_per_meter':100, 'pixel_origin':[0,600]}
        assert page.request.put(f'{BASE}/api/projects/{project}/plan', data=plan).ok
        page.route('**/suggest', lambda route: route.fulfill(json={'suggestions':[]}))
        page.goto(f'{BASE}/?project={project}')
        page.wait_for_function('state.image && !state.suggesting')
        page.locator('#inferencePanel summary').first.click()
        page.wait_for_function("document.querySelector('#inferenceTransport').textContent.includes('HTTPS')")
        assert page.locator('#inferenceKey').is_disabled()
        # Emulate a trusted HTTPS deployment for frontend-only checks.
        page.route('**/api/inference/config', lambda route: route.fulfill(json={'secure_transport':True,'base_url':'https://inference-api.nvidia.com/v1/'}))
        calls = []
        trace = {'provider':'NVIDIA Inference Hub','model':'test/vision','basis':'Visible wall lines','assumptions':['Doorway gap closed at wall line'],'prompt_version':'test'}
        suggestion = {'name':'AI study','label':'AI study','pixel_polygon':[[100,100],[400,100],[400,400],[100,400]],'ai_generated':True,'confidence':'needs-review','inference':trace}
        def inference(route):
            calls.append(route.request)
            assert route.request.headers['authorization'] == 'Bearer fake-ui-key'
            assert route.request.post_data_json == {'model':'test/vision','consent':True}
            route.fulfill(json={'suggestions':[suggestion], 'trace':trace})
        page.route('**/inference/outlines', inference)
        page.reload()
        page.wait_for_function('state.image && !state.suggesting')
        page.locator('#inferencePanel summary').first.click()
        page.locator('#inferenceKey').fill('fake-ui-key')
        page.locator('#inferenceModel').fill('test/vision')
        page.locator('#inferenceRun').click()
        assert not calls
        page.locator('#inferenceConsent').check()
        page.locator('#inferenceRun').click()
        page.wait_for_function("!document.querySelector('#inferenceReview').hidden")
        assert len(calls) == 1
        assert page.locator('#inferenceKey').input_value() == ''
        assert page.evaluate('state.plan.rooms.length') == 0
        assert page.evaluate('calibration().scale') == 100
        page.locator('#inferenceReview').click()
        assert not page.get_by_role('checkbox', name='Use proposed room 1', exact=True).is_checked()
        assert 'Doorway gap closed' in page.locator('#suggestions').inner_text()
        page.get_by_role('checkbox', name='Use proposed room 1', exact=True).check()
        page.locator('#acceptSuggestions').click()
        page.wait_for_function("state.plan.rooms.length === 1 && document.querySelector('#saveState').textContent === 'Saved'")
        saved = page.request.get(f'{BASE}/api/projects/{project}').json()['plan']
        assert saved['rooms'][0]['source_evidence']['inference'] == trace
        assert 'AI inferred' in saved['rooms'][0]['geometry_provenance']
        assert saved['calibration'] == plan['calibration']
        assert 'fake-ui-key' not in json.dumps(saved)
        assert not page.evaluate("JSON.stringify(localStorage).includes('fake-ui-key') || JSON.stringify(sessionStorage).includes('fake-ui-key')")
        # A plan edit invalidates pending AI output before it reaches review.
        page.locator('#inferenceKey').fill('fake-ui-key')
        page.locator('#inferenceConsent').check()
        page.locator('#inferenceRun').click()
        page.wait_for_function("!document.querySelector('#inferenceReview').hidden")
        page.evaluate('state.revision += 1')
        page.locator('#inferenceReview').click()
        assert 'plan changed' in page.locator('#inferenceStatus').inner_text()
        assert page.evaluate('state.plan.rooms.length') == 1
        assert not errors, errors
        target = Path(__file__).resolve().parents[1] / 'output/qa/inference-review.png'
        target.parent.mkdir(exist_ok=True, parents=True)
        page.screenshot(path=str(target), full_page=True)
        print(json.dumps({'project':project, 'checks':'HTTP gate, consent, opt-in, evidence persistence, scale retained, key cleared, stale review rejected', 'browser_errors':errors}))
        browser.close()


if __name__ == '__main__':
    main()
