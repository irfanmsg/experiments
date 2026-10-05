"""Playwright acceptance check against a running GPU stream.

Run: .venv/bin/python tests/check_live_view.py
For 4K: add --width 3840 --height 2160
Requires Playwright and the workstation's Chrome. Leaves the stream running.
"""
import argparse
import json
import math
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8088/?signal_port=49100')
    parser.add_argument('--width', type=int, default=1280)
    parser.add_argument('--height', type=int, default=720)
    args = parser.parse_args()
    url = urlsplit(args.url)
    origin = f'{url.scheme}://{url.netloc}'
    artifacts = Path(__file__).parents[1] / 'output/qa'
    artifacts.mkdir(parents=True, exist_ok=True)
    prefix = f'viewer-{args.width}x{args.height}'
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path='/opt/google/chrome/chrome', headless=True,
                                             args=['--no-sandbox'])
        page = browser.new_page(viewport={'width':1440, 'height':900})
        page.on('pageerror', lambda error: errors.append(str(error)))
        try:
            page.goto(args.url)
            page.wait_for_function("document.querySelector('video').currentTime > 2", timeout=45000)
            page.wait_for_function("document.querySelectorAll('#room-select option').length > 1")
            scene = page.request.get(origin + '/api/scene').json()
            if scene.get('reconstruction_decisions'):
                assert scene['up_axis'] == 'Z', scene['up_axis']
                assert scene['scale_audit']['meters_per_unit'] == 1
                for room in scene['rooms']:
                    assert all(math.isclose(a, b, abs_tol=2e-6) for a, b in zip(room['modeled_dimensions'], room['dimensions'])), room
                openings = {opening['id']: opening for opening in scene['openings']}
                assert {'outer_north_balcony_slider', 'outer_south_balcony_slider'} <= openings.keys()
                expected = ['bathroom_north', 'bedroom_north'] if scene.get('reference_manifest') else ['bathroom_north', 'north_circulation']
                assert openings['north_toilet_door']['connects'] == expected
                ruler = page.locator('#metric-ruler')
                assert float(ruler.get_attribute('x2')) - float(ruler.get_attribute('x1')) == 5
                page.locator('#reconstruction-details summary').click()
                assert scene['reconstruction_decisions'][0]['id'] in page.locator('#reconstruction-list').inner_text()
                page.locator('#reconstruction-details summary').click()
                page.locator('#room-select').select_option('bedroom_north')
                assert 'Door to' in page.locator('#room-access').inner_text()
                if scene.get('reference_manifest'):
                    assert 'bathroom_north' in openings['north_toilet_door']['connects']
                    assert 'powder_room_door' in openings
                    assert len(scene['reference_manifest']['sources']) == 20
                    assert scene['reference_manifest']['construction_photo_review']['summary']['file_count'] == 11
                    assert scene.get('presentation_decisions'), 'Specified home details should retain their assumptions'
                if scene.get('assets'):
                    assert all(asset['source_units_m'] > 0 and max(asset['size_xyz_m']) < 5 for asset in scene['assets'])
                    page.locator('#asset-scale-details summary').click()
                    assert 'converted without fitting to the room' in page.locator('#asset-scale-list').inner_text()
                    page.locator('#asset-scale-details summary').click()
            video = page.locator('video')
            state = video.evaluate('(v)=>({time:v.currentTime,width:v.videoWidth,height:v.videoHeight,paused:v.paused,frames:v.getVideoPlaybackQuality().totalVideoFrames})')
            assert state['width'] == args.width and state['height'] == args.height and not state['paused'], state
            bounds = video.bounding_box()
            assert bounds['width'] > 1000 and bounds['height'] > 560, bounds
            assert page.evaluate('document.documentElement.scrollHeight <= innerHeight')
            page.locator('#overview-button').click()
            page.wait_for_timeout(500)
            overview = page.request.get(origin + '/api/scene').json()['camera']
            assert overview['view'] == 'overview', overview
            page.screenshot(path=str(artifacts/f'{prefix}-overview.png'))

            page.locator('#source-button').click()
            assert page.locator('#source-compare').is_visible()
            assert scene['walls'], 'Source comparison should include the actual selected drawing trace'
            assert page.locator('#source-compare line').count() == len(scene['walls'])
            assert page.locator('#source-compare').evaluate('(s)=>{const r=s.getBoundingClientRect();return !!document.elementFromPoint(r.x+r.width/2,r.y+r.height/2).closest("#source-compare")}')
            page.wait_for_timeout(300)
            page.screenshot(path=str(artifacts/f'{prefix}-source-comparison.png'))

            page.locator('#plan-button').click()
            assert page.locator('#source-compare').is_hidden()
            page.wait_for_timeout(1500)
            plan = page.request.get(origin + '/api/scene').json()['camera']
            assert plan['view'] == 'plan' and math.isclose(plan['pitch'], math.pi / 2, abs_tol=.001), plan
            page.screenshot(path=str(artifacts/f'{prefix}-plan.png'))

            page.locator('#room-select').select_option('living_dining')
            assert '9.83 × 4.03 m' in page.locator('#room-dimensions').inner_text()
            page.locator('#room-button').click()
            page.wait_for_timeout(1500)
            page.screenshot(path=str(artifacts/f'{prefix}-living.png'))
            before = page.request.get(origin + '/api/scene').json()['camera']
            box = video.bounding_box()
            x, y = box['x']+box['width']/2, box['y']+box['height']/2
            page.mouse.move(x,y)
            page.mouse.down()
            page.mouse.move(x+90,y+20,steps=10)
            page.mouse.up()
            page.wait_for_timeout(400)
            after = page.request.get(origin + '/api/scene').json()['camera']
            assert abs(after['yaw']-before['yaw']) > .05, (before,after)

            # Losing focus while the pointer stays inside must not swallow the next drag.
            page.mouse.move(x,y)
            video.evaluate('(v)=>v.blur()')
            assert video.evaluate('(v)=>document.activeElement !== v')
            page.mouse.down()
            page.mouse.move(x+90,y+20,steps=10)
            page.mouse.up()
            page.wait_for_timeout(400)
            refocused = page.request.get(origin + '/api/scene').json()['camera']
            assert abs(refocused['yaw']-after['yaw']) > .05, (after,refocused)

            page.mouse.wheel(0,-120)
            page.wait_for_timeout(400)
            zoomed = page.request.get(origin + '/api/scene').json()['camera']
            assert zoomed['radius'] < refocused['radius'], (refocused,zoomed)

            page.locator('#interior-button').click()
            page.wait_for_timeout(1500)
            assert page.request.get(origin + '/api/scene').json()['camera']['view'] == 'interior'
            page.screenshot(path=str(artifacts/f'{prefix}-interior.png'))
            if scene.get('reference_manifest'):
                for room_id in ('bedroom_outer_south', 'kitchen', 'bathroom_north'):
                    page.locator('#room-select').select_option(room_id)
                    page.locator('#room-button').click()
                    page.wait_for_timeout(1500)
                    page.screenshot(path=str(artifacts/f'{prefix}-{room_id}.png'))
            page.locator('#reset-button').click()
            page.wait_for_timeout(500)
            reset = page.request.get(origin + '/api/scene').json()['camera']
            assert reset['view'] == 'overview', reset
            assert all(math.isclose(reset[key], overview[key], abs_tol=1e-6) for key in ('radius','yaw','pitch')), (overview,reset)
            page.set_viewport_size({'width':1920,'height':1080})
            page.wait_for_timeout(300)
            fit = video.bounding_box()
            page.locator('#size-button').click()
            page.wait_for_timeout(300)
            compact = video.bounding_box()
            assert compact['width'] <= args.width + 1 and compact['width'] <= fit['width'] + 1, (fit,compact)
            assert compact['height'] <= args.height + 1, compact
            page.locator('#size-button').click()
            page.locator('#plan-toggle').click()
            page.wait_for_timeout(300)
            assert page.locator('aside').is_hidden()
            page.locator('#plan-toggle').click()
            page.locator('#fullscreen-button').click()
            page.wait_for_function('Boolean(document.fullscreenElement)')
            page.evaluate('document.exitFullscreen()')
            page.set_viewport_size({'width':390,'height':844})
            page.wait_for_timeout(400)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert page.evaluate('document.documentElement.scrollHeight <= innerHeight')
            mobile = video.bounding_box()
            assert mobile['x'] >= 0 and mobile['width'] <= 390
            page.screenshot(path=str(artifacts/f'{prefix}-mobile.png'))
            later = video.evaluate('(v)=>({time:v.currentTime,frames:v.getVideoPlaybackQuality().totalVideoFrames})')
            assert later['time'] > state['time']+5 and later['frames'] > state['frames']+30
            assert not errors, errors
            result = {'passed':True,'url':args.url,'desktop_video':bounds,'mobile_video':mobile,'video_start':state,'video_end':later,
                      'reconstruction': {'openings':len(scene.get('openings', [])), 'assets':len(scene.get('assets', [])), 'scale_audit':scene.get('scale_audit', {})},
                      'camera':{'overview':overview,'top':plan,'before_drag':before,'after_drag':after,'after_blurred_drag':refocused,'zoomed':zoomed,'reset':reset},'page_errors':errors}
            (artifacts/f'{prefix}-result.json').write_text(json.dumps(result, indent=2))
            print(json.dumps(result))
        finally:
            try:
                page.request.post(origin + '/api/camera',data={'view':'overview'})
                page.evaluate("document.querySelector('#disconnect-button').click()")
            finally:
                browser.close()


if __name__ == '__main__':
    main()
