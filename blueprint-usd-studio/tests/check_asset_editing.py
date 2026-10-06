"""Live editor -> saved plan -> USD add/move/rotate/remove check on a scratch project.

Run with Studio on port 8001 and its real SimReady gallery configured:
    uv run --no-sync python tests/check_asset_editing.py
"""

import json
import os
import copy
from pathlib import Path

from playwright.sync_api import sync_playwright
from pxr import Usd, UsdGeom


ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("BLUEPRINT_STUDIO_URL", "http://10.46.71.211:8001")


def main():
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path="/opt/google/chrome/chrome", headless=True,
            args=["--no-sandbox"],
        )
        page = browser.new_page(viewport={"width": 1600, "height": 1100})
        page.on("pageerror", lambda error: errors.append(str(error)))
        protected = page.request.get(f'{BASE}/api/projects/b8c1fbd8870c').json()['plan']
        stream_before = page.request.get(f'{BASE}/api/stream/status').json()
        response = page.request.post(f"{BASE}/api/examples/b1-1502")
        assert response.ok, response.text()
        scratch = response.json()["id"]
        page.goto(f"{BASE}/?project={scratch}")
        page.wait_for_function("state.image && state.assets.length > 0")
        assert page.evaluate("state.project") == scratch
        if not page.locator(".assets-panel").evaluate("el => el.open"):
            page.locator(".assets-panel summary").click()
        while page.locator('#placementList button[aria-label^="Remove furnishing"]').count():
            page.locator('#placementList button[aria-label^="Remove furnishing"]').first.click()
        page.wait_for_function("document.querySelector('#saveState').textContent === 'Saved'")
        page.get_by_role("button", name="Armchair Physical size:", exact=False).click()
        page.locator("#planCanvas").scroll_into_view_if_needed()
        point = page.evaluate("centroid(state.plan.rooms.find(r => r.id === 'living_dining').polygon)")
        pixel = page.evaluate("p => {const [x,y] = metresToPixel(p), r = canvas.getBoundingClientRect(); return [r.x+x*r.width/canvas.width,r.y+y*r.height/canvas.height]}", point)
        page.mouse.click(*pixel)
        page.wait_for_function("state.plan.asset_placements.length === 1 && document.querySelector('#saveState').textContent === 'Saved'")
        page.locator('[data-style-id="contemporary"]').click()

        def generate():
            page.locator("#generateButton").click()
            page.wait_for_function("state.generated !== null", timeout=60000)
            return page.evaluate("state.generated.result")

        before = generate()
        placement = page.evaluate("state.plan.asset_placements[0]")
        original_size = before["asset_imports"][0]["size_xyz_m"]
        stage = Usd.Stage.Open(str(ROOT / "output" / scratch / "contemporary.usda"))
        stage.GetRootLayer().Reload()
        prim_path = f"/World/Assets/{placement['id']}"
        original_bound = list(UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_]).ComputeWorldBound(stage.GetPrimAtPath(prim_path)).ComputeAlignedBox().GetSize())
        stage = None
        # Blank numeric input must not silently place furniture at the origin.
        revision = page.evaluate("state.revision")
        field = page.get_by_role("spinbutton", name="X of Armchair in metres", exact=True)
        field.fill("")
        field.press("Tab")
        assert page.evaluate("state.revision") == revision
        assert page.evaluate("state.plan.asset_placements[0].position") == placement["position"]
        target = [round(placement["position"][0] + .25, 2), round(placement["position"][1] - .35, 2), placement["position"][2]]
        for label, value in [("X of Armchair in metres", target[0]), ("Y of Armchair in metres", target[1]), ("Rotation of Armchair in degrees", 90)]:
            field = page.get_by_role("spinbutton", name=label, exact=True)
            field.fill(str(value))
            field.press("Tab")
            page.wait_for_function("document.querySelector('#saveState').textContent === 'Saved'")
        assert page.evaluate("state.generated") is None
        assert page.evaluate("state.styles.every(style => !style.preview_url)")
        saved = page.request.get(f"{BASE}/api/projects/{scratch}").json()["plan"]["asset_placements"][0]
        assert saved["position"] == target and saved["rotation_deg"] == 90, saved
        after = generate()
        assert after["asset_imports"][0]["size_xyz_m"] == original_size
        stage = Usd.Stage.Open(str(ROOT / "output" / scratch / "contemporary.usda"))
        stage.GetRootLayer().Reload()
        prim = stage.GetPrimAtPath(prim_path)
        assert list(prim.GetAttribute("xformOp:translate").Get()) == target
        assert prim.GetAttribute("xformOp:rotateZ").Get() == 90
        bound = list(UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_]).ComputeWorldBound(prim).ComputeAlignedBox().GetSize())
        assert all(abs(a-b) < .00001 for a, b in zip(bound, [original_bound[1], original_bound[0], original_bound[2]])), (original_bound, bound)
        stage = None
        # Resize independently of native units; inspect actual generated geometry.
        for label, value in [('Width', original_size[0]*1.5), ('Depth', original_size[1]*.75), ('Height', original_size[2]*1.2)]:
            field = page.get_by_role('spinbutton', name=f'{label} of Armchair in metres', exact=True)
            field.fill(str(value)); field.press('Tab')
            page.wait_for_function("document.querySelector('#saveState').textContent === 'Saved'")
        resized = generate()['asset_imports'][0]
        assert resized['scale_xyz'] == [1.5,.75,1.2], resized
        stage = Usd.Stage.Open(str(ROOT / 'output' / scratch / 'contemporary.usda'))
        stage.GetRootLayer().Reload()
        box = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default']).ComputeWorldBound(stage.GetPrimAtPath(prim_path)).ComputeAlignedBox()
        expected = [original_size[1]*.75, original_size[0]*1.5, original_size[2]*1.2]
        assert all(abs(a-b) < 1e-5 for a,b in zip(box.GetSize(),expected))
        stage = None
        # Reject malformed edits before they replace the saved plan.
        valid_plan = page.request.get(f'{BASE}/api/projects/{scratch}').json()['plan']
        for bad in ([0,1,1], [-1,1,1], [True,1,1], [1,2], [1,float('inf'),1]):
            invalid = copy.deepcopy(valid_plan); invalid['asset_placements'][0]['scale_xyz'] = bad
            result = page.request.put(f'{BASE}/api/projects/{scratch}/plan', data=json.dumps(invalid), headers={'Content-Type':'application/json'})
            assert result.status == 400, result.text()
            assert page.request.get(f'{BASE}/api/projects/{scratch}').json()['plan'] == valid_plan
        for key,value in [('position',[0,float('nan'),0]), ('position',[False,0,0]), ('rotation_deg',float('inf'))]:
            invalid = copy.deepcopy(valid_plan); invalid['asset_placements'][0][key] = value
            result = page.request.put(f'{BASE}/api/projects/{scratch}/plan', data=json.dumps(invalid), headers={'Content-Type':'application/json'})
            assert result.status == 400, result.text()
            assert page.request.get(f'{BASE}/api/projects/{scratch}').json()['plan'] == valid_plan
        replacement = page.evaluate("state.assets.find(a => a.name === 'Appleseed Coffee Table')")
        page.get_by_role('combobox', name='Replacement asset for Armchair', exact=True).select_option(replacement['usd_path'])
        page.get_by_role('button', name='Replace Armchair', exact=True).click()
        page.wait_for_function("document.querySelector('#saveState').textContent === 'Saved'")
        current = page.evaluate('state.plan.asset_placements[0]')
        assert current['id'] == placement['id'] and current['position'] == target and current['rotation_deg'] == 90
        assert current['scale_xyz'] == [1,1,1]
        replaced = generate()['asset_imports'][0]
        assert replaced['edit_history'][-1]['action'] == 'replace'
        assert all(abs(a-b) < 1e-3 for a,b in zip(replaced['size_xyz_m'],replacement['size_xyz_m']))
        page.reload(); page.wait_for_function('state.image && state.assets.length > 0')
        page.locator('[data-style-id="contemporary"]').click()
        assert page.evaluate('state.plan.asset_placements[0].asset_path') == replacement['usd_path']
        page.get_by_role('button', name='Select Appleseed Coffee Table', exact=True).click()
        assert page.locator('.placement-row.selected').count() == 1
        page.evaluate('state.selectedPlacement = null; refreshPlacements(); draw()')
        page.locator('#planCanvas').scroll_into_view_if_needed()
        point = page.evaluate("() => {const item = state.plan.asset_placements[0], size = placementSize(item); return [item.position[0]+size[1]*.3,item.position[1]]}")
        pixel = page.evaluate("p => {const [x,y] = metresToPixel(p), r=canvas.getBoundingClientRect();return [r.x+x*r.width/canvas.width,r.y+y*r.height/canvas.height]}",point)
        page.mouse.click(*pixel)
        assert page.evaluate('state.selectedPlacement') == placement['id']
        page.wait_for_function("document.querySelector('#saveState').textContent === 'Saved'")
        page.locator('#placementList').screenshot(path=str(ROOT / 'output/qa/asset-transform-controls.png'))
        page.get_by_role('button', name='Remove furnishing Appleseed Coffee Table', exact=True).click()

        page.wait_for_function("document.querySelector('#saveState').textContent === 'Saved'")
        assert not page.request.get(f"{BASE}/api/projects/{scratch}").json()["plan"]["asset_placements"]
        removed = generate()
        assert not removed["asset_imports"]
        stage = Usd.Stage.Open(str(ROOT / "output" / scratch / "contemporary.usda"))
        stage.GetRootLayer().Reload()
        assert not stage.GetPrimAtPath(prim_path)
        # Generated furnishings use the same controls and can become library assets.
        page.locator('[data-style-id="bohemian"]').click()
        procedural_report = generate()
        item = next(obj for obj in procedural_report['editable_objects'] if obj.get('source_size_xyz_m') and min(obj['source_size_xyz_m']) > .005)
        object_row = page.locator(f'[data-placement-id="{item["id"]}"]')
        field = object_row.get_by_role('spinbutton', name=f"Width of {item['name']} in metres", exact=True)
        field.fill(str(item['source_size_xyz_m'][0]*1.4)); field.press('Tab')
        page.wait_for_function("document.querySelector('#saveState').textContent === 'Saved'")
        scaled_report = generate()
        scaled = next(obj for obj in scaled_report['editable_objects'] if obj['id'] == item['id'])
        assert abs(scaled['scale_xyz'][0]-1.4) < 1e-8
        object_row.get_by_role('button', name=f"Restore source size of {item['name']}", exact=True).click()
        page.wait_for_function("document.querySelector('#saveState').textContent === 'Saved'")
        reset = next(obj for obj in generate()['editable_objects'] if obj['id'] == item['id'])
        assert reset['local_size_xyz_m'] == item['source_size_xyz_m']
        object_row.get_by_role('combobox', name=f"Replacement asset for {item['name']}", exact=True).select_option(replacement['usd_path'])
        object_row.get_by_role('button', name=f"Replace {item['name']}", exact=True).click()
        page.wait_for_function("document.querySelector('#saveState').textContent === 'Saved'")
        converted = generate()
        assert len(converted['asset_imports']) == 1
        assert converted['asset_imports'][0]['position_m'] == item['position']
        assert all(obj['id'] != item['id'] for obj in converted['editable_objects'])
        stage = Usd.Stage.Open(str(ROOT / 'output' / scratch / 'bohemian.usda'))
        stage.GetRootLayer().Reload()
        assert not stage.GetPrimAtPath(item['id']).IsActive()
        assert not any(str(prim.GetPath()).startswith(item['id'] + '/') for prim in stage.Traverse())
        assert page.request.get(f'{BASE}/api/projects/b8c1fbd8870c').json()['plan'] == protected
        stream_after = page.request.get(f'{BASE}/api/stream/status').json()
        for key in ('project_id','style','quality'):
            assert stream_before.get(key) == stream_after.get(key)
        assert not errors, errors
        print(json.dumps({"passed": True, "scratch_project": scratch, "position_m": target, "rotation_deg": 90, "size_xyz_m": original_size, "removed_from_usd": True, "resized_and_replaced": True, "procedural_resize_reset_replace":True, "canvas_footprint_selection":True, "invalid_edits_rejected_before_save": True, "page_errors": errors}))
        browser.close()


if __name__ == "__main__":
    main()
