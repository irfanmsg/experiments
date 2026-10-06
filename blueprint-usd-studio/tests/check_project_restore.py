"""Verify saved-project recovery across independent browser instances.

Run against Studio with a current project streaming and an older saved B1 plan.
Uses actual server data; blocks browser API writes and never controls the stream.
"""
import argparse
import json
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8001')
    parser.add_argument('--project', default='6078b80f440b')
    parser.add_argument('--legacy-project', default='25ce54df6800')
    args = parser.parse_args()
    origin = args.url.rstrip('/')
    errors, writes = [], []

    def read_only(route):
        if route.request.method not in ('GET', 'HEAD', 'OPTIONS'):
            writes.append(route.request.method + ' ' + route.request.url)
            route.abort()
        else:
            route.continue_()

    def loaded(page):
        page.wait_for_function('state.image && state.plan && state.styles.length')

    def assert_project_url(page, project):
        query = parse_qs(urlparse(page.url).query)
        assert query.get('project') == [project], f'Expected project URL for {project}, got {page.url}'
        assert 'example' not in query, page.url

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path='/opt/google/chrome/chrome',
                                             headless=True, args=['--no-sandbox'])
        api = playwright.request.new_context(base_url=origin)
        before = api.get(f'/api/projects/{args.legacy_project}')
        assert before.ok, before.status
        legacy_plan = before.json()['plan']
        status = api.get('/api/stream/status').json()
        assert status.get('running') and status.get('project_id') == args.project, status

        def old_browser():
            context = browser.new_context()
            context.route('**/api/**', read_only)
            context.add_init_script(
                "if (!sessionStorage.getItem('restore-test-seeded')) {"
                f"localStorage.setItem('blueprint-studio-project', {json.dumps(args.legacy_project)});"
                "sessionStorage.setItem('restore-test-seeded', 'true');}"
            )
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            return page

        try:
            first = old_browser()
            first.goto(origin + '/')
            loaded(first)
            assert_project_url(first, args.legacy_project)
            notice = first.locator('#legacyProjectNotice')
            assert notice.is_visible(), 'Older saved layout must explain unavailable schemes'
            assert 'older' in notice.inner_text().lower(), notice.inner_text()
            assert first.locator('#schemeChoices .scheme-card').count() == 0
            updated = notice.locator('#updatedExampleLink')
            assert updated.get_attribute('href') == '/?example=b1-1502'
            live_link = notice.locator('#liveProjectLink')
            live_link.wait_for(state='visible')
            assert parse_qs(urlparse(live_link.get_attribute('href')).query).get('project') == [args.project]
            live_link.click()
            loaded(first)
            assert_project_url(first, args.project)
            assert first.locator('#schemeChoices .scheme-card').count() == 5
            assert first.locator('#legacyProjectNotice').is_hidden()
            copied_url = first.url

            second = old_browser()
            second.goto(copied_url)
            loaded(second)
            for _ in range(2):
                assert_project_url(second, args.project)
                assert second.locator('#schemeChoices .scheme-card').count() == 5
                assert second.locator('#legacyProjectNotice').is_hidden()
                assert second.evaluate("localStorage.getItem('blueprint-studio-project')") == args.project
                second.reload()
                loaded(second)
            assert api.get(f'/api/projects/{args.legacy_project}').json()['plan'] == legacy_plan
            assert not errors and not writes, {'errors': errors, 'writes': writes}
            print(json.dumps({'passed': True, 'legacy_project': args.legacy_project,
                              'project': args.project, 'copied_url': copied_url,
                              'scheme_cards': 5, 'legacy_plan_unchanged': True,
                              'page_errors': errors, 'api_writes': writes}))
        finally:
            browser.close()
            api.dispose()


if __name__ == '__main__':
    main()
