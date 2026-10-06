"""Upload, review detected rooms, calibrate and generate without naming or height setup.

Run against Studio: .venv/bin/python tests/check_onboarding.py
Creates a scratch project; never starts or stops the shared GPU stream.
"""
import argparse
from io import BytesIO
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8001')
    args = parser.parse_args()
    origin = args.url.rstrip('/')
    artifacts = Path(__file__).resolve().parents[1] / 'output/qa'
    artifacts.mkdir(parents=True, exist_ok=True)
    image = Image.new('RGB', (800, 600), 'white')
    drawing = ImageDraw.Draw(image)
    for bounds in [(80, 100, 320, 300), (400, 100, 640, 300)]:
        drawing.rectangle(bounds, outline='black', width=8)
    drawing.line([(80, 450), (480, 450)], fill='black', width=2)
    drawing.text((260, 430), '4.00 m', fill='black')
    upload = BytesIO()
    image.save(upload, format='PNG')
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path='/opt/google/chrome/chrome',
                                             headless=True, args=['--no-sandbox'])
        page = browser.new_page(viewport={'width': 1500, 'height': 1000})
        page.on('pageerror', lambda error: errors.append(str(error)))
        project = None
        try:
            initial_stream = page.request.get(origin + '/api/stream/status').json()
            page.goto(origin)
            page.locator('#fileInput').set_input_files({'name': 'onboarding-two-rooms.png',
                                                       'mimeType': 'image/png', 'buffer': upload.getvalue()})
            page.wait_for_function('state.project && state.image && state.plan')
            project = page.evaluate('state.project')
            page.wait_for_function('state.suggestions.length === 2', timeout=10000)
            candidates = page.evaluate('state.suggestions')
            assert page.evaluate('state.plan.calibration') is None
            assert page.evaluate('state.plan.rooms.length') == 0
            assert page.get_by_role('checkbox', name='Use proposed room', exact=False).count() == 2
            assert page.get_by_role('textbox', name='Name for proposed room', exact=False).count() == 2
            assert page.locator('#planCanvas').evaluate('''canvas => {
                const pixels=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;
                let coloured=0;
                for(let i=0;i<pixels.length;i+=4) if(Math.max(pixels[i],pixels[i+1],pixels[i+2])-Math.min(pixels[i],pixels[i+1],pixels[i+2])>30) coloured++;
                return coloured>50;
            }'''), 'Proposed outlines should be visible over the monochrome source before scale is set.'
            assert page.locator('#acceptSuggestions').is_disabled()
            assert page.locator('#generateButton').is_disabled()
            assert page.locator('#manualTools').get_attribute('open') is None
            assert page.locator('#modelSettings').get_attribute('open') is None
            assert page.locator('#heightInput').is_hidden()
            assert page.locator('#heightInput').input_value() == '2.9'
            assert not page.locator('#roomName').evaluate('(input) => input.required')
            page.locator('#canvasArea').screenshot(path=str(artifacts / 'onboarding-detected-rooms.png'))

            page.locator('#distanceInput').fill('4')
            page.locator('#calibrateButton').click()
            canvas = page.locator('#planCanvas')
            canvas.scroll_into_view_if_needed()
            for point in [[80, 450], [480, 450]]:
                screen = canvas.evaluate('(canvas, point) => {const box=canvas.getBoundingClientRect();return [box.x+point[0]*box.width/canvas.width,box.y+point[1]*box.height/canvas.height];}', point)
                page.mouse.click(*screen)
            page.wait_for_function('state.plan.calibration !== null')
            scale = page.evaluate('state.plan.calibration.pixels_per_meter')
            assert math.isclose(scale, 100, abs_tol=.01), scale
            assert page.locator('#acceptSuggestions').is_enabled()
            page.locator('#acceptSuggestions').click()
            page.wait_for_function('state.plan.rooms.length === 2')
            rooms = page.evaluate('state.plan.rooms')
            assert len({room['id'] for room in rooms}) == 2, rooms
            assert [room['name'] for room in rooms] == ['Room 1', 'Room 2'], rooms
            assert all('suggestion' in room['geometry_provenance'].lower() and
                       'accept' in room['geometry_provenance'].lower() for room in rooms)
            assert all('dimensions_m' not in room for room in rooms), 'The detector did not read printed room dimensions.'
            for room, candidate in zip(rooms, candidates):
                for axis in [0, 1]:
                    measured = max(p[axis] for p in room['polygon']) - min(p[axis] for p in room['polygon'])
                    pixels = max(p[axis] for p in candidate['pixel_polygon']) - min(p[axis] for p in candidate['pixel_polygon'])
                    assert math.isclose(measured, pixels / scale, abs_tol=.002), (room, candidate)
            assert page.locator('#roomName').input_value() == ''
            page.locator('#generateButton').click()
            page.wait_for_function('state.generated !== null', timeout=45000)
            generated = page.evaluate('state.generated.result')
            assert generated['room_count'] == 2 and generated['height_m'] == 2.9
            assert page.evaluate('state.plan.room_height_m') == 2.9
            assert 'assum' in page.evaluate('state.plan.height_status').lower()
            assert page.locator('#heightInput').is_hidden()

            name = page.locator('#roomList input').first
            name.fill('Living room')
            name.press('Tab')
            page.wait_for_function('state.plan.rooms[0].name === "Living room" && document.getElementById("saveState").textContent === "Saved"')
            saved = page.request.get(f'{origin}/api/projects/{project}').json()['plan']
            assert saved['rooms'][0]['name'] == 'Living room' and saved['room_height_m'] == 2.9
            assert saved['rooms'][0]['polygon'] == rooms[0]['polygon']
            assert page.evaluate('state.generated') is None, 'Renaming must invalidate stale generated metadata.'
            current_stream = page.request.get(origin + '/api/stream/status').json()
            for key in ['running', 'project_id', 'style', 'quality', 'physics']:
                assert current_stream.get(key) == initial_stream.get(key), (initial_stream, current_stream)
            assert not errors, errors
            page.locator('#outlineCard').evaluate('(card) => card.scrollIntoView({block: "center"})')
            page.locator('#outlineCard').screenshot(path=str(artifacts / 'onboarding-reviewed-rooms.png'))
            report = {'passed': True, 'scratch_project': project, 'detected_rooms_before_calibration': 2,
                      'pixels_per_meter': scale, 'room_count': 2, 'height_default_m': 2.9,
                      'optional_names': True, 'room_rename_saved': True, 'shared_stream_unchanged': True,
                      'page_errors': errors}
            (artifacts / 'onboarding-result.json').write_text(json.dumps(report, indent=2))
            print(json.dumps(report))
        except Exception:
            page.screenshot(path=str(artifacts / 'onboarding-failure.png'), full_page=True)
            print(json.dumps({'passed': False, 'scratch_project': project, 'page_errors': errors}))
            raise
        finally:
            browser.close()


if __name__ == '__main__':
    main()
