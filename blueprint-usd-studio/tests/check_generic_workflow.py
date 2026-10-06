"""Exercise a real scratch upload, generic schemes and editable USD furnishings.

Run against a Studio server: .venv/bin/python tests/check_generic_workflow.py --url http://127.0.0.1:8001
Creates its own project and imported test asset; never edits an existing project.
"""
import argparse
import io
import json
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright
from pxr import Usd, UsdGeom


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8001')
    args = parser.parse_args()
    origin = args.url.rstrip('/')
    errors = []
    png = io.BytesIO()
    Image.new('RGB', (1200, 900), 'white').save(png, format='PNG')
    artifacts = ROOT / 'output/qa'
    artifacts.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path='/opt/google/chrome/chrome',
                                             headless=True, args=['--no-sandbox'])
        page = browser.new_page(viewport={'width': 1600, 'height': 1100})
        page.on('pageerror', lambda error: errors.append(str(error)))
        try:
            page.goto(origin)
            page.locator('#fileInput').set_input_files({'name': 'Generic-workflow-QA.png',
                                                       'mimeType': 'image/png', 'buffer': png.getvalue()})
            page.wait_for_function("state.project && state.plan?.source?.filename === 'Generic-workflow-QA.png' && state.image")
            project = page.evaluate('state.project')
            plan = page.request.get(f'{origin}/api/projects/{project}').json()['plan']
            polygon = [[0, 0], [10, 0], [10, 8], [0, 8]]
            plan.update({'name': 'Generic workflow QA', 'calibration': {'pixels_per_meter': 80, 'pixel_origin': [100, 800]},
                         'footprint': {'polygon': polygon},
                         'rooms': [{'id': 'custom-room-42', 'name': 'Family space', 'category': 'living', 'polygon': polygon}]})
            response = page.request.put(f'{origin}/api/projects/{project}/plan', data=plan)
            assert response.ok and not response.json()['validation_errors'], response.text()
            page.goto(f'{origin}/?project={project}')
            page.wait_for_function('state.image && state.plan?.rooms?.length === 1')
            assert page.locator('#schemeChoices .scheme-card').count() == 5
            assert page.locator('[data-style-id="home_specification"]').count() == 0
            assert page.locator('#starterFurniture').is_hidden()
            page.locator('[data-style-id="bohemian"]').click()

            def saved():
                page.wait_for_function("document.querySelector('#saveState').textContent === 'Saved'")

            def generate():
                page.locator('#generateButton').click()
                page.wait_for_function('state.generated !== null', timeout=60000)
                return page.evaluate('state.generated.result')

            result = generate()
            assert not result['asset_imports']
            assert result['editable_objects']
            assert next(a for a in result['runtime_trace']['actions'] if a['id'] == 'usd_authoring')['status'] == 'executed'
            obj = next(item for item in result['editable_objects'] if item['name'] == 'rug')
            target = [obj['position'][0]+.25, obj['position'][1]-.25, obj['position'][2]]
            # Generated-object selectors below follow the same accessible labels
            # as the independently editable referenced-asset controls.
            for label, value in [(f"X of {obj['name']} in metres", target[0]),
                                 (f"Y of {obj['name']} in metres", target[1]),
                                 (f"Rotation of {obj['name']} in degrees", 90)]:
                field = page.get_by_role('spinbutton', name=label, exact=True)
                field.fill(str(value))
                field.press('Tab')
                saved()
            changed = generate()
            stage = Usd.Stage.Open(changed['usd_path'])
            prim = stage.GetPrimAtPath(obj['id'])
            assert list(prim.GetAttribute('xformOp:translate').Get()) == target
            assert prim.GetAttribute('xformOp:rotateZ').Get() == 90
            bound = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render']).ComputeWorldBound(prim).ComputeAlignedBox()
            assert all(abs(a-b) < 1e-6 for a, b in zip(bound.GetSize(), [obj['size_xyz_m'][1], obj['size_xyz_m'][0], obj['size_xyz_m'][2]]))
            stage = None
            page.get_by_role('button', name=f"Remove furnishing {obj['name']}", exact=True).click()
            saved()
            removed = generate()
            assert not any(item['id'] == obj['id'] for item in removed['editable_objects'])
            stage = Usd.Stage.Open(removed['usd_path'])
            assert not stage.GetPrimAtPath(obj['id']).IsActive()
            stage = None

            def pixel(point):
                return page.evaluate('''p => {
                    const [x,y] = metresToPixel(p), r = canvas.getBoundingClientRect();
                    return [r.x+x*r.width/canvas.width, r.y+y*r.height/canvas.height];
                }''', point)

            page.get_by_role('button', name='Armchair Physical size:', exact=False).click()
            page.locator('#planCanvas').scroll_into_view_if_needed()
            page.mouse.click(*pixel([8, 6]))
            saved()
            page.locator('#clearTool').click()
            page.locator('#planCanvas').scroll_into_view_if_needed()
            original = page.evaluate('state.plan.asset_placements[0]')
            start, end = pixel(original['position']), pixel([7.25, 5.25])
            page.mouse.move(*start)
            page.mouse.down()
            page.mouse.move(*end, steps=8)
            page.mouse.up()
            saved()
            placement = page.evaluate('state.plan.asset_placements[0]')
            assert all(abs(a-b) <= .015 for a, b in zip(placement['position'], [7.25, 5.25, 0])), placement
            dragged = generate()
            imported = next(item for item in dragged['asset_imports'] if item['id'] == placement['id'])
            assert all(abs(a-b) < .01 for a, b in zip(imported['size_xyz_m'], [1.118, .963, .856]))
            assert imported['position_m'] == placement['position']

            usd = b'''#usda 1.0
(defaultPrim = "QAAsset"\n metersPerUnit = 0.01\n upAxis = "Z")
def Cube "QAAsset" {
    double size = 100
}
'''
            page.locator('#assetImportInput').set_input_files({'name': 'QA-cube.usda',
                                                             'mimeType': 'application/octet-stream', 'buffer': usd})
            page.wait_for_function("state.selectedAsset?.name?.includes('QA-cube') && state.tool === 'asset'", timeout=30000)
            imported_asset = page.evaluate('state.selectedAsset')
            assert imported_asset.get('asset_kind') != 'NVIDIA SimReady USD'
            page.locator('#planCanvas').scroll_into_view_if_needed()
            page.mouse.click(*pixel([6, 2]))
            saved()
            added = generate()
            cube_placement = page.evaluate('state.plan.asset_placements[1]')
            cube_import = next(item for item in added['asset_imports'] if item['id'] == cube_placement['id'])
            assert cube_import['size_xyz_m'] == [1, 1, 1]
            assert cube_import['source_units_m'] == .01
            assert cube_import['position_m'] == cube_placement['position']
            page.reload()
            page.wait_for_function('state.image && state.plan?.asset_placements?.length === 2')
            assert any(asset['usd_path'] == imported_asset['usd_path'] for asset in page.evaluate('state.assets'))
            assert not errors, errors
            page.screenshot(path=str(artifacts / 'generic-workflow.png'), full_page=True)
            report = {'passed': True, 'project': project, 'generic_schemes': 5,
                      'generated_object_moved_rotated_removed': True,
                      'simready_drag_preserves_dimensions': True, 'centimetre_usd_import': True,
                      'page_errors': errors}
            (artifacts / 'generic-workflow-result.json').write_text(json.dumps(report, indent=2))
            print(json.dumps(report))
        finally:
            browser.close()


if __name__ == '__main__':
    main()
