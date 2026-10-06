"""Live editor -> saved plan -> USD add/move/rotate/remove check on a scratch project.

Run with Studio on port 8001 and its real SimReady gallery configured:
    .venv/bin/python tests/check_asset_editing.py
"""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright
from pxr import Usd, UsdGeom


ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8001"


def main():
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path="/opt/google/chrome/chrome", headless=True,
            args=["--no-sandbox"],
        )
        page = browser.new_page(viewport={"width": 1600, "height": 1100})
        page.on("pageerror", lambda error: errors.append(str(error)))
        response = page.request.post(f"{BASE}/api/examples/b1-1502")
        assert response.ok, response.text()
        scratch = response.json()["id"]
        page.goto(f"{BASE}/?project={scratch}")
        page.wait_for_function("state.image && state.assets.length > 0")
        assert page.evaluate("state.project") == scratch
        page.locator(".assets-panel summary").click()
        while page.locator("#placementList button").count():
            page.locator("#placementList button").first.click()
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
        prim = stage.GetPrimAtPath(prim_path)
        assert list(prim.GetAttribute("xformOp:translate").Get()) == target
        assert prim.GetAttribute("xformOp:rotateZ").Get() == 90
        bound = list(UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_]).ComputeWorldBound(prim).ComputeAlignedBox().GetSize())
        assert all(abs(a-b) < .00001 for a, b in zip(bound, [original_bound[1], original_bound[0], original_bound[2]])), (original_bound, bound)
        stage = None
        page.get_by_role("button", name="Remove furnishing Armchair", exact=True).click()
        page.wait_for_function("document.querySelector('#saveState').textContent === 'Saved'")
        assert not page.request.get(f"{BASE}/api/projects/{scratch}").json()["plan"]["asset_placements"]
        removed = generate()
        assert not removed["asset_imports"]
        stage = Usd.Stage.Open(str(ROOT / "output" / scratch / "contemporary.usda"))
        assert not stage.GetPrimAtPath(prim_path)
        assert not errors, errors
        print(json.dumps({"passed": True, "scratch_project": scratch, "position_m": target, "rotation_deg": 90, "size_xyz_m": original_size, "removed_from_usd": True, "page_errors": errors}))
        browser.close()


if __name__ == "__main__":
    main()
