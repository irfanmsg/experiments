"""Check printed-length guidance on the hosted UI without changing a user's plan."""
import argparse
from io import BytesIO
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright
from check_room_reconstruction import assert_reconstructed_rooms


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://10.46.71.211:8001')
    parser.add_argument('--reference-project', default='b8c1fbd8870c')
    args = parser.parse_args()
    origin = args.url.rstrip('/')
    artifacts = Path(__file__).resolve().parents[1] / 'output/qa'
    artifacts.mkdir(parents=True, exist_ok=True)
    errors, writes = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path='/opt/google/chrome/chrome',
                                             headless=True, args=['--no-sandbox'])
        page = browser.new_page(viewport={'width': 1600, 'height': 1100})
        page.on('pageerror', lambda error: errors.append(str(error)))

        def read_only(route):
            if route.request.method not in ('GET', 'HEAD', 'OPTIONS'):
                writes.append(route.request.url)
                route.abort()
            else:
                route.continue_()

        def capture(selector, filename):
            style = page.add_style_tag(content='.topbar { visibility: hidden !important; }')
            try:
                panel = page.locator(selector)
                panel.evaluate('(panel) => panel.scrollIntoView({block: "start"})')
                panel.screenshot(path=str(artifacts / filename))
            finally:
                style.evaluate('(style) => style.remove()')

        try:
            reference = page.request.get(f'{origin}/api/projects/{args.reference_project}').json()['plan']
            initial_stream = page.request.get(origin + '/api/stream/status').json()
            page.route('**/api/**', read_only)
            page.goto(f'{origin}/?project={args.reference_project}')
            page.wait_for_function('state.image && !state.suggesting && state.scaleProposal && state.suggestions.length > 0', timeout=120000)
            assert_reconstructed_rooms(page.evaluate('state.suggestions'))
            assert page.locator('#useDetectedScale').is_visible()
            assert page.locator('#manualScale').get_attribute('open') is None
            assert page.locator('#scaleEvidence li').count() >= 2
            capture('#measureCard', 'measurement-guidance-real-plan.png')
            capture('#outlineCard', 'room-review-real-plan.png')
            assert not writes
            page.unroute('**/api/**', read_only)

            image = Image.new('RGB', (800, 400), 'white')
            drawing = ImageDraw.Draw(image)
            drawing.line([(100, 250), (500, 250)], fill='black', width=3)
            drawing.text((270, 225), '13 ft 3 in', fill='black')
            png = BytesIO()
            image.save(png, format='PNG')
            page.locator('#fileInput').set_input_files({'name': 'measurement-guidance.png',
                                                       'mimeType': 'image/png', 'buffer': png.getvalue()})
            page.wait_for_function('(previous) => state.project !== previous && state.image && state.image.width === 800 && !state.suggesting', arg=args.reference_project, timeout=120000)
            project = page.evaluate('state.project')
            assert page.evaluate('state.suggestions.length') == 0
            assert page.locator('#manualScale').get_attribute('open') is not None
            assert 'Setting the scale will not create the missing outlines' in page.locator('#suggestionStatus').inner_text()
            for value in ['', 'thirteen cubits']:
                page.locator('#distanceInput').fill(value)
                page.locator('#calibrateButton').click()
                assert page.evaluate('state.tool') != 'calibrate'
                assert page.evaluate('state.plan.calibration') is None
                assert 'positive printed length' in page.locator('#toast').inner_text()
            entered = '13\'3"'
            page.locator('#distanceInput').fill(entered)
            page.locator('#calibrateButton').click()
            assert page.evaluate('state.tool') == 'calibrate'
            assert 'Step 1 of 2' in page.locator('#toolHint').inner_text()
            canvas = page.locator('#planCanvas')
            canvas.scroll_into_view_if_needed()
            for index, point in enumerate([[100, 250], [500, 250]]):
                screen = canvas.evaluate('(canvas,p)=>{const r=canvas.getBoundingClientRect();return [r.x+p[0]*r.width/canvas.width,r.y+p[1]*r.height/canvas.height];}', point)
                page.mouse.click(*screen)
                if index == 0:
                    assert 'Step 2 of 2' in page.locator('#toolHint').inner_text()
                    assert page.evaluate('state.plan.calibration') is None
            page.wait_for_function('state.plan.calibration && document.getElementById("saveState").textContent === "Saved"')
            saved = page.request.get(f'{origin}/api/projects/{project}').json()['plan']
            calibration = saved['calibration']
            evidence = calibration['reference_dimensions'][0]
            assert evidence['entered_length'] == entered
            assert math.isclose(evidence['distance_m'], 4.0386, abs_tol=1e-8)
            assert math.isclose(calibration['pixels_per_meter'], 400/4.0386, abs_tol=1e-4)
            assert 'not automatically extracted' in evidence['basis']
            assert saved['rooms'] == [] and saved['footprint']['polygon'] == []
            assert page.locator('#generateButton').is_disabled()
            assert 'still need' in page.locator('#toast').inner_text().lower()
            capture('#measureCard', 'measurement-guidance-imperial.png')
            page.reload()
            page.wait_for_function('state.image && state.plan.calibration && !state.suggesting')
            assert page.evaluate('state.plan.calibration') == calibration
            assert page.evaluate('state.plan.rooms') == []
            assert page.request.get(f'{origin}/api/projects/{project}').json()['plan'] == saved
            assert page.request.get(f'{origin}/api/projects/{args.reference_project}').json()['plan'] == reference
            final_stream = page.request.get(origin + '/api/stream/status').json()
            assert all(final_stream.get(key) == initial_stream.get(key) for key in ['running', 'project_id', 'style'])
            assert not errors, errors
            report = {'passed': True, 'hosted_url': origin, 'scratch_project': project,
                      'reference_project_unchanged': args.reference_project, 'entered_length': entered,
                      'metres': evidence['distance_m'], 'pixels_per_metre': calibration['pixels_per_meter'],
                      'invalid_input_blocked': True, 'two_step_guidance': True,
                      'no_rooms_invented_by_calibration': True, 'reload_preserved_geometry': True,
                      'shared_stream_unchanged': True, 'page_errors': errors}
            (artifacts / 'measurement-guidance-result.json').write_text(json.dumps(report, indent=2))
            print(json.dumps(report))
        finally:
            browser.close()


if __name__ == '__main__':
    main()
