#!/usr/bin/env python3
"""
Playwright-based script to fetch v2 files from webbuilder API.

Outputs:
1) Individual JSON files in site_manager/static/block_import/data/files_v2/{uuid}.json
2) Legacy consolidated JSON: site_manager/static/block_import/data/files_v2.json
3) Site-specific UUID-keyed JSON: site_manager/static/block_import/data/{V2_SITE_ID}_files.json
4) Permalink metadata cache (file_v2.json) via ensure_metadata_files
"""

import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from site_manager.permalink_converter import ensure_metadata_files

# Load environment variables
load_dotenv()

# Configuration
USERNAME = os.getenv('USERNAME')
PASSWORD = os.getenv('PASSWORD')
INSTANCE_ID = os.getenv('INSTANCE_ID', '').strip()
V2_SITE_ID = os.getenv('V2_SITE_ID', '').strip() or INSTANCE_ID
INTERACTIVE_BROWSER = os.getenv('FETCH_FILES_V2_INTERACTIVE_BROWSER', '1').strip().lower() in {'1', 'true', 'yes', 'on'}
MANUAL_LOGIN_WAIT_SECONDS_RAW = os.getenv('FETCH_FILES_V2_MANUAL_LOGIN_WAIT_SECONDS', '300').strip()
try:
    MANUAL_LOGIN_WAIT_SECONDS = max(30, min(900, int(MANUAL_LOGIN_WAIT_SECONDS_RAW)))
except Exception:
    MANUAL_LOGIN_WAIT_SECONDS = 300

# Output paths
OUTPUT_DIR = Path('site_manager/static/block_import/data/files_v2')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LEGACY_CONSOLIDATED_FILE = OUTPUT_DIR.parent / 'files_v2.json'
SITE_CONSOLIDATED_FILE = OUTPUT_DIR.parent / f'{V2_SITE_ID}_files.json'


class WebBuilderAPIFetcher:
    """Fetch files data from webbuilder API using Playwright-authenticated requests."""

    def __init__(self, instance_id: str, v2_site_id: str):
        self.instance_id = str(instance_id).strip()
        self.v2_site_id = str(v2_site_id).strip()

    @staticmethod
    def _is_authenticated_webbuilder_url(url: str) -> bool:
        current = (url or '').lower()
        if 'webbuilder.pfizer' not in current:
            return False
        blocked_fragments = ['/login', '/sso/login', 'authorization.ping', 'prodfederate.pfizer.com']
        return not any(fragment in current for fragment in blocked_fragments)

    def _wait_for_authenticated_session(self, page, timeout_ms: int = 60000) -> bool:
        deadline = time.time() + (timeout_ms / 1000)
        while time.time() < deadline:
            if self._is_authenticated_webbuilder_url(page.url):
                return True
            page.wait_for_timeout(1000)
        return False

    def _login_and_get_api_context(self, playwright):
        browser = playwright.chromium.launch(headless=not INTERACTIVE_BROWSER)
        page = browser.new_page()

        print('Opening dashboard and establishing authenticated session...')
        page.goto('https://webbuilder.pfizer/webbuilder/dashboard', wait_until='networkidle')

        try:
            login_button_xpath = 'xpath=//*[@id="app"]/div[1]/div[1]/div[1]/div/div[2]/a'
            if page.locator(login_button_xpath).first.is_visible():
                page.locator(login_button_xpath).first.click()
                page.wait_for_load_state('networkidle')
                page.wait_for_timeout(1500)

            username_selectors = [
                '#username',
                "input[name='username']",
                "input[name='pf.username']",
                "input[type='email']",
            ]
            password_selectors = [
                '#password',
                "input[name='password']",
                "input[type='password']",
            ]

            def first_visible_locator(selectors):
                for selector in selectors:
                    locator = page.locator(selector).first
                    try:
                        if locator.is_visible():
                            return locator
                    except Exception:
                        continue
                return None

            if 'prodfederate.pfizer.com' in (page.url or '').lower():
                print(f'Detected PingFederate login page: {page.url}')

            username_locator = None
            password_locator = None
            for _ in range(20):
                username_locator = first_visible_locator(username_selectors)
                password_locator = first_visible_locator(password_selectors)
                if username_locator and password_locator:
                    break
                page.wait_for_timeout(1000)

            if username_locator and password_locator:
                if not USERNAME or not PASSWORD:
                    raise RuntimeError('USERNAME/PASSWORD are required for login flow but missing in environment')

                print('Submitting credentials from environment variables...')
                username_locator.fill(USERNAME)
                password_locator.fill(PASSWORD)

                submit_locators = [
                    page.locator("button[type='submit']").first,
                    page.locator("input[type='submit']").first,
                    page.locator('#signOnButton').first,
                ]
                submitted = False
                for submit_locator in submit_locators:
                    try:
                        if submit_locator.is_visible():
                            submit_locator.click()
                            submitted = True
                            break
                    except Exception:
                        continue

                if not submitted:
                    password_locator.press('Enter')

                page.wait_for_load_state('networkidle')
                page.wait_for_timeout(2500)
            else:
                print('Session appears already authenticated (SSO/no credentials prompt).')
        except Exception as error:
            print(f'Warning: login interaction error: {error}')

        initial_timeout = 120000 if INTERACTIVE_BROWSER else 60000
        if not self._wait_for_authenticated_session(page, timeout_ms=initial_timeout):
            if INTERACTIVE_BROWSER:
                print(
                    'Authentication not complete yet. '
                    f'Waiting up to {MANUAL_LOGIN_WAIT_SECONDS}s for manual login in browser...'
                )
                if not self._wait_for_authenticated_session(page, timeout_ms=MANUAL_LOGIN_WAIT_SECONDS * 1000):
                    raise RuntimeError(
                        f'Authentication did not complete. Current URL: {page.url}. '
                        'Session is still on login/SSO redirect after manual wait window.'
                    )
            else:
                raise RuntimeError(
                    f'Authentication did not complete. Current URL: {page.url}. '
                    'Session is still on login/SSO redirect.'
                )

        page.wait_for_timeout(1500)

        csrf_token = None
        try:
            csrf_token = page.locator("meta[name='csrf-token']").first.get_attribute('content')
        except Exception:
            csrf_token = None

        return browser, page.context.request, csrf_token

    def fetch_all_files(self):
        """Fetch paginated files from API until no more data."""
        all_files = []
        page_num = 1
        last_page = None
        per_page = None
        total = None

        with sync_playwright() as playwright:
            browser, api_context, csrf_token = self._login_and_get_api_context(playwright)

            try:
                while True:
                    url = f'https://webbuilder.pfizer/api/builder/dashboard/website/{self.instance_id}/files'
                    params = {
                        'page': page_num,
                        'deleted': 'false',
                        'latest': 'true',
                        'version': self.v2_site_id,
                        'website': self.instance_id,
                    }

                    print(f'Fetching page {page_num}: {url}')
                    request_headers = {
                        'User-Agent': (
                            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                            'AppleWebKit/537.36 (KHTML, like Gecko) '
                            'Chrome/124.0.0.0 Safari/537.36'
                        ),
                        'Accept': 'application/json, text/plain, */*',
                        'Origin': 'https://webbuilder.pfizer',
                        'Referer': 'https://webbuilder.pfizer/webbuilder/dashboard',
                        'X-Requested-With': 'XMLHttpRequest',
                    }
                    if csrf_token:
                        request_headers['X-CSRF-TOKEN'] = csrf_token

                    response = api_context.get(url, params=params, headers=request_headers, timeout=30000)
                    status = response.status
                    response_url = response.url
                    body_text = response.text()

                    if status != 200:
                        raise RuntimeError(
                            f'API returned HTTP {status} for page {page_num}. URL={response_url}. '
                            f'Body preview={body_text[:300]}'
                        )

                    if '/login' in response_url.lower() or body_text.lstrip().startswith('<!DOCTYPE html'):
                        raise RuntimeError(
                            'API returned HTML/login page instead of JSON. '
                            'Authentication/session is not valid for API calls.'
                        )

                    try:
                        data = response.json()
                    except json.JSONDecodeError as error:
                        raise RuntimeError(f'Invalid JSON response on page {page_num}: {error}') from error

                    files_section = data.get('files', {}) if isinstance(data, dict) else {}
                    if not isinstance(files_section, dict):
                        raise RuntimeError(f'Unexpected files payload structure on page {page_num}')

                    page_files = files_section.get('data', []) or []
                    last_page = files_section.get('last_page', last_page)
                    per_page = files_section.get('per_page', per_page)
                    total = files_section.get('total', total)

                    if not page_files:
                        print(f'No data on page {page_num}. Ending pagination.')
                        break

                    all_files.extend(page_files)
                    print(
                        f'  -> Page {page_num}: {len(page_files)} files '
                        f'(running total: {len(all_files)})'
                    )

                    has_next = bool(files_section.get('next_page_url'))
                    if (last_page and page_num < int(last_page)) or has_next:
                        page_num += 1
                        time.sleep(0.5)
                        continue

                    print('Reached last page from pagination metadata.')
                    break
            finally:
                browser.close()

        return all_files, {'last_page': last_page, 'per_page': per_page, 'total': total}

    @staticmethod
    def _file_json_payload(file_data):
        uuid_value = file_data.get('uuid')
        return {
            'details': {
                'filename': file_data.get('filename', ''),
                'filetype': file_data.get('filetype', ''),
                'created_at': file_data.get('created_at', ''),
                'updated_at': file_data.get('updated_at', ''),
                'deleted_at': file_data.get('deleted_at'),
                'hash': file_data.get('hash'),
                'filepath': file_data.get('filepath', ''),
                'url': file_data.get('url'),
                'footer_file': file_data.get('footer_file', 0),
                'header_file': file_data.get('header_file', 0),
                'only_on_deployment': file_data.get('only_on_deployment', 0),
                'deploy_on': file_data.get('deploy_on', 'all'),
                'private': file_data.get('private', False),
                'hidden': file_data.get('hidden', False),
                'locked': file_data.get('locked', 0),
                'category': file_data.get('category', ''),
                'weight': file_data.get('weight', 0),
                'attachment_id': file_data.get('attachment_id'),
                'async': file_data.get('async', False),
                'modular': file_data.get('modular', False),
                'non_modular_version': file_data.get('non_modular_version'),
                'filesize': file_data.get('filesize', 0),
                'uuid': uuid_value,
            },
            'hash': file_data.get('hash', ''),
        }

    def write_outputs(self, files, pagination_meta):
        """Write individual files and both consolidated outputs."""
        print(f'Writing {len(files)} individual JSON files to {OUTPUT_DIR}')

        for file_data in files:
            uuid_value = file_data.get('uuid')
            if not uuid_value:
                continue
            output_file = OUTPUT_DIR / f'{uuid_value}.json'
            with open(output_file, 'w', encoding='utf-8') as handle:
                json.dump(self._file_json_payload(file_data), handle, indent=2, ensure_ascii=False)

        legacy_payload = {
            'files': {
                'current_page': 1,
                'data': files,
                'total': pagination_meta.get('total') if pagination_meta.get('total') is not None else len(files),
                'last_page': pagination_meta.get('last_page'),
                'per_page': pagination_meta.get('per_page'),
            }
        }
        with open(LEGACY_CONSOLIDATED_FILE, 'w', encoding='utf-8') as handle:
            json.dump(legacy_payload, handle, indent=2, ensure_ascii=False)

        site_payload = {
            file_data.get('uuid'): {
                'created_at': file_data.get('created_at', ''),
                'deleted_at': file_data.get('deleted_at'),
                'filename': file_data.get('filename', ''),
                'filepath': file_data.get('filepath', ''),
                'filesize': file_data.get('filesize', 0),
                'filetype': file_data.get('filetype', ''),
                'hash': file_data.get('hash'),
                'normalized_filename': file_data.get('filename', ''),
                'source_json': f"{file_data.get('uuid')}.json",
                'updated_at': file_data.get('updated_at', ''),
                'url': file_data.get('url'),
                'uuid': file_data.get('uuid'),
            }
            for file_data in files
            if file_data.get('uuid')
        }
        with open(SITE_CONSOLIDATED_FILE, 'w', encoding='utf-8') as handle:
            json.dump(site_payload, handle, indent=2, ensure_ascii=False)

        print(f'Wrote legacy consolidated file: {LEGACY_CONSOLIDATED_FILE}')
        print(f'Wrote site consolidated file: {SITE_CONSOLIDATED_FILE}')

        metadata_status = ensure_metadata_files(
            files_dir=str(OUTPUT_DIR.parent / 'files'),
            files_v2_dir=str(OUTPUT_DIR),
            v1_site_id=self.instance_id,
            v2_site_id=self.v2_site_id,
        )
        print('Prepared permalink metadata:')
        print(f"  file_v2: {metadata_status.get('file_v2_path')} ({metadata_status.get('file_v2_count')} entries)")


def main():
    if not INSTANCE_ID or not V2_SITE_ID:
        print('Error: INSTANCE_ID and V2_SITE_ID must be set in .env')
        return 1

    if not INSTANCE_ID.isdigit():
        print(f"Error: INSTANCE_ID must be numeric. Received '{INSTANCE_ID}'")
        return 1

    fetcher = WebBuilderAPIFetcher(INSTANCE_ID, V2_SITE_ID)

    try:
        files, pagination_meta = fetcher.fetch_all_files()
        if not files:
            print('No files returned by API.')
            return 2

        print(f'Total files fetched: {len(files)}')
        print(
            'Pagination summary: '
            f"last_page={pagination_meta.get('last_page')}, "
            f"per_page={pagination_meta.get('per_page')}, "
            f"total={pagination_meta.get('total')}"
        )

        fetcher.write_outputs(files, pagination_meta)
        print('Done.')
        return 0
    except Exception as error:
        print(f'Error: {error}')
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
