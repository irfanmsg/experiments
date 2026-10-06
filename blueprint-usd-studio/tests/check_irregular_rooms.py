"""Read-only hosted checks against visually inspected source-space floor areas.

These anchors describe the private 1290x2796 reference drawing, not detector
output. They include fixtures and furniture within rooms, while excluding
neighboring rooms, ducts, exterior wedges and the area beyond curved railings.
"""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright
from shapely.geometry import Point, Polygon


EXPECTED = {
    'main curved balcony': ('balcony', [(1080, 700), (1180, 1000), (1080, 1300)],
                            [(1235, 1000), (1160, 600), (900, 1000), (1050, 1500)]),
    'dry balcony': ('dry balcony', [(275, 375), (330, 415)],
                    [(280, 500), (475, 375), (300, 275)]),
    'upper balcony': ('balcony', [(500, 380), (585, 410)],
                      [(490, 550), (300, 375), (500, 280)]),
    'lower balcony': ('balcony', [(160, 1700), (300, 1650), (130, 1780), (110, 1810)],
                      [(330, 1800), (330, 1830), (220, 1550), (420, 1700)]),
    'entrance lobby': ('entrance lobby', [(170, 930), (200, 1020)],
                       [(90, 980), (170, 820), (380, 970)]),
    'service toilet': ('toilet', [(90, 170), (180, 205)],
                       [(140, 270), (140, 100), (250, 180)]),
    'bedroom 3 toilet': ('toilet', [(665, 445), (680, 530), (675, 580)],
                         [(665, 645), (500, 520), (820, 470)]),
    'bedroom 2 toilet': ('toilet', [(850, 475), (775, 485)],
                         [(880, 600), (975, 480), (665, 480)]),
    'bedroom 1 toilet': ('toilet', [(440, 1450), (430, 1570)],
                         [(330, 1480), (550, 1480), (430, 1700)]),
    'master toilet': ('toilet', [(800, 1450), (860, 1510)],
                      [(690, 1470), (850, 1360), (960, 1470), (850, 1580)]),
    'powder room': ('powder room', [(670, 655), (665, 690)],
                    [(680, 560), (570, 670), (675, 745)]),
}


def check_irregular_rooms(suggestions):
    matched, failures = {}, []
    for description, (name, inside, outside) in EXPECTED.items():
        candidates = [(item, Polygon(item['pixel_polygon'])) for item in suggestions
                      if name in (item.get('name') or item.get('label', '')).lower()]
        covering = [(item, shape) for item, shape in candidates
                    if shape.is_valid and all(shape.covers(Point(p)) for p in inside)]
        if len(covering) != 1:
            failures.append(f'{description}: expected one outline covering {inside}; got {len(covering)}')
            continue
        item, shape = covering[0]
        leaked = [p for p in outside if shape.covers(Point(p))]
        if leaked:
            failures.append(f'{description}: outline includes neighboring/exterior points {leaked}')
        if description == 'main curved balcony' and len(item['pixel_polygon']) <= 4:
            failures.append('main curved balcony: boundary is still a rectangle')
        if not item.get('wall_evidence'):
            failures.append(f'{description}: boundary evidence is missing')
        matched[description] = item
    assert not failures, '\n'.join(failures)
    return matched


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://10.46.71.211:8001')
    parser.add_argument('--project', default='b8c1fbd8870c')
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
            if route.request.method in ('GET', 'HEAD', 'OPTIONS'):
                route.continue_()
            else:
                writes.append(route.request.url)
                route.abort()

        try:
            reference = page.request.get(f'{origin}/api/projects/{args.project}').json()['plan']
            stream = page.request.get(origin + '/api/stream/status').json()
            page.route('**/api/**', read_only)
            page.goto(f'{origin}/?project={args.project}')
            page.wait_for_function('state.image && !state.suggesting && state.suggestions.length > 0',
                                   timeout=120000)
            page.add_style_tag(content='.canvas-scroll { max-height:none!important; height:auto!important; overflow:visible!important; } .topbar { visibility:hidden!important; }')
            page.locator('#canvasArea').screenshot(path=str(artifacts / 'irregular-room-outlines.png'))
            suggestions = page.evaluate('state.suggestions')
            (artifacts / 'irregular-room-suggestions.json').write_text(json.dumps(suggestions, indent=2))
            assert page.request.get(f'{origin}/api/projects/{args.project}').json()['plan'] == reference
            final_stream = page.request.get(origin + '/api/stream/status').json()
            assert all(final_stream.get(key) == stream.get(key)
                       for key in ['running', 'project_id', 'style', 'quality'])
            assert not errors and not writes, (errors, writes)
            matched = check_irregular_rooms(suggestions)
            report = {'passed': True, 'url': origin, 'source_project_unchanged': args.project,
                      'stream_unchanged': True, 'checked_spaces': list(matched),
                      'suggestion_count': len(suggestions), 'page_errors': errors}
            (artifacts / 'irregular-room-result.json').write_text(json.dumps(report, indent=2))
            print(json.dumps(report))
        finally:
            browser.close()


if __name__ == '__main__':
    main()
