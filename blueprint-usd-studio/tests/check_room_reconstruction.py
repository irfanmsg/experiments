"""Actual uploaded drawing -> named wall outlines -> confirmed OCR scale -> USD.

The original project is read-only. Reconstruction and asset editing use a fresh
upload of the same image. Requires the local reference upload and asset library.
"""
import argparse
import json
import math
from pathlib import Path

from playwright.sync_api import sync_playwright
from shapely.geometry import Point, Polygon


def assert_reconstructed_rooms(suggestions):
    # Ground truth read visually from the supplied 1290x2796 drawing, independent
    # of the detector: include furniture AND circulation, reject adjacent rooms.
    expected = {
        'bedroom 3': {'inside': [(470, 590), (570, 675)],
                      'outside': [(250, 600), (670, 653), (490, 370)],
                      'area': (50000, 110000), 'dimensions': [3.048, 4.0386]},
        'kitchen': {'inside': [(270, 620), (184, 610)],
                    'outside': [(470, 590), (450, 950), (280, 385)],
                    'area': (45000, 110000), 'dimensions': [2.7432, 4.0894]},
        'bedroom 2': {'inside': [(923, 710), (840, 620)],
                      'outside': [(850, 450), (650, 760), (1100, 820)],
                      'area': (50000, 115000), 'dimensions': [3.9624, 3.3528]},
    }
    matched = {}
    for name, truth in expected.items():
        candidates = [item for item in suggestions if (item.get('name') or item.get('label', '')).strip().lower() == name]
        assert len(candidates) == 1, (name, [(item.get('name'), item.get('label')) for item in suggestions])
        candidate = candidates[0]
        shape = Polygon(candidate['pixel_polygon'])
        assert shape.is_valid and truth['area'][0] < shape.area < truth['area'][1], (name, shape.area)
        assert all(shape.covers(Point(point)) for point in truth['inside']), (name, candidate['pixel_polygon'])
        assert all(not shape.covers(Point(point)) for point in truth['outside']), (name, candidate['pixel_polygon'])
        assert candidate['wall_evidence'] and candidate['dimension_evidence'], name
        evidence = candidate['dimension_evidence']
        values = evidence['dimensions_m']
        if name == 'bedroom 3' and values is None:
            # The raster loses the apostrophe in 10'0". Never require the OCR
            # parser to invent a unit marker merely to satisfy this fixture.
            assert evidence['status'] == 'ambiguous' and evidence['warning']
            parts = evidence['dimension_parts_m']
            assert parts[0] is None and math.isclose(parts[1], 4.0386, abs_tol=.005)
        else:
            assert values and len(values) == 2 and all(math.isclose(a, b, abs_tol=.005) for a, b in zip(sorted(values), sorted(truth['dimensions']))), (name, values)
        assert candidate.get('confidence') == 'needs-review', name
        matched[name] = candidate
    return matched


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://10.46.71.211:18001')
    parser.add_argument('--reference-project', default='b8c1fbd8870c')
    args = parser.parse_args()
    origin = args.url.rstrip('/')
    artifacts = Path(__file__).resolve().parents[1] / 'output/qa'
    artifacts.mkdir(parents=True, exist_ok=True)
    errors, writes = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path='/opt/google/chrome/chrome', headless=True, args=['--no-sandbox'])
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
                page.locator(selector).screenshot(path=str(artifacts / filename))
            finally:
                style.evaluate('(style) => style.remove()')

        try:
            reference_response = page.request.get(f'{origin}/api/projects/{args.reference_project}').json()
            reference = reference_response['plan']
            source_image = page.request.get(origin + reference_response['image_url']).body()
            initial_stream = page.request.get(origin + '/api/stream/status').json()
            page.route('**/api/**', read_only)
            page.goto(f'{origin}/?project={args.reference_project}')
            page.wait_for_function('state.image && !state.suggesting && state.scaleProposal && state.suggestions.length > 0', timeout=120000)
            detected = page.evaluate('state.suggestions')
            matched = assert_reconstructed_rooms(detected)
            disagreements = [(index, item) for index, item in enumerate(detected)
                             if (item.get('max_dimension_relative_error') or 0) > .075]
            assert disagreements, 'The undersized Servant Room must be flagged for review.'
            for index, item in disagreements:
                assert not item['selected']
                assert not page.get_by_role('checkbox', name=f'Use proposed room {index+1}', exact=True).is_checked()
                assert 'disagreement with a printed dimension' in page.locator('#suggestions .suggestion').nth(index).inner_text()
            assert all(item['selected'] for item in matched.values())
            scale = page.evaluate('state.scaleProposal')
            assert 70 < scale['pixels_per_meter'] < 90, scale
            assert len({observation['room_name'] for observation in scale['observations']}) >= 2
            assert scale['review_note'] and all('relative_error' in observation for observation in scale['observations'])
            assert page.locator('#useDetectedScale').is_visible()
            assert page.locator('#manualScale').get_attribute('open') is None
            assert page.locator('#distanceInput').input_value() == ''
            assert page.locator('#scaleEvidence li').count() == len(scale['observations'])
            assert any(item.get('inferred_boundaries') for item in matched.values())
            capture('#canvasArea', 'reconstructed-reference-outlines.png')
            expanded = page.add_style_tag(content='.canvas-scroll { max-height: none !important; height: auto !important; overflow: visible !important; }')
            try:
                capture('#canvasArea', 'reconstructed-reference-full-plan.png')
            finally:
                expanded.evaluate('(style) => style.remove()')
            capture('#outlineCard', 'reconstructed-reference-evidence.png')
            capture('#measureCard', 'reconstructed-reference-scale.png')
            assert not writes
            page.unroute('**/api/**', read_only)

            page.locator('#fileInput').set_input_files({'name': 'room-reconstruction-reference.png',
                                                       'mimeType': 'image/png', 'buffer': source_image})
            page.wait_for_function('(previous) => state.project !== previous && state.image && !state.suggesting && state.scaleProposal && state.suggestions.length > 0', arg=args.reference_project, timeout=120000)
            project = page.evaluate('state.project')
            assert_reconstructed_rooms(page.evaluate('state.suggestions'))
            page.locator('#useDetectedScale').click()
            assert page.evaluate('state.plan.calibration.pixels_per_meter') == scale['pixels_per_meter']
            assert page.evaluate('state.points.length') == 0
            assert page.locator('#distanceInput').input_value() == ''
            selected = page.evaluate('state.suggestions.filter(item => item.selected).map(item => item.reviewName)')
            page.locator('#acceptSuggestions').click()
            page.wait_for_function('state.plan.rooms.length > 0 && !state.furnishing && document.getElementById("saveState").textContent === "Saved"', timeout=60000)
            saved = page.request.get(f'{origin}/api/projects/{project}').json()['plan']
            assert sorted(room['name'] for room in saved['rooms']) == sorted(selected)
            for name, candidate in matched.items():
                room = next(room for room in saved['rooms'] if room['name'].lower() == name)
                assert room['source_evidence']['walls'] == candidate['wall_evidence']
                evidence = candidate['dimension_evidence']
                assert room['printed_dimensions_m'] == (evidence['dimensions_m'] or evidence['dimension_parts_m'])
                assert 'accepted by user' in room['geometry_provenance']
                assert 'dimension_mode' not in room, 'OCR readings must not be presented as enforced clear-room dimensions.'
            assert saved['calibration']['basis'].startswith('Printed dimensions matched')
            assert len(saved['calibration']['reference_dimensions']) >= 2
            assert any(item['kind'] == 'drawing-scale' for item in saved['reconstruction_decisions'])
            gaps = saved['openings']
            assert gaps and all(item['image_inferred'] and item['confidence'] == 'needs-review' for item in gaps)
            assert all(item['no_header'] and item['type'] == 'opening' and item['provenance']['basis'] for item in gaps)
            gap = gaps[0]
            page.locator('#reconstructionReview summary').click()
            classification = page.get_by_role('combobox', name=f"Type of {gap['name']}", exact=True)
            for choice in ['door', 'passage']:
                classification.select_option(choice)
                page.wait_for_function('document.getElementById("saveState").textContent === "Saved"')
                saved_gap = next(item for item in page.request.get(f'{origin}/api/projects/{project}').json()['plan']['openings'] if item['id'] == gap['id'])
                assert saved_gap['classification'] == choice
                assert saved_gap['no_header'] == (choice == 'passage')
                assert saved_gap['type'] == ('door' if choice == 'door' else 'opening')
                assert 'by the user' in saved_gap['provenance']['review_status']
                if choice == 'door':
                    assert saved_gap['height_m'] == 2.1 and 'assumption' in saved_gap['provenance']['height']
                else:
                    assert 'height_m' not in saved_gap

            # Use a separate full-size library asset so the check does not depend
            # on a particular bed being installed or automatically proposed.
            before_ids = {item['id'] for item in saved.get('asset_placements', [])}
            page.get_by_role('button', name='Armchair Physical size:', exact=False).click()
            page.locator('#canvasArea').scroll_into_view_if_needed()
            canvas = page.locator('#planCanvas')
            screen = canvas.evaluate('''(canvas,p) => {
                const scroller=canvas.parentElement;
                scroller.scrollTop=Math.max(0,p[1]*canvas.getBoundingClientRect().width/canvas.width-scroller.clientHeight/2);
                const r=canvas.getBoundingClientRect();
                return [r.x+p[0]*r.width/canvas.width,r.y+p[1]*r.height/canvas.height];
            }''', [570, 675])
            page.mouse.click(*screen)
            page.wait_for_function('(before) => state.plan.asset_placements.length > before && document.getElementById("saveState").textContent === "Saved"', arg=len(before_ids))
            armchair = next(item for item in page.evaluate('state.plan.asset_placements') if item['id'] not in before_ids)
            page.locator('[data-style-id="contemporary"]').click()
            page.locator('#generateButton').click()
            page.wait_for_function('state.generated !== null', timeout=60000)
            generated = page.evaluate('state.generated.result')
            assert generated['room_count'] == len(selected)
            from pxr import Gf, Usd, UsdGeom
            stage = Usd.Stage.Open(generated['usd_path'])
            world = stage.GetPrimAtPath('/World')
            exported_gaps = json.loads(world.GetCustomDataByKey('openingTrace'))
            assert next(item for item in exported_gaps if item['id'] == gap['id']) == saved_gap
            assert json.loads(world.GetCustomDataByKey('scaleAudit'))
            # A full-height gap must stay empty at both body and lintel height.
            # Transform probe points into each rendered wall cube, so rotated
            # walls cannot make an axis-aligned bounds check falsely pass.
            wall = stage.GetPrimAtPath('/World/Building/Walls/' + gap['wall_id'])
            assert wall and list(wall.GetChildren())
            transforms = UsdGeom.XformCache()
            for z in [.5, generated['height_m']-.15]:
                probe = Gf.Vec3d(*gap['center'], z)
                for piece in wall.GetChildren():
                    if piece.IsA(UsdGeom.Cube):
                        local = transforms.GetLocalToWorldTransform(piece).GetInverse().Transform(probe)
                        half = UsdGeom.Cube(piece).GetSizeAttr().Get()/2
                        assert not all(abs(value) < half-1e-5 for value in local), (gap['id'], str(piece.GetPath()), z)
            imported = next(item for item in generated['asset_imports'] if item['id'] == armchair['id'])
            assert imported['source_units_m'] == 1
            assert math.isclose(imported['size_xyz_m'][2], .8555029845, abs_tol=.0001)
            field = page.get_by_role('spinbutton', name=f"X of {armchair['name']} in metres", exact=True).last
            field.fill(str(armchair['position'][0]+.1))
            field.press('Tab')
            page.wait_for_function('document.getElementById("saveState").textContent === "Saved"')
            final_plan = page.request.get(f'{origin}/api/projects/{project}').json()['plan']
            edited = next(item for item in final_plan['asset_placements'] if item['id'] == armchair['id'])
            assert math.isclose(edited['position'][0], armchair['position'][0]+.1)
            assert final_plan['rooms'] == saved['rooms']
            page.reload()
            page.wait_for_function('state.image && state.plan.calibration && state.plan.rooms.length > 0')
            assert page.evaluate('state.plan') == final_plan
            assert page.request.get(f'{origin}/api/projects/{args.reference_project}').json()['plan'] == reference
            final_stream = page.request.get(origin + '/api/stream/status').json()
            assert all(final_stream.get(key) == initial_stream.get(key) for key in ['running', 'project_id', 'style'])
            assert not errors, errors
            report = {'passed': True, 'url': origin, 'reference_project_unchanged': args.reference_project,
                      'scratch_project': project, 'quality_checked_rooms': list(matched),
                      'detected_rooms': len(detected), 'scale_pixels_per_meter': scale['pixels_per_meter'],
                      'accepted_rooms': len(selected), 'dimension_disagreements_unselected': len(disagreements),
                      'manual_scale_points': 0, 'room_evidence_persisted': True,
                      'inferred_openings': len(gaps), 'opening_classification_persisted': True,
                      'usd_full_height_gap_verified': True,
                      'usd_room_count': generated['room_count'], 'editable_asset_size_m': imported['size_xyz_m'],
                      'page_errors': errors}
            (artifacts / 'room-reconstruction-result.json').write_text(json.dumps(report, indent=2))
            print(json.dumps(report))
        finally:
            browser.close()


if __name__ == '__main__':
    main()
