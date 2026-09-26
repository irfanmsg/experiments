"""Playwright acceptance check against a running GPU stream.

Run: .venv/bin/python tests/check_live_view.py
Requires Playwright and the workstation's Chrome. Leaves the stream running.
"""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    artifacts = Path(__file__).parents[1] / 'output/qa'
    artifacts.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path='/opt/google/chrome/chrome', headless=True,
                                             args=['--no-sandbox'])
        page = browser.new_page(viewport={'width':1440, 'height':900})
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('http://192.168.1.32:8088/?signal_port=49100&v=3')
        try:
            page.wait_for_function("document.querySelector('video').currentTime > 2", timeout=45000)
            page.wait_for_function("document.querySelectorAll('#room-select option').length > 1")
            video = page.locator('video')
            state = video.evaluate('(v)=>({time:v.currentTime,width:v.videoWidth,height:v.videoHeight,paused:v.paused,frames:v.getVideoPlaybackQuality().totalVideoFrames})')
            assert state['width'] == 1280 and state['height'] == 720 and not state['paused'], state
            bounds = video.bounding_box()
            assert bounds['width'] > 1000 and bounds['height'] > 560, bounds
            assert page.evaluate('document.documentElement.scrollHeight <= innerHeight')
            page.screenshot(path=str(artifacts/'viewer-overview.png'))

            page.locator('#source-button').click()
            assert page.locator('#source-compare').is_visible()
            assert page.locator('#source-compare line').count() > 60
            assert page.locator('#source-compare').evaluate('(s)=>{const r=s.getBoundingClientRect();return !!document.elementFromPoint(r.x+r.width/2,r.y+r.height/2).closest("#source-compare")}')
            page.wait_for_timeout(300)
            page.screenshot(path=str(artifacts/'viewer-source-comparison.png'))

            page.locator('#plan-button').click()
            assert page.locator('#source-compare').is_hidden()
            page.wait_for_timeout(1500)
            assert page.request.get('http://192.168.1.32:8088/api/scene').json()['camera']['view'] == 'plan'
            page.screenshot(path=str(artifacts/'viewer-plan.png'))

            page.locator('#room-select').select_option('living_dining')
            assert '9.83 × 4.03 m' in page.locator('#room-dimensions').inner_text()
            page.locator('#room-button').click()
            page.wait_for_timeout(1500)
            page.screenshot(path=str(artifacts/'viewer-living.png'))
            before = page.request.get('http://192.168.1.32:8088/api/scene').json()['camera']
            box = video.bounding_box()
            x, y = box['x']+box['width']/2, box['y']+box['height']/2
            page.mouse.move(x,y)
            page.mouse.down()
            page.mouse.move(x+90,y+20,steps=10)
            page.mouse.up()
            page.wait_for_timeout(400)
            after = page.request.get('http://192.168.1.32:8088/api/scene').json()['camera']
            assert abs(after['yaw']-before['yaw']) > .05, (before,after)
            page.mouse.wheel(0,-120)
            page.wait_for_timeout(400)
            zoomed = page.request.get('http://192.168.1.32:8088/api/scene').json()['camera']
            assert zoomed['radius'] < after['radius'], (after,zoomed)

            page.locator('#interior-button').click()
            page.wait_for_timeout(1500)
            assert page.request.get('http://192.168.1.32:8088/api/scene').json()['camera']['view'] == 'interior'
            page.screenshot(path=str(artifacts/'viewer-interior.png'))
            page.locator('#reset-button').click()
            page.set_viewport_size({'width':1920,'height':1080})
            page.wait_for_timeout(300)
            fit = video.bounding_box()
            page.locator('#size-button').click()
            page.wait_for_timeout(300)
            compact = video.bounding_box()
            assert compact['width'] <= 1280 and fit['width'] > compact['width'], (fit,compact)
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
            page.screenshot(path=str(artifacts/'viewer-mobile.png'))
            later = video.evaluate('(v)=>({time:v.currentTime,frames:v.getVideoPlaybackQuality().totalVideoFrames})')
            assert later['time'] > state['time']+5 and later['frames'] > state['frames']+30
            assert not errors, errors
            print(json.dumps({'passed':True,'desktop_video':bounds,'mobile_video':mobile,'video_start':state,'video_end':later,'page_errors':errors}))
        finally:
            page.request.post('http://192.168.1.32:8088/api/camera',data={'view':'overview'})
            page.evaluate("document.querySelector('#disconnect-button').click()")
            browser.close()


if __name__ == '__main__':
    main()
