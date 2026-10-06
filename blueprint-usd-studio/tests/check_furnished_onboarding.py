"""Live detector and full-size furnishing checks; creates only a scratch project."""
import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:18001')
    parser.add_argument('--reference-project', default='b8c1fbd8870c')
    args = parser.parse_args()
    origin = args.url.rstrip('/')
    artifacts = Path(__file__).resolve().parents[1] / 'output/qa'
    artifacts.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path='/opt/google/chrome/chrome',
                                             headless=True, args=['--no-sandbox'])
        page = browser.new_page(viewport={'width': 1600, 'height': 1100})
        page.on('pageerror', lambda error: errors.append(str(error)))

        def capture(selector, filename):
            # Sticky chrome otherwise overlaps tall element screenshots.
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
            writes = []

            def read_only(route):
                if route.request.method not in ('GET', 'HEAD', 'OPTIONS'):
                    writes.append(route.request.url)
                    route.abort()
                else:
                    route.continue_()

            page.route('**/api/**', read_only)
            page.goto(f'{origin}/?project={args.reference_project}')
            page.wait_for_function('state.image && !state.suggesting && document.getElementById("suggestionStatus").textContent.includes("No reliable")')
            assert page.evaluate('state.suggestions.length') == 0
            assert page.request.get(f'{origin}/api/projects/{args.reference_project}/suggest').json()['suggestions'] == []
            assert 'Furniture symbols are not room boundaries' in page.locator('#suggestionStatus').inner_text()
            assert not writes
            assert page.request.get(f'{origin}/api/projects/{args.reference_project}').json()['plan'] == reference
            capture('#canvasArea', 'furniture-room-detection-after.png')
            page.unroute('**/api/**', read_only)

            image = np.full((700, 1000, 3), 255, dtype=np.uint8)
            for x in (80, 540):
                cv2.rectangle(image, (x, 100), (x+350, 570), (30, 30, 30), 12)
                cv2.rectangle(image, (x+80, 280), (x+230, 490), (30, 30, 30), 2)
                cv2.rectangle(image, (x+85, 290), (x+145, 335), (30, 30, 30), 2)
                cv2.rectangle(image, (x+165, 290), (x+225, 335), (30, 30, 30), 2)
                cv2.rectangle(image, (x+8, 140), (x+65, 235), (30, 30, 30), 2)
            success, png = cv2.imencode('.png', image)
            assert success
            page.locator('#fileInput').set_input_files({'name': 'furnished-onboarding.png',
                                                       'mimeType': 'image/png', 'buffer': png.tobytes()})
            page.wait_for_function('state.suggestions.length === 2 && !state.suggesting')
            project = page.evaluate('state.project')
            assert project != args.reference_project
            assert all(item['pixel_area'] > 140000 for item in page.evaluate('state.suggestions'))
            page.get_by_role('textbox', name='Name for proposed room 1', exact=True).fill('Living room')
            page.locator('#distanceInput').fill('6')
            page.locator('#calibrateButton').click()
            canvas = page.locator('#planCanvas')
            canvas.scroll_into_view_if_needed()

            def click_pixel(point):
                screen = canvas.evaluate('(canvas,p)=>{const r=canvas.getBoundingClientRect();return [r.x+p[0]*r.width/canvas.width,r.y+p[1]*r.height/canvas.height];}', point)
                page.mouse.click(*screen)

            for point in [[80, 620], [480, 620]]:
                click_pixel(point)
            page.wait_for_function('state.plan.calibration !== null')
            assert math.isclose(page.evaluate('state.plan.calibration.pixels_per_meter'), 400/6, abs_tol=.01)
            page.locator('#acceptSuggestions').click()
            page.wait_for_function('!state.furnishing && state.plan.asset_placements.length >= 2 && document.getElementById("saveState").textContent === "Saved"', timeout=60000)
            placements = page.evaluate('state.plan.asset_placements')
            assert len({item['id'] for item in placements}) == len(placements)
            assert all('full-size' in item['provenance'] and item['size_xyz_m'] for item in placements)
            assert all('size' not in item and 'scale' not in item for item in placements)
            decisions = page.evaluate('state.plan.reconstruction_decisions')
            unknown = page.evaluate('state.plan.rooms[1].id')
            assert any(item.get('room_id') == unknown and item.get('status') == 'skipped' and 'purpose' in item['summary'] for item in decisions)
            page.locator('#furnitureReview summary').click()
            assert 'Room 2:' in page.locator('#furnitureDecisions').inner_text()

            page.locator('[data-style-id="contemporary"]').click()
            page.locator('#generateButton').click()
            page.wait_for_function('state.generated !== null', timeout=60000)
            imports = {item['id']: item for item in page.evaluate('state.generated.result.asset_imports')}
            assert len(imports) == len(placements)
            for item in placements:
                assert all(math.isclose(a, b, abs_tol=1e-5) for a, b in zip(item['size_xyz_m'], imports[item['id']]['size_xyz_m'])), item
            # Capture the complete proposal before later removal/race checks.
            capture('#canvasArea', 'furnished-onboarding-plan.png')
            capture('.assets-panel', 'furnished-onboarding-assets.png')
            first = placements[0]
            page.get_by_role('button', name='Move ' + first['name'], exact=True).click()
            target = [first['position'][0]+.10, first['position'][1]+.10, first['position'][2]]
            pixel = page.evaluate('point => metresToPixel(point)', target[:2])
            canvas.scroll_into_view_if_needed()
            click_pixel(pixel)
            page.wait_for_function('document.getElementById("saveState").textContent === "Saved"')
            saved = page.request.get(f'{origin}/api/projects/{project}').json()['plan']['asset_placements']
            moved = next(item for item in saved if item['id'] == first['id'])
            assert all(math.isclose(a, b, abs_tol=.015) for a, b in zip(moved['position'], target)), (moved, target)
            assert moved['size_xyz_m'] == first['size_xyz_m']
            page.locator('#suggestFurniture').click()
            page.wait_for_function('!state.furnishing && document.getElementById("saveState").textContent === "Saved"')
            assert page.evaluate('state.plan.asset_placements') == saved
            page.locator('#modelSettings summary').click()
            for kind in ['office', 'home']:
                page.locator('#structureType').select_option(kind)
                page.wait_for_function('!state.furnishing && document.getElementById("saveState").textContent === "Saved"')
                assert page.evaluate('state.plan.asset_placements') == saved

            # Hold a real response while an actual form edit makes it stale.
            page.get_by_role('button', name='Remove furnishing ' + first['name'], exact=True).click()
            page.wait_for_function('document.getElementById("saveState").textContent === "Saved"')
            remaining = page.evaluate('state.plan.asset_placements')
            pending = []
            page.route('**/suggest-furniture*', lambda route: pending.append(route))
            with page.expect_request('**/suggest-furniture*'):
                page.locator('#suggestFurniture').click()
            page.wait_for_timeout(20)
            response = pending[0].fetch()
            assert response.ok and response.json()['placements'], 'The held response must propose a replacement.'
            survivor = remaining[0]
            field = page.get_by_role('spinbutton', name=f"X of {survivor['name']} in metres", exact=True)
            target_x = survivor['position'][0] + .08
            field.fill(str(target_x))
            field.press('Tab')
            pending[0].fulfill(response=response)
            page.unroute('**/suggest-furniture*')
            page.wait_for_function('!state.furnishing && document.getElementById("saveState").textContent === "Saved"')
            assert 'layout changed during placement' in page.locator('#furnitureStatus').inner_text().lower()
            current = page.evaluate('state.plan.asset_placements')
            assert len(current) == len(remaining)
            assert next(item for item in current if item['id'] == survivor['id'])['position'][0] == target_x
            assert page.request.get(f'{origin}/api/projects/{args.reference_project}').json()['plan'] == reference
            final_stream = page.request.get(origin + '/api/stream/status').json()
            assert all(final_stream.get(key) == initial_stream.get(key) for key in ['running', 'project_id', 'style'])
            assert not errors, errors
            report = {'passed': True, 'reference_project_unchanged': args.reference_project,
                      'real_image_suggestions': 0, 'scratch_project': project, 'structural_rooms': 2,
                      'automatic_furnishings': len(placements), 'physical_sizes_match_usd': True,
                      'move_saved': True, 'repeat_no_duplicates': True, 'building_type_preserves_edits': True,
                      'unknown_room_explained': True, 'stale_furniture_response_ignored': True,
                      'page_errors': errors}
            (artifacts / 'furnished-onboarding-result.json').write_text(json.dumps(report, indent=2))
            print(json.dumps(report))
        except Exception:
            page.screenshot(path=str(artifacts / 'furnished-onboarding-failure.png'), full_page=True)
            print(json.dumps(page.evaluate('({project:state.project, rooms:state.plan?.rooms?.length, placements:state.plan?.asset_placements?.length, furnishing:state.furnishing, message:document.getElementById("furnitureStatus").textContent})')))
            raise
        finally:
            browser.close()


if __name__ == '__main__':
    main()
