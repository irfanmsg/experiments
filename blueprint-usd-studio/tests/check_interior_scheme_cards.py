"""Check real scheme cards after at least one scheme has rendered.

Run with Studio running: .venv/bin/python tests/check_interior_scheme_cards.py
Uses actual project metadata and PNGs; blocks writes and never controls a stream.
"""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8001')
    parser.add_argument('--project', default='6078b80f440b')
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
                writes.append(route.request.method + ' ' + route.request.url)
                route.abort()
            else:
                route.continue_()

        page.route('**/api/**', read_only)
        try:
            response = page.request.get(f'{origin}/api/projects/{args.project}')
            assert response.ok, response.status
            before = response.json()
            schemes = [style for style in before['styles'] if style.get('is_design_scheme')]
            assert len(schemes) == 5, schemes
            assert {'indian_contemporary', 'bohemian'} <= {style['id'] for style in schemes}
            previews = [style for style in schemes if style.get('preview_url')]
            assert previews, 'Render a scheme first: this check requires a real PNG preview.'
            page.goto(f'{origin}/?project={args.project}')
            page.wait_for_function('state.image && state.plan && state.styles.length')
            cards = page.locator('#schemeChoices .scheme-card')
            assert cards.count() == len(schemes)
            assert page.locator('#interiorSchemes').is_visible()
            assert page.locator('#finishPresets').is_visible()
            assert page.locator('#finishChoices [role=radio]').count() >= 1
            assert page.locator('#styleChoices [aria-checked=true]').get_attribute('data-style-id') == schemes[0]['id']

            for style in schemes:
                card = cards.filter(has=page.locator(f'[data-style-id="{style["id"]}"]'))
                assert card.locator('.scheme-features li').all_text_contents() == style['design_features']
                assert card.locator('.scheme-references a').evaluate_all('(links) => links.map(link => link.href)') == style['reference_urls']
                assert card.locator('button a').count() == 0
                card.scroll_into_view_if_needed()
                if style.get('preview_url'):
                    preview = page.request.get(origin + style['preview_url'])
                    assert preview.ok and preview.headers['content-type'].startswith('image/png')
                    assert preview.body().startswith(b'\x89PNG\r\n\x1a\n')
                    card.locator('img').wait_for()
                    page.wait_for_function('(id) => { const img = document.querySelector(`[data-style-id="${id}"] img`); return img && img.complete && img.naturalWidth > 0; }', arg=style['id'])
                    assert card.locator('.scheme-preview-caption').is_visible()
                    assert card.locator('.scheme-preview-pending').is_hidden()
                else:
                    assert card.locator('.scheme-preview-pending').is_visible()

            first = page.locator(f'[data-style-id="{schemes[0]["id"]}"]')
            first.focus()
            page.keyboard.press('ArrowRight')
            assert page.locator('#styleChoices [aria-checked=true]').get_attribute('data-style-id') == schemes[1]['id']
            assert page.locator('#styleChoices [tabindex="0"]').count() == 1
            assert page.evaluate('document.activeElement.dataset.styleId') == schemes[1]['id']
            page.keyboard.press('End')
            assert page.locator('#finishChoices [role=radio]').last.get_attribute('aria-checked') == 'true'
            page.keyboard.press('Home')
            assert first.get_attribute('aria-checked') == 'true'
            page.locator('#createPanel').screenshot(path=str(artifacts / 'interior-scheme-cards.png'))
            page.set_viewport_size({'width': 390, 'height': 844})
            for card in cards.all():
                card.scroll_into_view_if_needed()
                assert card.evaluate('(card) => { const box = card.getBoundingClientRect(); return box.left >= 0 && box.right <= innerWidth; }')
            page.locator('#createPanel').screenshot(path=str(artifacts / 'interior-scheme-cards-mobile.png'))

            # Dispatch the real edit handler, cancelling autosave in the same JS task.
            # The route guard above blocks accidental writes even if this regresses.
            page.evaluate('''() => {
                const input = document.getElementById('heightInput');
                input.value = Number(input.value) + .1;
                input.dispatchEvent(new Event('change', {bubbles: true}));
                clearTimeout(state.saveTimer);
            }''')
            assert page.locator('#schemeChoices img').count() == 0
            assert page.locator('#schemeChoices .scheme-preview-pending:visible').count() == len(schemes)
            assert page.request.get(f'{origin}/api/projects/{args.project}').json()['plan'] == before['plan']
            assert not errors and not writes, {'errors': errors, 'writes': writes}
            report = {'passed': True, 'project': args.project, 'schemes': [style['id'] for style in schemes],
                      'rendered_previews': [style['id'] for style in previews], 'keyboard_selection': True,
                      'mobile_cards_fit': True, 'unsaved_edit_clears_previews': True,
                      'saved_plan_unchanged': True, 'page_errors': errors}
            (artifacts / 'interior-scheme-cards-result.json').write_text(json.dumps(report, indent=2))
            print(json.dumps(report))
        finally:
            browser.close()


if __name__ == '__main__':
    main()
