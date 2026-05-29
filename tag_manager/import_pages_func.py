#!/usr/bin/env python3
"""
Selenium-based migration script for V1 to V2 page migration.
This script automates the process of creating pages in V2 from V1 JSON exports.
"""
import os
import sys
import json
import requests
import time
import platform
from pathlib import Path
from typing import Dict, Any, Optional
from urllib.parse import urlparse

# Ensure Django settings are available if script is run standalone
if not os.environ.get('DJANGO_SETTINGS_MODULE'):
    os.environ['DJANGO_SETTINGS_MODULE'] = 'tag_manager.settings'
try:
    from django.conf import settings
    import django
    django.setup()
except ImportError:
    print("Warning: Django not available. settings.BASE_DIR will not work.")
    settings = None

# Force UTF-8 encoding for console output to handle Chinese characters
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from openpyxl import load_workbook

# Detect OS for cross-platform compatibility
IS_MAC = platform.system() == 'Darwin'
IS_WINDOWS = platform.system() == 'Windows'
IS_LINUX = platform.system() == 'Linux'

# Use appropriate modifier key based on OS
MODIFIER_KEY = Keys.COMMAND if IS_MAC else Keys.CONTROL

"""
Purpose
-------
Batch migrate multiple pages from V1 webbuilder export (JSON files) into a V2 instance, using Selenium.

What it does
------------
1) Loads V2 credentials and instance info from .env
2) Scans the pages directory and reads ALL page JSON files
3) Identifies homepage (slug='index') and skips it for now
4) For each page JSON file:
   a) Extracts settings (title, slug, language, brand, indication, therapeutic area, etc.)
   b) Extracts content (HTML and CSS)
   c) Checks if page already exists (duplicate prevention)
   d) Creates the page via "+ ADD PAGE" modal
   e) Fills in all page settings
   f) Opens "Edit Page" → "Edit Code"
   g) Inserts HTML and CSS into CodeMirror editor:
      <HTML from JSON>
      <style>
      <CSS from JSON>
      </style>
   h) Saves the page
   i) Moves to the next page

5) Generates a final summary report showing:
   - Total pages processed
   - Successfully migrated pages
   - Skipped pages (already exist)
   - Failed pages with error reasons

Features
--------
- Batch processing: Migrates all pages automatically one by one
- Duplicate prevention: Checks if pages already exist before creating
- Homepage detection: Identifies and skips homepage (slug='index')
- Detailed logging: Shows progress for each page
- Error handling: Continues processing even if individual pages fail
- Summary report: Final status of all pages

Configuration
-------------
- Set TARGET_PAGE_JSON_BASENAME = None to process ALL pages (batch mode)
- Set TARGET_PAGE_JSON_BASENAME = "filename.json" to process a single page (testing mode)

Notes
-----
- Cross-platform compatible: Works on Windows, Mac, and Linux
- Automatically detects OS and uses appropriate keyboard shortcuts (Cmd on Mac, Ctrl on Windows/Linux)
- Update DEFAULT_V1_PAGES_DIR path format based on your OS:
  * Windows: r"D:\POC\pages"
  * Mac/Linux: "/Users/username/POC/pages"
- You may need to fine-tune the selectors in SELECTORS below to match your V2 UI
- The script handles SSO/federated login automatically
- Browser stays open for 60 seconds after completion for verification
- Do not modify import_os_func.py as requested; this script is standalone and uses Selenium
"""

# ------------------------------
# Configurable constants
# ------------------------------
DEFAULT_V1_PAGES_DIR = os.path.join(settings.BASE_DIR, 'site_manager', 'static', 'block_import', 'data', 'pages')
# If you want to target a specific page JSON file, set it here; otherwise ALL JSON files will be processed
TARGET_PAGE_JSON_BASENAME = None  # Set to None to process all pages, or specify a filename for single page

# Persist page import progress so interrupted runs can resume without recreating completed pages.
PAGE_IMPORT_PROGRESS_FILENAME = None

# Multi-lingual site support: Set to True if your site supports multiple languages
# When True, pages with the same title but different languages will be created (no duplicate check)
# When False, duplicate page titles will be skipped
IS_MULTILINGUAL_SITE = True  # Set to True for multi-lingual sites, False for single-language sites

# Skip problematic pages: Set to True to continue processing even if some pages fail
# When True, pages that fail validation or have errors will be skipped and logged
# When False, the script will stop on first error (not recommended)
SKIP_FAILED_PAGES = True  # Set to True to continue processing all pages

# Attempted URL to reach the Pages area directly; adjust if your builder uses a different panel key
PAGES_PANEL_KEY = "left-sidebar-settings--pages"  # update if needed

# UI selectors that may vary per tenant/theme; adjust as needed
SELECTORS: Dict[str, str] = {
    # Direct login fields (IDs or names may vary per tenant)
    "username_input": '//*[@id="username"]',
    "password_input": '//*[@id="password"]',

    # Search and open page in Pages Manager (adjust as needed)
    # Provide either a search box selector and a table row selector, or a direct editor open method
    "pages_search_box": '//*[@id="page-search-text-input"]',  # guess; update if different
    "pages_table_rows": 'table tbody tr',  # generic
    # The edit icon within a row; use format with {row_index} if needed; keep generic clickable cell for now
    "page_row_title_cell": 'td:nth-child(1)',  # the title/slug cell to match
    "page_row_click_cell": 'td:nth-child(1)',  # what to click to open editor

    # Inside the page editor: where to insert HTML and CSS
    # Multiple generic candidates; the code will attempt several of these
    "html_textarea": '//*[@id="page-html-textarea"]',  # placeholder; update to actual
    "css_textarea": '//*[@id="page-css-textarea"]',    # placeholder; update to actual
    "combined_code_editor": '//*[@id="page-code-editor"]',  # placeholder; update to actual
    # Generic fallbacks tried programmatically:
    #   //textarea, //*[@contenteditable='true'], //div[contains(@class,'monaco-editor')], //div[contains(@class,'CodeMirror')]

    # Save button inside the page editor
    "save_button": (
        "//button[contains(@class, 'btn') and (contains(., 'Save') or contains(., 'Enregistrer'))]"
    )
}


# ------------------------------
# Utilities
# ------------------------------

def load_env() -> Dict[str, str]:
    load_dotenv()
    env = {
        "SITENAME": os.getenv("SITENAME"),
        "USERNAME": os.getenv("USERNAME"),
        "PASSWORD": os.getenv("PASSWORD"),
        "INSTANCE_ID": os.getenv("INSTANCE_ID"),
    }
    missing = [k for k, v in env.items() if not v]
    if missing:
        raise RuntimeError(f"Missing required .env values: {', '.join(missing)}")
    return env


def pick_one_page_json(pages_dir: str, basename: Optional[str] = None) -> Path:
    p = Path(pages_dir)
    if not p.is_dir():
        raise FileNotFoundError(f"Pages directory not found: {pages_dir}")
    if basename:
        candidate = p / basename
        if not candidate.is_file():
            raise FileNotFoundError(f"Target page JSON not found: {candidate}")
        return candidate
    # fallback: pick the 4th JSON file alphabetically as per user approval
    files = sorted([fp for fp in p.iterdir() if fp.suffix.lower() == ".json"], key=lambda x: x.name.lower())
    if len(files) >= 4:
        return files[3]
    if files:
        return files[0]
    raise FileNotFoundError(f"No JSON files found in {pages_dir}")


def parse_page_json(file_path) -> Dict[str, Any]:
    # Convert to Path if it's a string
    if isinstance(file_path, str):
        file_path = Path(file_path)
    with file_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Check if page is deleted - skip if deleted_at or deleted_by has a value
    settings = data.get("settings", {})
    inner_settings = settings.get("settings", {}) if isinstance(settings, dict) else {}
    
    # Check both settings and settings.settings for deleted fields
    deleted_at = settings.get("deleted_at") or inner_settings.get("deleted_at")
    deleted_by = settings.get("deleted_by") or inner_settings.get("deleted_by")
    
    # If deleted_at is not null/None or deleted_by is not null/None, mark as deleted
    is_deleted = (deleted_at is not None and deleted_at != "" and deleted_at != "null") or \
                 (deleted_by is not None and deleted_by != "" and deleted_by != "null")
    
    if is_deleted:
        print(f"INFO: Page is marked as deleted (deleted_at={deleted_at}, deleted_by={deleted_by})")
        return {"is_deleted": True, "deleted_at": deleted_at, "deleted_by": deleted_by}
    
    # Typical structure observed in the provided exports
    storage = data.get("storage", {})
    storage_data = storage.get("data", {})
    html = storage_data.get("html", "")
    css = storage_data.get("css", "")
    # settings appears twice in some files; prefer root-level for title/uuid
    title = settings.get("title") or storage.get("settings", {}).get("title")
    slug = None
    path = None
    
    # Some files have settings.settings (nested) - check for language there
    inner_settings = settings.get("settings", {}) if isinstance(settings, dict) else {}

    # In some files, nested settings include path/slug/seo; attempt best-effort reads
    # We won't rely on deep traversal here; adjust as needed for your tenant schema
    nested_settings = {}
    seo_title = None
    meta_description = None
    meta_keywords = None
    visibility = None
    parent = None
    template = None
    if isinstance(data.get("storage"), dict):
        # try to find nested settings with path/slug
        # This is a best-effort heuristic; safe if absent
        try:
            nested_settings = data.get("storage", {}).get("data", {}).get("settings", {})
            slug = nested_settings.get("slug") or slug
            path = nested_settings.get("path") or path
            seo_title = nested_settings.get("seo_title") or nested_settings.get("meta_title")
            meta_description = nested_settings.get("meta_description") or nested_settings.get("description")
            meta_keywords = nested_settings.get("meta_keywords") or nested_settings.get("keywords")
            visibility = nested_settings.get("visibility")
            parent = nested_settings.get("parent") or nested_settings.get("parent_id")
            template = nested_settings.get("template") or nested_settings.get("layout")
        except Exception:
            pass

    # Fall back to nested settings under settings/settings (and typo variant settings/sittings),
    # then top-level settings if present
    if not slug and isinstance(inner_settings, dict):
        slug = inner_settings.get("slug")
    if not path and isinstance(inner_settings, dict):
        path = inner_settings.get("path")
    if not slug and isinstance(settings, dict):
        typo_inner_settings = settings.get("sittings", {})
        if isinstance(typo_inner_settings, dict):
            slug = typo_inner_settings.get("slug")
    if not path and isinstance(settings, dict):
        typo_inner_settings = settings.get("sittings", {})
        if isinstance(typo_inner_settings, dict):
            path = typo_inner_settings.get("path")
    if not slug:
        slug = settings.get("slug")
    if not path:
        path = settings.get("path")

    # --- Extract taxonomy terms from relationships ---
    def extract_term_by_vocab_keywords(rels, keywords):
        if not isinstance(rels, list):
            return None
        for rel in rels:
            try:
                vocab = (rel.get("vocabulary") or {}).get("machine_name") or (rel.get("vocabulary") or {}).get("name") or ""
                vocab_l = str(vocab).lower()
                if any(k in vocab_l for k in keywords):
                    term = (rel.get("term") or {}).get("name") or (rel.get("term") or {}).get("machine_name")
                    if term:
                        return str(term).strip()
            except Exception:
                continue
        return None

    # Check multiple locations for relationships/related
    relationships = data.get("relationships") or data.get("storage", {}).get("data", {}).get("relationships") or settings.get("related") or []
    # Brand: extract from vocabulary_id 45
    # Indication: extract from vocabulary_id 48
    # Therapeutic Area: extract from vocabulary_id 51
    brand = None
    indication = None
    therapeutic_area = None
    print(f"DEBUG parse_page_json: Found {len(relationships) if isinstance(relationships, list) else 0} relationships/related items")
    if isinstance(relationships, list):
        for rel in relationships:
            try:
                vocab_id = rel.get("vocabulary_id")
                if vocab_id == 45:
                    term = (rel.get("term") or {}).get("name") or (rel.get("term") or {}).get("machine_name")
                    if term:
                        brand = str(term).strip()
                        print(f"DEBUG parse_page_json: Found brand from vocab_id 45: '{brand}'")
                elif vocab_id == 48:
                    term = (rel.get("term") or {}).get("name") or (rel.get("term") or {}).get("machine_name")
                    if term:
                        indication = str(term).strip()
                        print(f"DEBUG parse_page_json: Found indication from vocab_id 48: '{indication}'")
                elif vocab_id == 51:
                    term = (rel.get("term") or {}).get("name") or (rel.get("term") or {}).get("machine_name")
                    if term:
                        therapeutic_area = str(term).strip()
                        print(f"DEBUG parse_page_json: Found therapeutic_area from vocab_id 51: '{therapeutic_area}'")
            except Exception as e:
                print(f"DEBUG parse_page_json: Error checking relationship: {e}")
                continue
    print(f"DEBUG parse_page_json: Final brand value = '{brand}'")
    print(f"DEBUG parse_page_json: Final indication value = '{indication}'")
    print(f"DEBUG parse_page_json: Final therapeutic_area value = '{therapeutic_area}'")
    # Language: check multiple locations
    # 1. settings.settings.language (inner nested)
    # 2. settings.language (root level)
    # 3. storage.data.settings.language (nested_settings)
    # 4. relationships (taxonomy)
    language = None
    if isinstance(inner_settings, dict):
        language = inner_settings.get("language")
    if not language:
        language = settings.get("language")
    if not language and isinstance(nested_settings, dict):
        language = nested_settings.get("language")
    if not language:
        language = extract_term_by_vocab_keywords(relationships, ["language", "languages"])
    # Note: indication and therapeutic_area are already extracted above by vocabulary_id

    # Hidden: check inner_settings (settings.settings) first, then root settings, then nested
    hidden = None
    if isinstance(inner_settings, dict) and "hidden" in inner_settings:
        hidden = inner_settings.get("hidden")
        print(f"DEBUG parse_page_json: inner_settings.get('hidden') = {hidden}")
    if hidden is None:
        hidden = settings.get("hidden")
        print(f"DEBUG parse_page_json: settings.get('hidden') = {hidden}")
    if hidden is None and isinstance(nested_settings, dict):
        hidden = nested_settings.get("hidden")
        print(f"DEBUG parse_page_json: nested_settings.get('hidden') = {hidden}")
    # If still None, check visibility field
    if hidden is None and isinstance(nested_settings, dict) and "visibility" in nested_settings:
        vis = str(nested_settings.get("visibility")).lower()
        hidden = False if vis in ("visible", "public", "published") else True
    
    # Slug special-chars toggle
    remove_special_slug = None
    if isinstance(nested_settings, dict):
        if "remove_special_characters_from_slug" in nested_settings:
            remove_special_slug = nested_settings.get("remove_special_characters_from_slug")
    
    # Primary Message Category from analytics.meta.primaryMessageCategory
    primary_message_category = None
    if isinstance(inner_settings, dict):
        analytics = inner_settings.get("analytics", {})
        if isinstance(analytics, dict):
            meta = analytics.get("meta", {})
            if isinstance(meta, dict):
                primary_message_category = meta.get("primaryMessageCategory")
    print(f"DEBUG parse_page_json: primaryMessageCategory = {primary_message_category}")

    # Extract additional page settings: public, dynamic, promotional, brand_kit
    # These are typically in nested_settings (storage.data.settings)
    public = None
    dynamic = None
    promotional = None
    brand_kit = None
    
    if isinstance(inner_settings, dict):
        public = inner_settings.get("public")
        dynamic = inner_settings.get("dynamic")
        promotional = inner_settings.get("promotional")
        brand_kit = inner_settings.get("brand_kit")
    
    if public is None and isinstance(nested_settings, dict):
        public = nested_settings.get("public")
    if dynamic is None and isinstance(nested_settings, dict):
        dynamic = nested_settings.get("dynamic")
    if promotional is None and isinstance(nested_settings, dict):
        promotional = nested_settings.get("promotional")
    if brand_kit is None and isinstance(nested_settings, dict):
        brand_kit = nested_settings.get("brand_kit")
    
    print(f"DEBUG parse_page_json: public = {public}")
    print(f"DEBUG parse_page_json: dynamic = {dynamic}")
    print(f"DEBUG parse_page_json: promotional = {promotional}")
    print(f"DEBUG parse_page_json: brand_kit = {brand_kit}")
    
    # Extract SEO settings from inner_settings (settings.settings) first, then nested_settings
    seo_title_val = None
    seo_description = None
    seo_keywords = None
    seo_abstract = None
    exclude_sitemap = None
    private_but_indexable = None
    
    # Try inner_settings first (settings.settings)
    if isinstance(inner_settings, dict):
        seo_title_val = inner_settings.get("seo_title")
        seo_description = inner_settings.get("seo_description")
        seo_keywords = inner_settings.get("seo_keywords")
        seo_abstract = inner_settings.get("seo_abstract")
        exclude_sitemap = inner_settings.get("exclude_sitemap")
        private_but_indexable = inner_settings.get("private_but_indexable")
    
    # Fall back to nested_settings if not found
    if seo_title_val is None and isinstance(nested_settings, dict):
        seo_title_val = nested_settings.get("seo_title")
    if seo_description is None and isinstance(nested_settings, dict):
        seo_description = nested_settings.get("seo_description")
    if seo_keywords is None and isinstance(nested_settings, dict):
        seo_keywords = nested_settings.get("seo_keywords")
    if seo_abstract is None and isinstance(nested_settings, dict):
        seo_abstract = nested_settings.get("seo_abstract")
    if exclude_sitemap is None and isinstance(nested_settings, dict):
        exclude_sitemap = nested_settings.get("exclude_sitemap")
    if private_but_indexable is None and isinstance(nested_settings, dict):
        private_but_indexable = nested_settings.get("private_but_indexable")
    
    print(f"DEBUG parse_page_json: seo_title_val = {seo_title_val}")
    print(f"DEBUG parse_page_json: seo_description = {seo_description}")
    print(f"DEBUG parse_page_json: seo_keywords = {seo_keywords}")
    print(f"DEBUG parse_page_json: seo_abstract = {seo_abstract}")
    print(f"DEBUG parse_page_json: exclude_sitemap = {exclude_sitemap}")
    print(f"DEBUG parse_page_json: private_but_indexable = {private_but_indexable}")

    result = {
        "title": title,
        "slug": slug,
        "path": path,
        "html": html,
        "css": css,
    }
    # Attach optional metadata if present
    for k, v in [("seo_title", locals().get("seo_title", None)),
                 ("meta_description", locals().get("meta_description", None)),
                 ("meta_keywords", locals().get("meta_keywords", None)),
                 ("visibility", locals().get("visibility", None)),
                 ("parent", locals().get("parent", None)),
                 ("template", locals().get("template", None))]:
        if v:
            result[k] = v
    # Attach taxonomy and flags
    if brand:
        result["brand"] = brand
    if language:
        result["language"] = language
    if indication:
        result["indication"] = indication
    if therapeutic_area:
        result["therapeutic_area"] = therapeutic_area
    if hidden is not None:
        result["hidden"] = bool(hidden)
    if remove_special_slug is not None:
        result["remove_special_slug"] = bool(remove_special_slug)
    if primary_message_category:
        result["primary_message_category"] = str(primary_message_category)
    
    # Attach additional page settings
    if public is not None:
        result["public"] = bool(public)
    if dynamic is not None:
        result["dynamic"] = bool(dynamic)
    if promotional is not None:
        result["promotional"] = bool(promotional)
    if brand_kit is not None:
        result["brand_kit"] = str(brand_kit) if brand_kit else ""
    
    # Attach SEO settings
    if seo_title_val is not None:
        result["seo_title_val"] = str(seo_title_val) if seo_title_val else ""
    if seo_description is not None:
        result["seo_description"] = str(seo_description) if seo_description else ""
    if seo_keywords is not None:
        result["seo_keywords"] = str(seo_keywords) if seo_keywords else ""
    if seo_abstract is not None:
        result["seo_abstract"] = str(seo_abstract) if seo_abstract else ""
    if exclude_sitemap is not None:
        result["exclude_sitemap"] = bool(exclude_sitemap)
    if private_but_indexable is not None:
        result["private_but_indexable"] = bool(private_but_indexable)
    
    return result

def convert_v1_to_v2(html: str, css: str) -> str:
    """
    Call Django API to convert V1 HTML and CSS to V2 format.
    Returns the converted content if successful, or the original content if conversion fails.
    """
    api_url = os.getenv("API_URL")
    bearer_token = os.getenv("BEARER_TOKEN")

    headers = {
        'Authorization': f'Bearer {bearer_token}',
        'Content-Type': 'application/json'
    }

    payload = {
        "v1_body": html,
        "v1_css": css,
        "v1_js": ""
    }

    # Validate API URL and token
    if not api_url:
        print("ERROR: API_URL is not set in environment variables")
        return f"{html}\n<style>\n{css}\n</style>"
        
    if not bearer_token:
        print("WARNING: BEARER_TOKEN is not set in environment variables")
        # Continue without token if the API doesn't require it

    # Parse the API URL to check if it's valid
    try:
        parsed_url = urlparse(api_url)
        if not all([parsed_url.scheme, parsed_url.netloc]):
            print(f"ERROR: Invalid API URL: {api_url}")
            return f"{html}\n<style>\n{css}\n</style>"
    except Exception as e:
        print(f"ERROR: Failed to parse API URL: {e}")
        return f"{html}\n<style>\n{css}\n</style>"
    
    print(f"\nCalling V1 to V2 conversion API at: {api_url}")
    print(f"Request payload size - HTML: {len(html)} chars, CSS: {len(css)} chars")
    
    try:
        # Make the API request with a timeout of 60 seconds
        print("Sending request to conversion API...")
        response = requests.post(api_url, json=payload, headers=headers, timeout=60)
        
        print(f"API response status code: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                v2_body = data.get('v2_body', '')
                v2_css = data.get('v2_css', '')
                
                if not v2_body and not v2_css:
                    print("WARNING: API returned empty V2 content. Using original content.")
                    return f"{html}\n<style>\n{css}\n</style>"
                
                print(f"API response received - V2 content size: {len(v2_body) + len(v2_css)} chars")
                return f"{v2_body}\n<style>\n{v2_css}\n</style>"
                
            except json.JSONDecodeError as je:
                print(f"ERROR: Failed to parse API response as JSON: {je}")
                print(f"Response content: {response.text[:500]}..." if len(response.text) > 500 else f"Response content: {response.text}")
        else:
            print(f"ERROR: API request failed with status {response.status_code}")
            print(f"Response headers: {dict(response.headers)}")
            print(f"Response content: {response.text[:500]}..." if len(response.text) > 500 else f"Response content: {response.text}")
            
    except requests.exceptions.Timeout:
        print("ERROR: API request timed out after 60 seconds")
    except requests.exceptions.RequestException as re:
        print(f"ERROR: Request failed: {str(re)}")
    except Exception as e:
        print(f"ERROR: Unexpected error during API call: {str(e)}")
    
    # If we get here, there was an error - return original content
    print("Falling back to original V1 content due to API error")
    return f"{html}\n<style>\n{css}\n</style>"


# ------------------------------
# Selenium flows
# ------------------------------

def dump_debug(driver: webdriver.Chrome, name: str):
    """Save a screenshot and the current page HTML to files next to this script."""
    base = Path(__file__).with_name(name)
    screenshot_path = str(base.with_suffix('.png'))
    html_path = str(base.with_suffix('.html'))
    try:
        driver.save_screenshot(screenshot_path)
    except Exception:
        pass

def scroll_into_view(driver: webdriver.Chrome, el):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});", el)
        time.sleep(0.2)
    except Exception:
        pass

def set_input_by_label(driver: webdriver.Chrome, labels, value) -> bool:
    for label in labels:
        try:
            el = WebDriverWait(driver, 2).until(EC.presence_of_element_located((By.XPATH, f"//label[contains(., '{label}')]/following::input[1]")))
            scroll_into_view(driver, el)
            try:
                el.clear()
            except Exception:
                pass
            el.send_keys(value)
            return True
        except TimeoutException:
            continue
    return False


def open_page_menu_and_update_settings_from_row(driver: webdriver.Chrome, page_title: str, row: Dict[str, Any]) -> bool:
    """Open the page's context menu and update settings using the Excel row mapping."""
    # Reuse selection and menu opening logic from the parsed variant
    try:
        page_item = WebDriverWait(driver, 6).until(EC.element_to_be_clickable((By.XPATH, f"//nav//*[contains(@class,'page') or contains(@class,'item') or self::a or self::div][normalize-space()='{page_title}']")))
        page_item.click(); time.sleep(1)
    except TimeoutException:
        try:
            page_item = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, f"//*[normalize-space()='{page_title}']")))
            page_item.click(); time.sleep(1)
        except TimeoutException:
            dump_debug(driver, "debug_page_select")
            return False

    menu_opened = False
    menu_xpaths = [
        "//div[contains(@class,'context') or contains(@class,'menu') or contains(@class,'actions')]//button",
        "//button[.//i[contains(@class,'fa-ellipsis') or contains(@class,'fa-cog')]]",
        f"(//*[normalize-space()='{page_title}']/following::*[self::button or self::a][1])",
    ]
    for xp in menu_xpaths:
        try:
            btn = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, xp)))
            btn.click(); time.sleep(1)
            menu_opened = True
            break
        except TimeoutException:
            continue
        except Exception:
            continue
    if not menu_opened:
        pass

    # Try Page settings
    try:
        settings_item = WebDriverWait(driver, 4).until(EC.element_to_be_clickable((By.XPATH, "//a[contains(., 'Page settings')] | //button[contains(., 'Page settings')]")))
        settings_item.click(); time.sleep(1)
    except TimeoutException:
        try:
            edit_item = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.XPATH, "//a[contains(., 'Edit Page')] | //button[contains(., 'Edit Page')]")))
            edit_item.click(); time.sleep(1)
        except TimeoutException:
            dump_debug(driver, "debug_page_menu")
            return False

    updated = update_page_settings_from_row(driver, row)
    if not updated:
        dump_debug(driver, "debug_page_settings_update")
        return False
    return True

def set_textarea_by_label(driver: webdriver.Chrome, labels, value) -> bool:
    for label in labels:
        try:
            el = WebDriverWait(driver, 2).until(EC.presence_of_element_located((By.XPATH, f"//label[contains(., '{label}')]/following::textarea[1]")))
            scroll_into_view(driver, el)
            try:
                el.clear()
            except Exception:
                pass
            el.send_keys(value)
            return True
        except TimeoutException:
            continue
    return False

def set_select_by_label(driver: webdriver.Chrome, labels, value) -> bool:
    """Handle native select or custom selects by clicking and typing value."""
    for label in labels:
        try:
            # Try native select
            sel = WebDriverWait(driver, 1).until(EC.presence_of_element_located((By.XPATH, f"//label[contains(., '{label}')]/following::select[1]")))
            scroll_into_view(driver, sel)
            from selenium.webdriver.support.ui import Select
            try:
                Select(sel).select_by_visible_text(value)
            except Exception:
                try:
                    Select(sel).select_by_value(value)
                except Exception:
                    return False
            return True
        except TimeoutException:
            pass
        # Try custom select input
        try:
            box = WebDriverWait(driver, 1).until(EC.element_to_be_clickable((By.XPATH, f"//label[contains(., '{label}')]/following::*[self::div or self::button][1]")))
            scroll_into_view(driver, box)
            box.click(); time.sleep(0.2)
            # Type to filter then Enter
            ActionChains(driver).send_keys(value).send_keys(Keys.ENTER).perform()
            return True
        except TimeoutException:
            continue
        except Exception:
            continue
    return False

def set_checkbox_by_label(driver: webdriver.Chrome, labels, desired: bool) -> bool:
    for label in labels:
        try:
            cb = WebDriverWait(driver, 1).until(EC.presence_of_element_located((By.XPATH, f"//label[contains(., '{label}')]/preceding::input[@type='checkbox'][1] | //label[contains(., '{label}')]/following::input[@type='checkbox'][1]")))
            scroll_into_view(driver, cb)
            checked = cb.is_selected()
            if checked != desired:
                try:
                    cb.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", cb)
            return True
        except TimeoutException:
            continue
    return False
    try:
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
    except Exception:
        pass

def create_driver(headless: bool = False) -> webdriver.Chrome:
    options = ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--start-maximized")
    # Use a separate user data directory to avoid closing existing Chrome windows
    options.add_argument("--user-data-dir=C:\\temp\\chrome_selenium_profile")
    options.add_argument("--profile-directory=SeleniumProfile")
    # Prevent closing other Chrome instances
    options.add_experimental_option("detach", True)
    service = ChromeService(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def wait_for(driver: webdriver.Chrome, by: By, selector: str, timeout: int = 20):
    return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, selector)))


def login_to_dashboard(driver: webdriver.Chrome, sitename: str, username: str, password: str, instance_id: str):
    """Open the base site URL and log in directly using username/password fields.
    Flow provided by user:
      1) Open https://{SITENAME}/login
      2) Click the SSO login button on that page to authenticate
      3) If classic username/password fields exist, use them as fallback
      4) After SSO click, check if redirected to Pfizer federated login page
      5) If federated login page appears, fill username and password from .env
      6) After login, we can navigate to the builder URL
    """
    login_url = f"https://{sitename}/login"
    driver.get(login_url)

    # Try SSO button first with a few heuristics
    sso_candidates = [
        "//button[contains(., 'SSO')]",
        "//a[contains(., 'SSO')]",
        "//button[contains(., 'Sign in') or contains(., 'Login')]",
        "//a[contains(., 'Sign in') or contains(., 'Login')]",
        "//*[@id='app']//a[contains(@href, 'sso') or contains(., 'SSO') or contains(., 'login')]",
    ]
    sso_clicked = False
    for xpath in sso_candidates:
        try:
            elem = WebDriverWait(driver, 6).until(EC.element_to_be_clickable((By.XPATH, xpath)))
            elem.click()
            sso_clicked = True
            break
        except TimeoutException:
            continue

    if not sso_clicked:
        # Fall back to classic username/password if present on the login page
        try:
            usr = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "input#username, input[name='username']")))
            pwd = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "input#password, input[name='password']")))
            usr.clear(); usr.send_keys(username)
            pwd.clear(); pwd.send_keys(password)
            pwd.send_keys(Keys.ENTER)
        except TimeoutException:
            # Diagnostics: save screenshot and page source
            screenshot_path = str(Path(__file__).with_name("debug_login.png"))
            html_path = str(Path(__file__).with_name("debug_login.html"))
            driver.save_screenshot(screenshot_path)
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            raise RuntimeError(f"Could not find SSO button or login fields. Saved screenshot to {screenshot_path} and HTML to {html_path}.")

    # Allow SSO redirect/handshake
    time.sleep(3)
    
    # Check if redirected to Pfizer federated login page (prodfederate.pfizer.com)
    # This happens when the script runs outside the Pfizer network
    current_url = driver.current_url
    print(f"Current URL after SSO click: {current_url}")
    
    if "prodfederate.pfizer.com" in current_url or "authorization.ping" in current_url:
        print(f"Detected Pfizer federated login page: {current_url}")
        try:
            # Look for username field with id="username" or name="pf.username"
            username_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//input[@id='username' or @name='pf.username']"))
            )
            # Look for password field with id="password" or name="pf.pass"
            password_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//input[@id='password' or @name='pf.pass']"))
            )
            
            # Fill in the credentials from .env
            username_field.clear()
            username_field.send_keys(username)
            password_field.clear()
            password_field.send_keys(password)
            
            # Submit the form (press Enter on password field)
            password_field.send_keys(Keys.ENTER)
            
            print("Submitted Pfizer federated login credentials")
            # Wait for redirect after federated login
            time.sleep(5)
            
        except TimeoutException:
            # If federated login fields not found, save debug info
            screenshot_path = str(Path(__file__).with_name("debug_federated_login.png"))
            html_path = str(Path(__file__).with_name("debug_federated_login.html"))
            driver.save_screenshot(screenshot_path)
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            print(f"Warning: Federated login page detected but fields not found. Saved debug files.")
            # Continue anyway in case login succeeded through other means
    else:
        # Not on federated login page - might need manual login
        print("\n" + "="*80)
        print("MANUAL LOGIN REQUIRED")
        print("="*80)
        print("Please complete the login manually in the browser window.")
        print("The script will wait for 30 seconds for you to log in.")
        print("="*80 + "\n")
        time.sleep(30)  # Wait 30 seconds for manual login


def go_to_builder_site(driver: webdriver.Chrome, sitename: str, instance_id: str):
    """Navigate to the builder website root for the given instance."""
    builder_root_url = f"https://{sitename}/builder/website/{instance_id}"
    driver.get(builder_root_url)
    time.sleep(2)

def open_builder_in_new_tab(driver: webdriver.Chrome, sitename: str, instance_id: str):
    """Open the builder website in a new browser tab (per user's flow)."""
    builder_root_url = f"https://{sitename}/builder/website/{instance_id}"
    driver.switch_to.new_window('tab')
    driver.get(builder_root_url)
    time.sleep(2)

def go_to_pages_manager(driver: webdriver.Chrome, sitename: str, instance_id: str):
    """Navigate to Pages Manager panel where we can see the list of all pages."""
    print("Navigating to Pages Manager panel...")
    
    # Direct URL to pages manager - this is the most reliable method
    pages_url = f"https://{sitename}/builder/website/{instance_id}/pages"
    driver.get(pages_url)
    time.sleep(1.5)
    
    # Verify we're on the pages list by looking for page list indicators
    try:
        WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH,
            "//input[contains(@id, 'search') or contains(@placeholder, 'Search')] | //table | //div[contains(@class, 'page-list')]"
        )))
        print("Successfully navigated to Pages Manager")
        return
    except TimeoutException:
        print("Direct URL didn't work, trying panel parameter...")
    
    # Try with panel parameter
    panel_candidates = [
        "pages",
        "left-sidebar-settings--pages",
        "page-manager",
        "pages-manager",
        "website-pages",
        "content-pages",
        "content",
    ]
    for panel in panel_candidates:
        try:
            url = f"https://{sitename}/builder/website/{instance_id}?panel={panel}"
            driver.get(url)
            time.sleep(2)
            # Look for page list indicators
            _ = WebDriverWait(driver, 2).until(EC.presence_of_element_located((By.XPATH,
                "//input[contains(@id, 'search') or contains(@placeholder, 'Search')] | //table"
            )))
            print(f"Successfully navigated using panel={panel}")
            return
        except TimeoutException:
            continue

    # If direct URLs didn't work, try clicking a sidebar item that mentions Pages
    print("Trying to click Pages link in sidebar...")
    try:
        sidebar_candidates = [
            "//nav//a[normalize-space()='Pages']",
            "//aside//a[normalize-space()='Pages']",
            "//a[contains(., 'Pages')]",
            "//button[contains(., 'Pages')]",
            "//*[@id='app']//nav//a[contains(., 'Pages') or contains(., 'Page')]",
        ]
        for xp in sidebar_candidates:
            try:
                el = WebDriverWait(driver, 4).until(EC.element_to_be_clickable((By.XPATH, xp)))
                el.click()
                time.sleep(2)
                print("Successfully clicked Pages link")
                return
            except TimeoutException:
                continue
    except Exception:
        pass
    
    # As a last resort, dump debug
    print("WARNING: Could not navigate to Pages Manager reliably")
    dump_debug(driver, "debug_pages_nav")


def open_page_for_edit(driver: webdriver.Chrome, title_or_slug: str) -> bool:
    """Try to locate a page row by title/slug and open it for editing.
    Returns True if opened, False otherwise.
    """
    # Try multiple search box selectors
    search_xpaths = [
        SELECTORS.get("pages_search_box", "//*[@id='page-search-text-input']"),
        "//*[@id='page-search']",
        "//input[contains(@placeholder, 'Search') or contains(@placeholder, 'Rechercher')]",
        "//input[contains(@id, 'search') and contains(@id, 'page')]",
    ]
    search_found = False
    for sx in search_xpaths:
        try:
            search = WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.XPATH, sx)))
            search.click()
            search.send_keys(MODIFIER_KEY, 'a')
            search.send_keys(title_or_slug)
            search.send_keys(Keys.ENTER)
            time.sleep(2)
            search_found = True
            break
        except TimeoutException:
            continue
        except Exception:
            continue

    # Scan table rows (generic CSS) and anchors/buttons fallback
    try:
        # First try clickable anchors/buttons with matching text
        link_xpaths = [
            f"//a[normalize-space()='{title_or_slug}']",
            f"//a[contains(., '{title_or_slug}')]",
            f"//button[contains(., '{title_or_slug}')]",
            f"//div[contains(@class, 'row') or contains(@class, 'item')]//*[contains(., '{title_or_slug}')]",
        ]
        for xp in link_xpaths:
            try:
                el = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.XPATH, xp)))
                el.click()
                time.sleep(2)
                return True
            except TimeoutException:
                continue

        rows = driver.find_elements(By.CSS_SELECTOR, SELECTORS["pages_table_rows"])  # generic
        for row in rows:
            try:
                cell = row.find_element(By.CSS_SELECTOR, SELECTORS["page_row_title_cell"])  # title cell
                text = cell.text.strip()
                if text and (title_or_slug.lower() in text.lower()):
                    click_cell = row.find_element(By.CSS_SELECTOR, SELECTORS["page_row_click_cell"])  # click to open
                    click_cell.click()
                    time.sleep(2)
                    return True
            except NoSuchElementException:
                continue
    except Exception:
        pass

    # Diagnostics on failure
    dump_debug(driver, "debug_pages")
    return False


def insert_content_and_save(driver: webdriver.Chrome, html_with_css: str) -> bool:
    """Attempt to insert content into page editor. Tries to open a code editor first,
    then tries combined editor, then separate HTML/CSS fields.
    Returns True if saved, False otherwise.
    """
    # Ensure code editor is open (toolbar button with code/pencil icon)
    if not open_code_editor(driver):
        # Not fatal; proceed in case the editor is already visible
        pass
    # Combined editor
    try:
        editor = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, SELECTORS["combined_code_editor"])) )
        editor.click()
        # Select-all then paste
        editor.send_keys(MODIFIER_KEY, 'a')
        editor.send_keys(html_with_css)
        _click_save(driver)
        return True
    except TimeoutException:
        pass

    # Try generic editors in the main document
    if _try_generic_editors(driver, html_with_css):
        _click_save(driver)
        return True

    # Try editors inside iframes
    if _try_iframe_editors(driver, html_with_css):
        _click_save(driver)
        return True

    # Separate HTML/CSS textareas (explicit selectors)
    html_ok = False
    css_ok = False
    try:
        html_area = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, SELECTORS["html_textarea"])) )
        html_area.click(); html_area.send_keys(MODIFIER_KEY, 'a'); html_area.send_keys(Keys.DELETE)
        html_area.send_keys(html_with_css)
        html_ok = True
    except TimeoutException:
        pass

    # If there's a dedicated CSS area that should only receive CSS, you can change the logic here to split.
    # For now, we assume the single combined content is enough, so css_ok can remain False without failing.

    if html_ok or css_ok:
        _click_save(driver)
        return True

    return False


def _click_save(driver: webdriver.Chrome):
    try:
        save_btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, SELECTORS["save_button"])) )
        save_btn.click()
        time.sleep(2)
    except TimeoutException:
        # surface but continue
        print("Warning: Save button not found/clickable; verify selector.")


def open_code_editor(driver: webdriver.Chrome) -> bool:
    """Try to open the page's code editor using common toolbar buttons.
    Looks for icons/buttons with code/pencil/edit semantics.
    """
    candidates = [
        # Code icon/buttons
        "//button[.//i[contains(@class,'fa-code') or contains(@class,'icon-code')]]",
        "//a[.//i[contains(@class,'fa-code') or contains(@class,'icon-code')]]",
        "//button[contains(., 'Code') or contains(@title, 'Code') or contains(@aria-label, 'Code')]",
        "//a[contains(., 'Code') or contains(@title, 'Code') or contains(@aria-label, 'Code')]",
        # Edit/pencil fallback
        "//button[.//i[contains(@class,'fa-pencil') or contains(@class,'fa-edit') or contains(@class,'icon-edit')]]",
        "//a[.//i[contains(@class,'fa-pencil') or contains(@class,'fa-edit') or contains(@class,'icon-edit')]]",
        "//button[contains(., 'Edit') or contains(@title, 'Edit') or contains(@aria-label, 'Edit')]",
    ]
    for xp in candidates:
        try:
            el = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, xp)))
            el.click()
            time.sleep(1)
            if _is_editor_visible(driver):
                return True
        except TimeoutException:
            continue
        except Exception:
            continue
    # Try pressing a common shortcut (Ctrl+Shift+E) if the app supports it (best-effort, may do nothing)
    try:
        ActionChains(driver).key_down(MODIFIER_KEY).key_down(Keys.SHIFT).send_keys('E').key_up(Keys.SHIFT).key_up(MODIFIER_KEY).perform()
        time.sleep(1)
        if _is_editor_visible(driver):
            return True
    except Exception:
        pass
    # Enumerate toolbar buttons/links heuristically and try clicking each until editor appears
    try:
        toolbar_buttons = driver.find_elements(By.XPATH,
            "(//div[contains(@class,'toolbar') or contains(@class,'tools') or contains(@class,'actions') or contains(@class,'editor')])[1]//button | "
            "(//div[contains(@class,'toolbar') or contains(@class,'tools') or contains(@class,'actions') or contains(@class,'editor')])[1]//a | "
            "//div[@id='webbuilder-editor-content-wrapper']//button | //div[@id='webbuilder-editor-content-wrapper']//a"
        )
        for idx, btn in enumerate(toolbar_buttons[:20]):  # limit to avoid clicking too much
            try:
                btn_text = btn.text.strip().lower()
                title = (btn.get_attribute('title') or '').lower()
                aria = (btn.get_attribute('aria-label') or '').lower()
                classes = (btn.get_attribute('class') or '').lower()
                # Prefer likely matches first
                if any(k in (btn_text + title + aria + classes) for k in ['code','html','source','editor','edit','custom']):
                    btn.click()
                    time.sleep(1)
                    if _is_editor_visible(driver):
                        return True
            except Exception:
                continue
        # As a last attempt, click first few buttons blindly
        for btn in toolbar_buttons[:8]:
            try:
                btn.click(); time.sleep(0.7)
                if _is_editor_visible(driver):
                    return True
            except Exception:
                continue
    except Exception:
        pass
    # As last resort, dump debug
    dump_debug(driver, "debug_toolbar")
    return False


def _try_generic_editors(driver: webdriver.Chrome, html_with_css: str) -> bool:
    """Try to find generic code editors in the current document and inject content reliably using JS."""
    # 1) contenteditable regions
    try:
        el = WebDriverWait(driver, 2).until(EC.presence_of_element_located((By.CSS_SELECTOR, "[contenteditable='true']")))
        driver.execute_script("arguments[0].innerHTML = arguments[1];", el, html_with_css)
        return True
    except TimeoutException:
        pass
    # 2) Common editors (Monaco/CodeMirror)
    try:
        # Monaco uses a hidden textarea and a div.monaco-editor; try focusing the editor surface
        monaco = driver.find_elements(By.CSS_SELECTOR, ".monaco-editor")
        if monaco:
            monaco[0].click()
            ActionChains(driver).key_down(MODIFIER_KEY).send_keys('a').key_up(MODIFIER_KEY).perform()
            ActionChains(driver).send_keys(html_with_css).perform()
            return True
    except Exception:
        pass
    try:
        # CodeMirror often has .CodeMirror div; set underlying textarea if present
        cm = driver.find_elements(By.CSS_SELECTOR, ".CodeMirror")
        if cm:
            # Use JS to set the CodeMirror editor value if available
            driver.execute_script(
                "var cmEl=arguments[0]; var cm=cmEl.CodeMirror || cmEl.closest('.CodeMirror')?.CodeMirror; if(cm){ cm.setValue(arguments[1]); }",
                cm[0], html_with_css
            )
            return True
    except Exception:
        pass
    # 3) Plain textarea
    try:
        ta = WebDriverWait(driver, 2).until(EC.presence_of_element_located((By.TAG_NAME, 'textarea')))
        driver.execute_script("arguments[0].value = arguments[1];", ta, html_with_css)
        return True
    except TimeoutException:
        pass
    return False


def _try_iframe_editors(driver: webdriver.Chrome, html_with_css: str) -> bool:
    """Iterate iframes, trying the same generic editor strategies inside them."""
    iframes = driver.find_elements(By.TAG_NAME, 'iframe')
    for idx, frame in enumerate(iframes):
        try:
            driver.switch_to.frame(frame)
            if _try_generic_editors(driver, html_with_css):
                driver.switch_to.default_content()
                return True
        except Exception:
            pass
        finally:
            try:
                driver.switch_to.default_content()
            except Exception:
                pass
    return False


# ------------------------------
# Main
# ------------------------------

def check_if_page_exists(driver: webdriver.Chrome, page_title: str) -> bool:
    """Check if a page with the given title already exists in the pages list.
    Returns True if page exists, False otherwise.
    Flow:
    1. Open hamburger menu (three bars icon)
    2. Click on search toggle icon (fa-search)
    3. Search box opens with id="page--search-field"
    4. Enter page title and check for exact match
    """
    print(f"\nChecking if page '{page_title}' already exists...")
    
    # Wait a bit for the page to fully load
    time.sleep(1)
    
    # Step 1: Open the hamburger menu first
    print("Opening hamburger menu...")
    menu_btn_xpaths = [
        "//button[@aria-label='Menu' or contains(@title,'Menu') or contains(@aria-label,'Menu')]",
        "//button[.//i[contains(@class,'fa-bars') or contains(@class,'fal fa-bars')]]",
        "//div[contains(@class,'tw-cursor-pointer') and .//i[contains(@class,'fa-bars')]]",
        "//i[contains(@class,'fa-bars')]/ancestor::*[self::button or self::div][1]",
    ]
    
    menu_opened = False
    for xp in menu_btn_xpaths:
        try:
            btn = WebDriverWait(driver, 6).until(EC.presence_of_element_located((By.XPATH, xp)))
            scroll_into_view(driver, btn)
            time.sleep(0.1)
            try:
                WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.XPATH, xp)))
                btn.click()
            except Exception:
                driver.execute_script("arguments[0].click();", btn)
            time.sleep(0.5)
            menu_opened = True
            print("Successfully opened hamburger menu")
            break
        except TimeoutException:
            continue
        except Exception:
            continue
    
    if not menu_opened:
        print("WARNING: Could not open hamburger menu")
        # Continue anyway, menu might already be open
    
    # Step 2: Click on the search toggle icon
    search_toggle_found = False
    search_toggle_xpaths = [
        "//*[@id='pages-search-toggle']",
        "//i[contains(@class, 'fa-search') and contains(@id, 'search-toggle')]",
        "//i[contains(@class, 'fa-search')]",
    ]
    
    for toggle_xpath in search_toggle_xpaths:
        try:
            search_toggle = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, toggle_xpath)))
            scroll_into_view(driver, search_toggle)
            search_toggle.click()
            time.sleep(1)
            search_toggle_found = True
            print("Successfully clicked search toggle")
            break
        except TimeoutException:
            continue
        except Exception:
            continue
    
    if not search_toggle_found:
        print("WARNING: Could not find search toggle icon")
        return False
    
    # Step 2: Find and use the search field that opens after clicking toggle
    search_field_xpaths = [
        "//*[@id='page--search-field']",
        "//input[@id='page--search-field']",
        "//input[contains(@placeholder, 'Search by Title and Slug')]",
        "//input[@type='search' and contains(@placeholder, 'Title')]",
    ]
    
    search_found = False
    for search_xpath in search_field_xpaths:
        try:
            search_field = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, search_xpath)))
            scroll_into_view(driver, search_field)
            search_field.click()
            time.sleep(0.5)
            # Clear existing search
            search_field.send_keys(MODIFIER_KEY, 'a')
            search_field.send_keys(Keys.DELETE)
            time.sleep(0.3)
            # Search for the exact page title
            search_field.send_keys(page_title)
            time.sleep(1)  # Wait for search results to filter
            search_found = True
            print(f"Successfully searched for page: '{page_title}'")
            break
        except TimeoutException:
            continue
        except Exception as e:
            print(f"Error with search field: {e}")
            continue
    
    if not search_found:
        print("WARNING: Could not find search field after clicking toggle")
        return False
    
    # Now check if the page exists in the results
    # Try multiple methods to find the page
    page_found = False
    
    # Method 1: Look for exact match in links/buttons
    try:
        exact_match = driver.find_element(By.XPATH, f"//a[normalize-space()='{page_title}'] | //button[normalize-space()='{page_title}'] | //td[normalize-space()='{page_title}'] | //div[contains(@class,'page') and normalize-space()='{page_title}']")
        if exact_match:
            page_found = True
            print(f"[FOUND] Page '{page_title}' already exists (exact match found)")
    except NoSuchElementException:
        pass
    
    # Method 2: Look for partial match - page title might have slug appended like "Page Title (/page-slug)"
    if not page_found:
        try:
            # Try to find elements that start with the page title
            partial_match = driver.find_element(By.XPATH, f"//a[starts-with(normalize-space(), '{page_title}')] | //div[contains(@class,'page') and starts-with(normalize-space(), '{page_title}')]")
            if partial_match:
                text = partial_match.text.strip()
                # Check if it's the same page (title might have slug appended)
                # e.g., "PGR docs links (/pgr-docs-links)"
                if text.startswith(page_title):
                    page_found = True
                    print(f"[FOUND] Page '{page_title}' already exists (found as '{text}')")
        except NoSuchElementException:
            pass
    
    # Method 3: Look in table rows or list items
    if not page_found:
        try:
            partial_match = driver.find_element(By.XPATH, f"//tr[contains(., '{page_title}')] | //li[contains(., '{page_title}')] | //div[contains(@class, 'row') and contains(., '{page_title}')]")
            if partial_match:
                # Verify it's actually the page title and not just containing the text
                text = partial_match.text.strip()
                if page_title.lower() in text.lower():
                    page_found = True
                    print(f"[FOUND] Page '{page_title}' already exists (found in list)")
        except NoSuchElementException:
            pass
    
    # Method 3: Check for "No results" or empty state messages
    if not page_found:
        try:
            no_results = driver.find_element(By.XPATH, "//div[contains(., 'No results') or contains(., 'No pages found') or contains(., 'Aucun résultat')] | //p[contains(., 'No results') or contains(., 'No pages found')]")
            if no_results:
                print(f"[NOT FOUND] Page '{page_title}' does not exist (no results message found)")
                return False
        except NoSuchElementException:
            pass
    
    if not page_found:
        print(f"[NOT FOUND] Page '{page_title}' does not exist")
    
    return page_found


def open_menu_and_click_add_page(driver: webdriver.Chrome) -> bool:
    """Open the hamburger menu and click '+ ADD PAGE'. Stop there. Returns True if the
    Create Page modal is detected after the click.
    """
    # 1) Open the left menu (three parallel lines) if present to reveal '+ ADD PAGE'
    menu_btn_xpaths = [
        "//button[@aria-label='Menu' or contains(@title,'Menu') or contains(@aria-label,'Menu')]",
        "//button[.//i[contains(@class,'fa-bars') or contains(@class,'fal fa-bars')]]",
        "//div[contains(@class,'tw-cursor-pointer') and .//i[contains(@class,'fa-bars')]]",
        "//i[contains(@class,'fa-bars')]/ancestor::*[self::button or self::div][1]",
        "//*[@id='app']//div[contains(@class,'webbuilder-navbar-edit') or contains(@class,'navbar')]/descendant::*[self::button or self::div][.//i[contains(@class,'fa-bars')]]",
        "//*[@id='app']//button[contains(@class,'menu') or contains(@class,'hamburger') or contains(@class,'sidebar') or contains(@class,'tw-cursor-pointer')]",
        "//div[contains(@class,'sidebar') or contains(@class,'navigation')]//button[contains(@class,'toggle') or contains(@class,'menu')]",
    ]
    for xp in menu_btn_xpaths:
        try:
            btn = WebDriverWait(driver, 6).until(EC.presence_of_element_located((By.XPATH, xp)))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
            time.sleep(0.2)
            try:
                WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.XPATH, xp)))
                btn.click()
            except Exception:
                driver.execute_script("arguments[0].click();", btn)
            time.sleep(1)
            break
        except TimeoutException:
            continue
        except Exception:
            continue

    # 2) Click '+ADD PAGE' button (try sidebar and top menus)
    add_btn_xpaths = [
        "//button[normalize-space() = '+ ADD PAGE']",
        "//button[contains(@class,'tw-text-xs') and contains(., 'ADD PAGE')]",
        "//nav//button[contains(., '+') and contains(., 'ADD') and contains(., 'PAGE')]",
        "//nav//button[contains(., 'ADD PAGE')]",
        "//nav//a[contains(., 'ADD PAGE')]",
        "//button[contains(., '+') and contains(., 'ADD') and contains(., 'PAGE')]",
        "//button[contains(., 'ADD PAGE')]",
        "//a[contains(., 'ADD PAGE')]",
        "//button[contains(., 'Add Page') or contains(., 'Add page')]",
        "//a[contains(., 'Add Page') or contains(., 'Add page')]",
        "//button[@aria-label='Add Page' or @title='Add Page']",
        "//a[@aria-label='Add Page' or @title='Add Page']",
        "//button[.//i[contains(@class,'fa-plus')]]",
        "//a[.//i[contains(@class,'fa-plus')]]",
    ]
    clicked = False
    # Wait a bit for the menu to render its items
    WebDriverWait(driver, 6).until(lambda d: True)
    for xp in add_btn_xpaths:
        try:
            el = WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.XPATH, xp)))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
            try:
                WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.XPATH, xp)))
                el.click()
            except Exception:
                driver.execute_script("arguments[0].click();", el)
            time.sleep(1)
            clicked = True
            break
        except TimeoutException:
            continue
        except Exception:
            continue
    if not clicked:
        # Try top-right kebab/dropdown near 'Edit Page' to reveal Add Page
        try:
            kebab_candidates = [
                "//button[.//i[contains(@class,'fa-ellipsis')]]",
                "//button[contains(@class,'dropdown') or contains(@aria-label,'More') or contains(@title,'More')]",
                "//div[contains(@class,'actions') or contains(@class,'toolbar')]//button[.//i[contains(@class,'fa-ellipsis')]]",
            ]
            for kb in kebab_candidates:
                try:
                    b = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, kb)))
                    b.click(); time.sleep(1)
                    # look for add page in the dropdown
                    for mx in [
                        "//a[contains(., 'Add Page')] | //button[contains(., 'Add Page')]",
                        "//a[contains(., '+') and contains(., 'Add') and contains(., 'Page')]",
                        "//a[contains(., 'ADD PAGE')] | //button[contains(., 'ADD PAGE')]",
                    ]:
                        try:
                            m = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, mx)))
                            m.click(); time.sleep(1)
                            clicked = True
                            break
                        except TimeoutException:
                            continue
                    if clicked:
                        break
                except TimeoutException:
                    continue
        except Exception:
            pass
    if not clicked:
        dump_debug(driver, "debug_add_page_btn")
        return False

    # 3) Detect the Create Page modal (best-effort) and stop here
    try:
        title_input = WebDriverWait(driver, 6).until(EC.presence_of_element_located((By.XPATH, "//input[@id='page-title' or @name='page-title'] | //label[contains(., 'Title')]/following::input[1] | //input[@id='title' or @name='title' or contains(@placeholder,'Title')]")))
        # Modal is open; return True to signal success
        return True
    except TimeoutException:
        dump_debug(driver, "debug_add_page_submit")
        return False


def fill_create_page_modal(driver: webdriver.Chrome, parsed: Dict[str, Any]) -> bool:
    """Fill the Create Page modal with Title and Language from parsed JSON. Do not submit yet."""
    title = parsed.get("title")
    slug = (parsed.get("slug") or "").strip()
    language = parsed.get("language")

    if not title:
        print("Warning: No title found in JSON; skipping modal fill.")
        return False

    # 1) Fill Title input
    try:
        title_input = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, "//input[@id='page-title' or @name='page-title'] | //input[@id='title' or @name='title'] | //label[contains(., 'Title')]/following::input[1]")))
        scroll_into_view(driver, title_input)
        try:
            title_input.clear()
        except Exception:
            pass
        title_input.send_keys(title)
        print(f"Filled Title: {title}")
    except TimeoutException:
        print("Warning: Could not find Title input in modal.")
        dump_debug(driver, "debug_modal_title")
        return False

    # 2) If slug is available, enable custom slug and set page slug
    if slug:
        try:
            custom_slug_checkbox = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located(
                    (
                        By.XPATH,
                        "//input[@id='customize-slug' or @name='customize-slug' or @id='customise-slug']"
                    )
                )
            )
            scroll_into_view(driver, custom_slug_checkbox)

            if not custom_slug_checkbox.is_selected():
                try:
                    custom_slug_checkbox.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", custom_slug_checkbox)
                time.sleep(0.4)

            slug_input = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located(
                    (
                        By.XPATH,
                        "//input[@id='page-slug' or @name='page-slug']"
                    )
                )
            )
            scroll_into_view(driver, slug_input)

            # Ensure readonly is removed if UI has not toggled yet, then set value.
            driver.execute_script("arguments[0].removeAttribute('readonly');", slug_input)
            driver.execute_script(
                "arguments[0].value = arguments[1];"
                "arguments[0].dispatchEvent(new Event('input', {bubbles:true}));"
                "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
                slug_input,
                slug,
            )

            # Extra fallback in case framework ignores JS event updates.
            try:
                slug_input.click()
                slug_input.send_keys(MODIFIER_KEY, 'a')
                slug_input.send_keys(Keys.DELETE)
                slug_input.send_keys(slug)
            except Exception:
                pass

            print(f"Filled Slug: {slug}")
        except TimeoutException:
            print("WARNING: Slug provided but customize/page-slug fields were not found.")
        except Exception as e:
            print(f"WARNING: Could not set slug '{slug}': {e}")

    # 3) Select Brand from multiselect (find by label "Brand")
    # brand = parsed.get("brand")
    # if brand:
    #     print(f"DEBUG: Attempting to select brand: '{brand}'")
    #     try:
    #         # Find Brand multiselect by its label
    #         brand_container = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, "//label[contains(text(),'Brand')]/following-sibling::section//div[contains(@class,'multiselect__tags')] | //label[@for='brands']/following-sibling::section//div[contains(@class,'multiselect__tags')]")))
    #         print(f"DEBUG: Found Brand multiselect by label")
    #         if brand_container:
    #             scroll_into_view(driver, brand_container)
                
    #             # FIRST: Clear any existing selections (like default "UNBRANDED")
    #             print("DEBUG: Clearing existing Brand selections in Create Page Modal...")
    #             time.sleep(1.0)  # Wait longer for multiselect to be ready
                
    #             # Try multiple strategies to clear existing selections
    #             cleared = False
                
    #             # Strategy 1: Find and click remove icons
    #             try:
    #                 remove_buttons = brand_container.find_elements(By.XPATH, ".//i[contains(@class,'multiselect__tag-icon')]")
    #                 print(f"DEBUG: Strategy 1 - Found {len(remove_buttons)} remove icon buttons")
    #                 if len(remove_buttons) > 0:
    #                     for idx, btn in enumerate(remove_buttons):
    #                         try:
    #                             driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
    #                             time.sleep(0.2)
    #                             # Try both click methods
    #                             try:
    #                                 btn.click()
    #                             except:
    #                                 driver.execute_script("arguments[0].click();", btn)
    #                             time.sleep(0.3)
    #                             print(f"DEBUG: Removed Brand selection {idx+1}/{len(remove_buttons)}")
    #                             cleared = True
    #                         except Exception as e:
    #                             print(f"DEBUG: Could not click remove button {idx+1}: {str(e)[:50]}")
    #             except Exception as e:
    #                 print(f"DEBUG: Strategy 1 failed: {str(e)[:50]}")
                
    #             # Strategy 2: Find tags and click their close icons
    #             if not cleared:
    #                 try:
    #                     tags = brand_container.find_elements(By.XPATH, ".//span[contains(@class,'multiselect__tag')]")
    #                     print(f"DEBUG: Strategy 2 - Found {len(tags)} tag elements")
    #                     for idx, tag in enumerate(tags):
    #                         try:
    #                             # Find the close icon within the tag
    #                             close_icon = tag.find_element(By.XPATH, ".//i")
    #                             driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", close_icon)
    #                             time.sleep(0.2)
    #                             driver.execute_script("arguments[0].click();", close_icon)
    #                             time.sleep(0.3)
    #                             print(f"DEBUG: Removed tag {idx+1}/{len(tags)}")
    #                             cleared = True
    #                         except Exception as e:
    #                             print(f"DEBUG: Could not remove tag {idx+1}: {str(e)[:50]}")
    #                 except Exception as e:
    #                     print(f"DEBUG: Strategy 2 failed: {str(e)[:50]}")
                
    #             if cleared:
    #                 time.sleep(0.5)
    #                 print("SUCCESS: Cleared existing Brand selections")
    #             else:
    #                 print("WARNING: Could not find any existing Brand selections to clear")
                
    #             # NOW: Add the new brand value
    #             # Use JavaScript to click and activate the multiselect
    #             driver.execute_script("arguments[0].scrollIntoView(true);", brand_container)
    #             time.sleep(0.3)
    #             driver.execute_script("arguments[0].click();", brand_container)
    #             time.sleep(0.8)
    #             # Now find the input inside and send keys using JavaScript
    #             brand_input = brand_container.find_element(By.XPATH, ".//input[contains(@class,'multiselect__input')]")
    #             # Use JavaScript to focus and set value
    #             driver.execute_script("arguments[0].focus();", brand_input)
    #             driver.execute_script("arguments[0].value = '';", brand_input)  # Clear input field
    #             time.sleep(0.2)
    #             # For Brand: Always use first word in UPPERCASE (e.g., "UNBRANDED")
    #             brand_search = brand.split('/')[0].split()[0].strip().upper()  # "UNBRANDED"
                
    #             # Clear and type the search term
    #             driver.execute_script("arguments[0].value = '';", brand_input)
    #             time.sleep(0.2)
    #             for char in brand_search:
    #                 brand_input.send_keys(char)
    #                 time.sleep(0.05)
    #             time.sleep(1)  # Wait for dropdown to populate
                
    #             # Try to find matching option
    #             try:
    #                 option = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, f"//span[contains(@class,'multiselect__option')]//span[text()='{brand_search}']")))
    #                 driver.execute_script("arguments[0].click();", option)
    #                 print(f"SUCCESS: Selected Brand: {brand_search}")
    #                 time.sleep(0.5)
    #             except TimeoutException:
    #                 # Try contains instead of exact match
    #                 try:
    #                     option = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.XPATH, f"//span[contains(@class,'multiselect__option')]//span[contains(text(),'{brand_search}')]")))
    #                     driver.execute_script("arguments[0].click();", option)
    #                     print(f"SUCCESS: Selected Brand: {brand_search} (partial match)")
    #                     time.sleep(0.5)
    #                 except TimeoutException:
    #                     # Last resort: press Enter
    #                     from selenium.webdriver.common.keys import Keys
    #                     brand_input.send_keys(Keys.ENTER)
    #                     time.sleep(0.5)
    #                     print(f"INFO: Pressed Enter for Brand: {brand_search}")
    #         else:
    #             print("WARNING: No multiselect containers found for Brand")
    #     except Exception as e:
    #         print(f"WARNING: Could not select Brand: {e}")
    # else:
    #     print("DEBUG: No brand value found in JSON")

    # 4) Set Hidden toggle (NOTE: Hidden is often disabled in Create Page modal, will be set in Page Settings)
    hidden = parsed.get("hidden")
    print(f"DEBUG: Hidden value from JSON: {hidden}")
    print(f"INFO: Hidden toggle is typically disabled in Create Page modal. Will be set in Page Settings after creation.")
    # Skip Hidden toggle in Create Page modal as it's usually disabled
    # We'll set it later in Page Settings
    if False and hidden is not None:  # Disabled for now
        try:
            # Find the Hidden toggle - try the visual slider first, then checkbox
            # Look for the slider span or the parent label/switch container
            try:
                # Try clicking the visual slider/switch container
                toggle_container = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, "//label[@for='hidden' or contains(text(),'Hidden')]//following::span[contains(@class,'slider')][1] | //label[@for='hidden']//span[contains(@class,'slider')] | //label[contains(text(),'Hidden')]//following::label[contains(@class,'switch')][1]")))
                scroll_into_view(driver, toggle_container)
                # Check the checkbox state to determine current value
                hidden_checkbox = driver.find_element(By.XPATH, "//label[@for='hidden' or contains(text(),'Hidden')]//following::input[@type='checkbox'][1] | //label[@for='hidden' or contains(text(),'Hidden')]//preceding::input[@type='checkbox'][1]")
                is_checked = hidden_checkbox.is_selected()
            except:
                # Fallback to checkbox
                hidden_toggle = WebDriverWait(driver, 2).until(EC.presence_of_element_located((By.XPATH, "//label[@for='hidden' or contains(text(),'Hidden')]//following::input[@type='checkbox'][1] | //label[@for='hidden' or contains(text(),'Hidden')]//preceding::input[@type='checkbox'][1]")))
                scroll_into_view(driver, hidden_toggle)
                toggle_container = hidden_toggle
                hidden_checkbox = hidden_toggle
                is_checked = hidden_toggle.is_selected()
            # hidden=True means toggle should be ON (checked)
            # hidden=False or None means toggle should be OFF (unchecked)
            should_be_checked = bool(hidden)
            print(f"DEBUG: Hidden toggle currently: {is_checked}, should be: {should_be_checked}")
            if is_checked != should_be_checked:
                try:
                    # Click the visual toggle container
                    driver.execute_script("arguments[0].click();", toggle_container)
                except Exception:
                    toggle_container.click()
                time.sleep(0.5)  # Wait for toggle animation
                print(f"SUCCESS: Set Hidden toggle to: {should_be_checked}")
            else:
                print(f"SUCCESS: Hidden toggle already correct: {should_be_checked}")
            # Verify the toggle state after clicking
            time.sleep(0.3)
            final_state = hidden_checkbox.is_selected()
            print(f"DEBUG: Hidden toggle final state after click: {final_state}")
        except TimeoutException:
            print("WARNING: Could not find Hidden toggle.")
    else:
        # If hidden is None, set toggle to OFF (unchecked/visible)
        print("DEBUG: Hidden is None, setting toggle to OFF")
        try:
            # Try visual slider first
            try:
                toggle_container = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, "//label[@for='hidden' or contains(text(),'Hidden')]//following::span[contains(@class,'slider')][1] | //label[@for='hidden']//span[contains(@class,'slider')]")))
                hidden_checkbox = driver.find_element(By.XPATH, "//label[@for='hidden' or contains(text(),'Hidden')]//following::input[@type='checkbox'][1] | //label[@for='hidden' or contains(text(),'Hidden')]//preceding::input[@type='checkbox'][1]")
            except:
                hidden_toggle = WebDriverWait(driver, 2).until(EC.presence_of_element_located((By.XPATH, "//label[@for='hidden' or contains(text(),'Hidden')]//following::input[@type='checkbox'][1] | //label[@for='hidden' or contains(text(),'Hidden')]//preceding::input[@type='checkbox'][1]")))
                toggle_container = hidden_toggle
                hidden_checkbox = hidden_toggle
            scroll_into_view(driver, toggle_container)
            if hidden_checkbox.is_selected():
                try:
                    driver.execute_script("arguments[0].click();", toggle_container)
                except Exception:
                    toggle_container.click()
                time.sleep(0.5)  # Wait for toggle animation
                print("SUCCESS: Set Hidden toggle to OFF (null value)")
            else:
                print("SUCCESS: Hidden toggle already OFF (null value)")
            # Verify the toggle state
            time.sleep(0.3)
            final_state = hidden_checkbox.is_selected()
            print(f"DEBUG: Hidden toggle final state: {final_state}")
        except TimeoutException:
            print("WARNING: Could not find Hidden toggle.")

    # 5) Select Indication from multiselect (find by label "Indication")
    indication = parsed.get("indication")
    if indication:
        print(f"DEBUG: Attempting to select indication: '{indication}'")
        try:
            # Find Indication multiselect by its label
            indication_container = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, "//label[contains(text(),'Indication')]/following-sibling::section//div[contains(@class,'multiselect__tags')] | //label[@for='indication']/following-sibling::section//div[contains(@class,'multiselect__tags')]")))
            print(f"DEBUG: Found Indication multiselect by label")
            if indication_container:
                scroll_into_view(driver, indication_container)
                # Use JavaScript to click and activate
                driver.execute_script("arguments[0].scrollIntoView(true);", indication_container)
                time.sleep(0.3)
                driver.execute_script("arguments[0].click();", indication_container)
                time.sleep(0.8)
                # Now find the input and type
                indication_input = indication_container.find_element(By.XPATH, ".//input[contains(@class,'multiselect__input')]")
                driver.execute_script("arguments[0].focus();", indication_input)
                driver.execute_script("arguments[0].value = '';", indication_input)
                time.sleep(0.2)
                # For Indication: Try exact match, then uppercase, then capitalize
                indication_variations = [indication, indication.upper(), indication.capitalize()]
                
                driver.execute_script("arguments[0].value = '';", indication_input)
                time.sleep(0.2)
                for char in indication:
                    indication_input.send_keys(char)
                    time.sleep(0.05)
                time.sleep(1)  # Wait for dropdown
                
                option_found = False
                for variant in indication_variations:
                    if option_found:
                        break
                    try:
                        option = WebDriverWait(driver, 1).until(EC.element_to_be_clickable((By.XPATH, f"//span[contains(@class,'multiselect__option')]//span[text()='{variant}']")))
                        driver.execute_script("arguments[0].click();", option)
                        print(f"SUCCESS: Selected Indication: {variant}")
                        option_found = True
                        time.sleep(0.5)
                        break
                    except TimeoutException:
                        continue
                
                if not option_found:
                    # Try partial match
                    try:
                        option = WebDriverWait(driver, 1).until(EC.element_to_be_clickable((By.XPATH, f"//span[contains(@class,'multiselect__option')]//span[contains(text(),'{indication}')]")))
                        driver.execute_script("arguments[0].click();", option)
                        print(f"SUCCESS: Selected Indication: {indication} (partial)")
                        time.sleep(0.5)
                    except TimeoutException:
                        from selenium.webdriver.common.keys import Keys
                        indication_input.send_keys(Keys.ENTER)
                        time.sleep(0.5)
                        print(f"INFO: Pressed Enter for Indication: {indication}")
            else:
                print(f"WARNING: Not enough multiselect containers found (need at least 2, found {len(all_multiselect_containers)})")
        except Exception as e:
            print(f"WARNING: Could not select Indication: {e}")
    else:
        print("DEBUG: No indication value found in JSON")

    # 6) Select Therapeutic Area from multiselect (find by label "Therapeutic")
    therapeutic_area = parsed.get("therapeutic_area")
    if therapeutic_area:
        print(f"DEBUG: Attempting to select therapeutic area: '{therapeutic_area}'")
        try:
            # Find Therapeutic Area multiselect by its label
            ta_container = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, "//label[contains(text(),'Therapeutic')]/following-sibling::section//div[contains(@class,'multiselect__tags')] | //label[@for='therapeutic']/following-sibling::section//div[contains(@class,'multiselect__tags')]")))
            print(f"DEBUG: Found Therapeutic Area multiselect by label")
            if ta_container:
                scroll_into_view(driver, ta_container)
                # Use JavaScript to click and activate
                driver.execute_script("arguments[0].scrollIntoView(true);", ta_container)
                time.sleep(0.3)
                driver.execute_script("arguments[0].click();", ta_container)
                time.sleep(0.8)
                # Now find the input and type
                ta_input = ta_container.find_element(By.XPATH, ".//input[contains(@class,'multiselect__input')]")
                driver.execute_script("arguments[0].focus();", ta_input)
                driver.execute_script("arguments[0].value = '';", ta_input)
                time.sleep(0.2)
                # For Therapeutic Area: Try exact match, then uppercase, then capitalize
                ta_variations = [therapeutic_area, therapeutic_area.upper(), therapeutic_area.capitalize()]
                
                driver.execute_script("arguments[0].value = '';", ta_input)
                time.sleep(0.2)
                for char in therapeutic_area:
                    ta_input.send_keys(char)
                    time.sleep(0.05)
                time.sleep(1)  # Wait for dropdown
                
                option_found = False
                for variant in ta_variations:
                    if option_found:
                        break
                    try:
                        option = WebDriverWait(driver, 1).until(EC.element_to_be_clickable((By.XPATH, f"//span[contains(@class,'multiselect__option')]//span[text()='{variant}']")))
                        driver.execute_script("arguments[0].click();", option)
                        print(f"SUCCESS: Selected Therapeutic Area: {variant}")
                        option_found = True
                        time.sleep(0.5)
                        break
                    except TimeoutException:
                        continue
                
                if not option_found:
                    # Try partial match
                    try:
                        option = WebDriverWait(driver, 1).until(EC.element_to_be_clickable((By.XPATH, f"//span[contains(@class,'multiselect__option')]//span[contains(text(),'{therapeutic_area}')]")))
                        driver.execute_script("arguments[0].click();", option)
                        print(f"SUCCESS: Selected Therapeutic Area: {therapeutic_area} (partial)")
                        time.sleep(0.5)
                    except TimeoutException:
                        from selenium.webdriver.common.keys import Keys
                        ta_input.send_keys(Keys.ENTER)
                        time.sleep(0.5)
                        print(f"INFO: Pressed Enter for Therapeutic Area: {therapeutic_area}")
            else:
                print(f"WARNING: Not enough multiselect containers found (need at least 3, found {len(all_multiselect_containers)})")
        except Exception as e:
            print(f"WARNING: Could not select Therapeutic Area: {e}")
    else:
        print("DEBUG: No therapeutic area value found in JSON")

    # 7) Select Primary Message Category dropdown
    primary_msg = parsed.get("primary_message_category")
    if primary_msg:
        print(f"DEBUG: Attempting to select Primary Message Category: '{primary_msg}'")
        try:
            # Find the Primary Message Category select dropdown
            pmc_select = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, "//select[contains(@class,'form-control')]//option[@value='' and contains(text(),'Select')]/parent::select | //select[.//option[contains(text(),'Resources HCP')]]")))
            scroll_into_view(driver, pmc_select)
            from selenium.webdriver.support.ui import Select
            sel = Select(pmc_select)
            try:
                sel.select_by_value(str(primary_msg))
                # Get the selected option text for confirmation
                selected_text = sel.first_selected_option.text
                print(f"SUCCESS: Selected Primary Message Category: {selected_text} (value={primary_msg})")
            except Exception as e:
                print(f"WARNING: Could not select Primary Message Category value '{primary_msg}': {e}")
        except TimeoutException:
            print("WARNING: Could not find Primary Message Category dropdown.")
    else:
        print("DEBUG: No Primary Message Category value found in JSON, keeping default")

    # 8) Select Language dropdown by value attribute
    print(f"DEBUG fill_create_page_modal: received language = '{language}'")
    if language:
        print(f"DEBUG: Attempting to select language: '{language}'")
        import time as time_module
        lang_start_time = time_module.time()
        try:
            # Try multiple XPath strategies to find Language dropdown
            lang_select = None
            lang_xpaths = [
                "//label[contains(text(),'Language')]/following::select[1]",
                "//label[@for='language']/following::select[1]",
                "//select[@id='language' or @name='language']",
                "//select[contains(@class,'form-control')]",
                "//select"
            ]
            
            for xpath in lang_xpaths:
                try:
                    lang_select = WebDriverWait(driver, 2).until(EC.presence_of_element_located((By.XPATH, xpath)))
                    if lang_select:
                        print(f"Found Language dropdown using: {xpath}")
                        break
                except TimeoutException:
                    continue
            
            if lang_select:
                scroll_into_view(driver, lang_select)
                from selenium.webdriver.support.ui import Select
                sel = Select(lang_select)
                
                # Try to select by value (e.g., "fr", "en", "FR", "EN")
                try:
                    lang_lower = str(language).lower().strip()
                    print(f"DEBUG: Trying to select by value: '{lang_lower}'")
                    sel.select_by_value(lang_lower)
                    print(f"SUCCESS: Selected Language by value: {lang_lower}")
                except Exception as e:
                    print(f"DEBUG: select_by_value (lowercase) failed: {e}")
                    # Try uppercase
                    try:
                        lang_upper = str(language).upper().strip()
                        print(f"DEBUG: Trying to select by value: '{lang_upper}'")
                        sel.select_by_value(lang_upper)
                        print(f"SUCCESS: Selected Language by value: {lang_upper}")
                    except Exception as e2:
                        print(f"DEBUG: select_by_value (uppercase) failed: {e2}")
                        # If exact value fails, try visible text match
                        try:
                            # Find option whose text contains the language code
                            print(f"DEBUG: Trying to match by text containing: '{lang_upper}'")
                            matched = False
                            option_count = 0
                            for opt in sel.options:
                                option_count += 1
                                # Timeout check
                                if time_module.time() - lang_start_time > 15:
                                    print(f"DEBUG: Language selection timeout (15s), stopping search")
                                    break
                                if option_count > 20:  # Limit to prevent hanging
                                    print(f"DEBUG: Checked 20 options, stopping search")
                                    break
                                try:
                                    opt_value = opt.get_attribute('value') or ''
                                    opt_text = opt.text or ''
                                    # Only print first 5 options to avoid console spam
                                    if option_count <= 5:
                                        print(f"  Option {option_count}: value='{opt_value}', text='{opt_text[:50]}'")
                                    if lang_upper in opt_text.upper() or lang_lower == opt_value.lower() or lang_lower in opt_value.lower():
                                        sel.select_by_visible_text(opt_text)
                                        print(f"SUCCESS: Selected Language by text match: {opt_text}")
                                        matched = True
                                        break
                                except Exception as opt_err:
                                    print(f"DEBUG: Error checking option {option_count}: {str(opt_err)[:50]}")
                                    continue
                            if not matched:
                                print(f"WARNING: No option matched language '{language}' - using default")
                        except Exception as e3:
                            print(f"WARNING: Could not select language '{language}': {e3}")
            else:
                print("WARNING: Could not find Language dropdown in modal.")
        except Exception as e:
            print(f"ERROR: Exception while selecting language: {e}")
    else:
        print(f"DEBUG: No language value found in JSON (language={language})")

    # 9) Wait for SAVE button to become enabled, then click it
    print("\nWaiting for SAVE button to become enabled...")
    
    # First, close any drawer that might have opened
    try:
        # Try to close drawer by pressing Escape or clicking close button
        from selenium.webdriver.common.keys import Keys
        driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.5)
        print("DEBUG: Pressed ESC to close any open drawer")
    except Exception:
        pass
    
    # Wait up to 10 seconds for SAVE button to be enabled
    max_wait_seconds = 10
    save_button = None
    
    for attempt in range(max_wait_seconds):
        try:
            # Find SAVE button in modal (look for button with "Save" text)
            buttons = driver.find_elements(By.XPATH, "//div[contains(@class,'modal')]//button[contains(., 'Save')] | //button[contains(., 'Save')]")
            
            for btn in buttons:
                button_text = btn.text.strip()
                is_disabled = btn.get_attribute("disabled")
                
                # Check if this is the SAVE button and if it's enabled
                if "save" in button_text.lower() and not is_disabled:
                    save_button = btn
                    print(f"SUCCESS: SAVE button is now enabled after {attempt + 1} seconds")
                    break
            
            if save_button:
                break
            
            # Button still disabled, wait and try again
            if attempt == 0:
                print(f"DEBUG: SAVE button is disabled, waiting for it to be enabled...")
            time.sleep(1)
            
        except Exception as e:
            time.sleep(1)
            continue
    
    if save_button:
        # Click the enabled SAVE button
        try:
            scroll_into_view(driver, save_button)
            time.sleep(0.3)
            driver.execute_script("arguments[0].click();", save_button)
            print(f"SUCCESS: Clicked SAVE button")
            time.sleep(3)  # Wait for page creation
            return True
        except Exception as e:
            print(f"ERROR: Failed to click SAVE button: {e}")
            dump_debug(driver, "debug_save_button_click_failed")
            return False
    else:
        print(f"WARNING: SAVE button remained disabled after {max_wait_seconds} seconds")
        print("This usually means required fields are not properly filled or validated.")
        dump_debug(driver, "debug_save_button_still_disabled")
        return False


def open_page_menu_and_update_settings(driver: webdriver.Chrome, page_title: str, parsed: Dict[str, Any]) -> bool:
    """Open the page's context menu and update basic settings (title/slug/path), and SEO if present.
    Returns True on success; saves debug dump on failure.
    """
    # 1) Select the page in the left list
    try:
        page_item = WebDriverWait(driver, 6).until(EC.element_to_be_clickable((By.XPATH, f"//nav//*[contains(@class,'page') or contains(@class,'item') or self::a or self::div][normalize-space()='{page_title}']")))
        page_item.click(); time.sleep(1)
    except TimeoutException:
        # try generic
        try:
            page_item = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, f"//*[normalize-space()='{page_title}']")))
            page_item.click(); time.sleep(1)
        except TimeoutException:
            dump_debug(driver, "debug_page_select")
            return False

    # 2) Open context menu (gear/kebab) near the selected page
    menu_opened = False
    menu_xpaths = [
        "//div[contains(@class,'context') or contains(@class,'menu') or contains(@class,'actions')]//button",
        "//button[.//i[contains(@class,'fa-ellipsis') or contains(@class,'fa-cog')]]",
        f"(//*[normalize-space()='{page_title}']/following::*[self::button or self::a][1])",
    ]
    for xp in menu_xpaths:
        try:
            btn = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, xp)))
            btn.click(); time.sleep(1)
            menu_opened = True
            break
        except TimeoutException:
            continue
        except Exception:
            continue
    if not menu_opened:
        # Menu might already be open
        pass

    # 3) Click 'Page settings'
    try:
        settings_item = WebDriverWait(driver, 4).until(EC.element_to_be_clickable((By.XPATH, "//a[contains(., 'Page settings')] | //button[contains(., 'Page settings')]")))
        settings_item.click(); time.sleep(1)
    except TimeoutException:
        # Try Edit Page then a settings tab
        try:
            edit_item = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.XPATH, "//a[contains(., 'Edit Page')] | //button[contains(., 'Edit Page')]")))
            edit_item.click(); time.sleep(1)
        except TimeoutException:
            dump_debug(driver, "debug_page_menu")
            return False

    # 4) Update fields: title, slug/path
    updated_any = False
    title = parsed.get("title")
    slug = parsed.get("slug") or parsed.get("path")
    if title and set_input_by_label(driver, ["Title", "Page title"], title):
        updated_any = True
    if slug and (set_input_by_label(driver, ["Slug", "URL", "Path"], slug)):
        updated_any = True

    # 5) SEO settings (navigate to SEO tab if present)
    try:
        seo_tab = driver.find_elements(By.XPATH, "//a[contains(., 'SEO') or contains(., 'Seo')] | //button[contains(., 'SEO') or contains(., 'Seo')]")
        if seo_tab:
            try:
                scroll_into_view(driver, seo_tab[0]); seo_tab[0].click(); time.sleep(0.5)
            except Exception:
                pass
    except Exception:
        pass

    seo_title = parsed.get("seo_title") or title
    meta_desc = parsed.get("meta_description")
    meta_keys = parsed.get("meta_keywords")
    if seo_title and set_input_by_label(driver, ["Meta title", "SEO title", "Title"], seo_title):
        updated_any = True
    if meta_desc and set_textarea_by_label(driver, ["Meta description", "SEO description", "Description"], meta_desc):
        updated_any = True
    if meta_keys and set_input_by_label(driver, ["Meta keywords", "SEO keywords", "Keywords"], meta_keys):
        updated_any = True

    # 6) Optional: Visibility, Parent, Template/Layout
    visibility = parsed.get("visibility")
    parent = parsed.get("parent")
    template = parsed.get("template")
    if visibility and set_select_by_label(driver, ["Visibility", "Status"], visibility):
        updated_any = True
    if parent and set_select_by_label(driver, ["Parent", "Parent page"], parent):
        updated_any = True
    if template and set_select_by_label(driver, ["Template", "Layout"], template):
        updated_any = True

    # 6b) New: Brand, Indication, Therapeutic Area (multiselects), Hidden (toggle), Language (dropdown)
    brand = parsed.get("brand")
    language = parsed.get("language")
    indication = parsed.get("indication")
    t_area = parsed.get("therapeutic_area")
    hidden_flag = parsed.get("hidden")
    remove_slug = parsed.get("remove_special_slug")

    # Brand multiselect
    if brand:
        print(f"Setting Brand in Page Settings: {brand}")
        try:
            # First, clear any existing selections (like default "UNBRANDED")
            print("Clearing existing Brand selections in Page Settings...")
            time.sleep(1.0)  # Wait longer for page to be ready
            
            # Try multiple strategies to clear existing selections
            cleared = False
            
            # Strategy 1: Find remove icon buttons
            try:
                remove_buttons = driver.find_elements(By.XPATH, "//label[contains(text(),'Brand')]/following::div[contains(@class,'multiselect')][1]//i[contains(@class,'multiselect__tag-icon')]")
                print(f"Strategy 1 - Found {len(remove_buttons)} remove icon buttons")
                if len(remove_buttons) > 0:
                    for idx, btn in enumerate(remove_buttons):
                        try:
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                            time.sleep(0.2)
                            # Try both click methods
                            try:
                                btn.click()
                            except:
                                driver.execute_script("arguments[0].click();", btn)
                            time.sleep(0.3)
                            print(f"Removed Brand selection {idx+1}/{len(remove_buttons)}")
                            cleared = True
                        except Exception as e:
                            print(f"Could not click remove button {idx+1}: {str(e)[:50]}")
            except Exception as e:
                print(f"Strategy 1 failed: {str(e)[:50]}")
            
            # Strategy 2: Find tags and click their close icons
            if not cleared:
                try:
                    tags = driver.find_elements(By.XPATH, "//label[contains(text(),'Brand')]/following::div[contains(@class,'multiselect')][1]//span[contains(@class,'multiselect__tag')]")
                    print(f"Strategy 2 - Found {len(tags)} tag elements")
                    for idx, tag in enumerate(tags):
                        try:
                            close_icon = tag.find_element(By.XPATH, ".//i")
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", close_icon)
                            time.sleep(0.2)
                            driver.execute_script("arguments[0].click();", close_icon)
                            time.sleep(0.3)
                            print(f"Removed tag {idx+1}/{len(tags)}")
                            cleared = True
                        except Exception as e:
                            print(f"Could not remove tag {idx+1}: {str(e)[:50]}")
                except Exception as e:
                    print(f"Strategy 2 failed: {str(e)[:50]}")
            
            if cleared:
                time.sleep(0.5)
                print("SUCCESS: Cleared all existing Brand selections in Page Settings")
            else:
                print("WARNING: Could not find any existing Brand selections to clear")
            
            # Now add the new brand value
            brand_input = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, "//label[contains(text(),'Brand')]/following::div[contains(@class,'multiselect')]//input | //div[contains(@class,'multiselect')]//input[@placeholder='Select or add'][1]")))
            scroll_into_view(driver, brand_input)
            brand_input.click()
            time.sleep(0.5)
            brand_input.send_keys(brand)
            time.sleep(0.5)
            try:
                option = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, f"//span[contains(@class,'multiselect__option')]//span[contains(text(),'{brand}')]")))
                option.click()
                print(f"SUCCESS: Set Brand to {brand}")
                updated_any = True
            except TimeoutException:
                brand_input.send_keys(Keys.ENTER)
                print(f"SUCCESS: Set Brand to {brand} (Enter)")
                updated_any = True
        except TimeoutException:
            print("WARNING: Could not find Brand multiselect in Page Settings")
    
    # Indication multiselect
    if indication:
        print(f"Setting Indication in Page Settings: {indication}")
        try:
            indication_input = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, "//label[contains(text(),'Indication')]/following::div[contains(@class,'multiselect')]//input | //div[contains(@class,'multiselect')]//input[@placeholder='Select or add'][2]")))
            scroll_into_view(driver, indication_input)
            indication_input.click()
            time.sleep(0.5)
            indication_input.send_keys(indication)
            time.sleep(0.5)
            try:
                option = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, f"//span[contains(@class,'multiselect__option')]//span[contains(text(),'{indication}')]")))
                option.click()
                print(f"SUCCESS: Set Indication to {indication}")
                updated_any = True
            except TimeoutException:
                indication_input.send_keys(Keys.ENTER)
                print(f"SUCCESS: Set Indication to {indication} (Enter)")
                updated_any = True
        except TimeoutException:
            print("WARNING: Could not find Indication multiselect in Page Settings")
    
    # Therapeutic Area multiselect
    if t_area:
        print(f"Setting Therapeutic Area in Page Settings: {t_area}")
        try:
            ta_input = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, "//label[contains(text(),'Therapeutic')]/following::div[contains(@class,'multiselect')]//input | //div[contains(@class,'multiselect')]//input[@placeholder='Select or add'][3]")))
            scroll_into_view(driver, ta_input)
            ta_input.click()
            time.sleep(0.5)
            ta_input.send_keys(t_area)
            time.sleep(0.5)
            try:
                option = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, f"//span[contains(@class,'multiselect__option')]//span[contains(text(),'{t_area}')]")))
                option.click()
                print(f"SUCCESS: Set Therapeutic Area to {t_area}")
                updated_any = True
            except TimeoutException:
                ta_input.send_keys(Keys.ENTER)
                print(f"SUCCESS: Set Therapeutic Area to {t_area} (Enter)")
                updated_any = True
        except TimeoutException:
            print("WARNING: Could not find Therapeutic Area multiselect in Page Settings")
    
    # Hidden toggle (should be enabled in Page Settings)
    if hidden_flag is not None:
        print(f"Setting Hidden toggle in Page Settings: {hidden_flag}")
        try:
            hidden_toggle = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, "//label[@for='hidden' or contains(text(),'Hidden')]//following::input[@type='checkbox'][1] | //label[@for='hidden']//preceding::input[@type='checkbox'][1]")))
            scroll_into_view(driver, hidden_toggle)
            is_checked = hidden_toggle.is_selected()
            should_be_checked = bool(hidden_flag)
            if is_checked != should_be_checked:
                try:
                    driver.execute_script("arguments[0].click();", hidden_toggle)
                except Exception:
                    hidden_toggle.click()
                print(f"SUCCESS: Set Hidden to {should_be_checked}")
                updated_any = True
            else:
                print(f"Hidden already set to {should_be_checked}")
        except TimeoutException:
            print("WARNING: Could not find Hidden toggle in Page Settings")
    
    # Language dropdown (if not set in Create modal)
    if language:
        print(f"Setting Language in Page Settings: {language}")
        lang_value = language
        if isinstance(language, str) and len(language.strip()) == 2:
            lang_value = language.strip().upper()
        
        # Try to set language using multiple strategies
        try:
            # Strategy 1: Use set_select_by_label helper
            if set_select_by_label(driver, ["Language"], lang_value):
                updated_any = True
                print(f"SUCCESS: Set Language to {lang_value}")
            else:
                # Strategy 2: Try lowercase value
                if set_select_by_label(driver, ["Language"], lang_value.lower()):
                    updated_any = True
                    print(f"SUCCESS: Set Language to {lang_value.lower()}")
                else:
                    print(f"WARNING: Could not set Language to {lang_value} in Page Settings")
        except Exception as e:
            print(f"WARNING: Error setting Language in Page Settings: {e}")
    
    if remove_slug is not None and set_checkbox_by_label(driver, ["Remove special characters from page slug", "Remove special characters"], bool(remove_slug)):
        updated_any = True

    # 7) Save if a save/apply button is present in the settings panel
    try:
        save_candidates = [
            "//button[contains(., 'Save') or contains(., 'Apply') or contains(., 'Enregistrer')]",
            "//a[contains(., 'Save') or contains(., 'Apply') or contains(., 'Enregistrer')]",
        ]
        for xp in save_candidates:
            try:
                sb = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.XPATH, xp)))
                sb.click(); time.sleep(1)
                break
            except TimeoutException:
                continue
    except Exception:
        pass

    if not updated_any:
        dump_debug(driver, "debug_page_settings_update")
        return False
    return True

def insert_html_and_css_in_editor(driver: webdriver.Chrome, html_content: str, css_content: str) -> bool:
    """
    After page creation, click 'Edit Page' button, then 'Edit Code' button,
    and insert HTML and CSS content.
    
    Flow:
    1. Click "Edit Page" button
    2. Click "Edit Code" button (fa-edit icon)
    3. Find the code editor
    4. Insert: html + "\n<style>\n" + css + "\n</style>"
    """
    print("\n" + "="*60)
    print("INSERTING HTML AND CSS CONTENT")
    print("="*60)
    
    # Step 1: Click "Edit Page" button
    print("Step 1: Looking for 'Edit Page' button...")
    edit_page_xpaths = [
        "//span[contains(text(),'Edit Page')]/parent::button",
        "//button[contains(.,'Edit Page')]",
        "//span[normalize-space()='Edit Page']/ancestor::button",
        "//button[contains(@class,'btn') and contains(.,'Edit')]",
    ]
    
    edit_page_clicked = False
    for xpath in edit_page_xpaths:
        try:
            edit_btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, xpath)))
            scroll_into_view(driver, edit_btn)
            edit_btn.click()
            time.sleep(2)
            edit_page_clicked = True
            print("Successfully clicked 'Edit Page' button")
            break
        except TimeoutException:
            continue
        except Exception as e:
            print(f"Error clicking Edit Page: {e}")
            continue
    
    if not edit_page_clicked:
        print("ERROR: Could not find 'Edit Page' button")
        dump_debug(driver, "debug_edit_page_button")
        return False
    
    # Step 2: Click "Edit Code" button (fa-edit icon)
    print("Step 2: Looking for 'Edit Code' button...")
    edit_code_xpaths = [
        "//span[contains(@class,'fa-edit') and @data-tooltip='Edit Code']",
        "//span[@data-tooltip='Edit Code']",
        "//span[contains(@class,'gjs-pn-btn') and contains(@class,'fa-edit')]",
        "//*[@title='Edit Code']",
        "//button[contains(@title,'Code') or contains(@aria-label,'Code')]",
    ]
    
    edit_code_clicked = False
    for xpath in edit_code_xpaths:
        try:
            edit_code_btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, xpath)))
            scroll_into_view(driver, edit_code_btn)
            edit_code_btn.click()
            time.sleep(2)
            edit_code_clicked = True
            print("Successfully clicked 'Edit Code' button")
            break
        except TimeoutException:
            continue
        except Exception as e:
            print(f"Error clicking Edit Code: {e}")
            continue
    
    if not edit_code_clicked:
        print("ERROR: Could not find 'Edit Code' button")
        dump_debug(driver, "debug_edit_code_button")
        return False
    
    # Step 3: Find the CodeMirror editor and insert content
    print("Step 3: Looking for CodeMirror editor...")
    
    # Prepare the content to insert
    payload = {
        'v1_body': html_content,
        'v1_css': css_content,
        'v1_js': ''
    }

    api_url = os.getenv('API_URL')
    bearer_token = os.getenv('BEARER_TOKEN')
    headers = {
        'Authorization': f'Bearer {bearer_token}',
        'Content-Type': 'application/json'
    }

    if not api_url:
        print("WARNING: API_URL is not set; using original V1 content")
    else:
        try:
            response = requests.post(api_url, json=payload, headers=headers, timeout=60)
            if response.status_code == 200:
                data = response.json()
                html_content = data.get('v2_body', '') or html_content
                css_content = data.get('v2_css', '') or css_content
                print("Content successfully converted from V1 to V2 format")
            else:
                print(f"WARNING: Conversion API returned HTTP {response.status_code}; using original V1 content")
                print(f"Response: {response.text[:500]}")
        except requests.exceptions.RequestException as error:
            print(f"WARNING: Conversion API request failed: {error}; using original V1 content")
        except Exception as error:
            print(f"WARNING: Unexpected conversion error: {error}; using original V1 content")

    combined_content = html_content + "\n<style>\n" + css_content + "\n</style>"
    print(f"Content length: HTML={len(html_content)}, CSS={len(css_content)}, Combined={len(combined_content)}")
    
    # Wait for CodeMirror to be ready
    time.sleep(2)
    
    # Use JavaScript to set CodeMirror content directly
    print("Inserting HTML and CSS content into CodeMirror editor...")
    try:
        # Escape the content for JavaScript
        escaped_content = combined_content.replace('\\', '\\\\').replace('`', '\\`').replace('$', '\\$')
        
        # JavaScript to set CodeMirror content
        script = f"""
        // Find CodeMirror instance
        var codeMirrorElement = document.querySelector('.CodeMirror');
        if (codeMirrorElement && codeMirrorElement.CodeMirror) {{
            var cm = codeMirrorElement.CodeMirror;
            // Set the content
            cm.setValue(`{escaped_content}`);
            // Trigger change event
            cm.refresh();
            return true;
        }}
        
        // Alternative: Try to find textarea and set value
        var textarea = document.querySelector('.CodeMirror textarea');
        if (textarea) {{
            textarea.value = `{escaped_content}`;
            // Trigger input event
            var event = new Event('input', {{ bubbles: true }});
            textarea.dispatchEvent(event);
            return true;
        }}
        
        return false;
        """
        
        result = driver.execute_script(script)
        
        if result:
            print("Successfully inserted HTML and CSS content into CodeMirror")
            time.sleep(1)
        else:
            print("ERROR: Could not find CodeMirror editor")
            dump_debug(driver, "debug_codemirror")
            return False
            
    except Exception as e:
        print(f"ERROR: Failed to insert content into CodeMirror: {e}")
        dump_debug(driver, "debug_codemirror_error")
        return False
    
    # Step 4: Click the Save button (gjs-btn-prim gjs-btn-import)
    print("Step 4: Looking for Save button...")
    save_xpaths = [
        "//button[contains(@class,'gjs-btn-prim') and contains(@class,'gjs-btn-import')]",
        "//button[contains(@class,'gjs-btn-import')]",
        "//button[contains(text(),'Save')]",
        "//button[contains(@class, 'btn') and contains(., 'Save')]",
    ]
    
    save_clicked = False
    for xpath in save_xpaths:
        try:
            save_btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, xpath)))
            scroll_into_view(driver, save_btn)
            save_btn.click()
            time.sleep(2)
            print("Successfully clicked Save button")
            save_clicked = True
            break
        except TimeoutException:
            continue
        except Exception as e:
            print(f"Error clicking save button: {e}")
            continue
    
    if not save_clicked:
        print("WARNING: Could not find Save button, but content may have been inserted")
        dump_debug(driver, "debug_save_button")
    
    print("="*60)
    print("HTML AND CSS INSERTION COMPLETED")
    print("="*60)
    return True

def set_toggle_by_label(driver: webdriver.Chrome, label_text: str, desired_state: bool) -> bool:
    """Set a toggle button (slider) to the desired state based on its label.
    Args:
        driver: Selenium WebDriver instance
        label_text: The text of the label associated with the toggle
        desired_state: True for ON, False for OFF
    Returns:
        True if toggle was set successfully, False otherwise
    """
    try:
        # Find the label - try multiple approaches
        label_xpaths = [
            f"//label[normalize-space()='{label_text}']",
            f"//label[contains(text(),'{label_text}')]",
            f"//*[normalize-space()='{label_text}' and (self::label or self::div)]",
        ]
        
        label = None
        for xpath in label_xpaths:
            try:
                label = WebDriverWait(driver, 2).until(EC.presence_of_element_located((By.XPATH, xpath)))
                if label:
                    break
            except TimeoutException:
                continue
        
        if not label:
            print(f"WARNING: Could not find label for '{label_text}'")
            return False
        
        scroll_into_view(driver, label)
        
        # Find the associated checkbox input - try multiple approaches
        checkbox_xpaths = [
            f"//label[normalize-space()='{label_text}']/following-sibling::*//input[@type='checkbox']",
            f"//label[normalize-space()='{label_text}']/preceding-sibling::*//input[@type='checkbox']",
            f"//label[contains(text(),'{label_text}')]/following::input[@type='checkbox'][1]",
            f"//label[contains(text(),'{label_text}')]/preceding::input[@type='checkbox'][1]",
            f"//label[normalize-space()='{label_text}']/ancestor::div[1]//input[@type='checkbox']",
        ]
        
        checkbox = None
        for xpath in checkbox_xpaths:
            try:
                checkbox = driver.find_element(By.XPATH, xpath)
                if checkbox:
                    break
            except NoSuchElementException:
                continue
        
        if not checkbox:
            print(f"WARNING: Could not find checkbox for '{label_text}'")
            return False
        
        # Check current state
        is_checked = checkbox.is_selected()
        print(f"DEBUG: {label_text} current state: {'ON' if is_checked else 'OFF'}, desired: {'ON' if desired_state else 'OFF'}")
        
        # If state doesn't match desired, click the toggle switch
        if is_checked != desired_state:
            # Try to find the toggle switch (the clickable element)
            toggle_xpaths = [
                f"//label[normalize-space()='{label_text}']/following-sibling::*//label[contains(@class,'switch')]",
                f"//label[normalize-space()='{label_text}']/preceding-sibling::*//label[contains(@class,'switch')]",
                f"//label[normalize-space()='{label_text}']/ancestor::div[1]//label[contains(@class,'switch')]",
                f"//label[contains(text(),'{label_text}')]/following::label[contains(@class,'switch')][1]",
            ]
            
            toggle_clicked = False
            for xpath in toggle_xpaths:
                try:
                    toggle = driver.find_element(By.XPATH, xpath)
                    scroll_into_view(driver, toggle)
                    try:
                        driver.execute_script("arguments[0].click();", toggle)
                    except Exception:
                        toggle.click()
                    time.sleep(0.5)
                    toggle_clicked = True
                    print(f"SUCCESS: Set {label_text} toggle to {'ON' if desired_state else 'OFF'}")
                    break
                except NoSuchElementException:
                    continue
            
            if not toggle_clicked:
                # Last resort: click the checkbox directly
                try:
                    driver.execute_script("arguments[0].click();", checkbox)
                    time.sleep(0.5)
                    print(f"SUCCESS: Set {label_text} toggle to {'ON' if desired_state else 'OFF'} (via checkbox)")
                except Exception as e:
                    print(f"WARNING: Could not click toggle for '{label_text}': {e}")
                    return False
        else:
            print(f"INFO: {label_text} toggle already {'ON' if desired_state else 'OFF'}")
        
        return True
    except Exception as e:
        print(f"WARNING: Could not set {label_text} toggle: {e}")
        import traceback
        traceback.print_exc()
        return False


def set_slug_in_page_settings(driver: webdriver.Chrome, slug_value: str) -> bool:
    """Open/enable custom slug controls in Page Settings and set page-slug value."""
    if not slug_value:
        return False

    try:
        # Step 1: Enable custom slug checkbox
        checkbox = WebDriverWait(driver, 6).until(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    "//input[@id='customize-slug' or @name='customize-slug' or @id='customise-slug']"
                )
            )
        )
        scroll_into_view(driver, checkbox)

        if not checkbox.is_selected():
            try:
                checkbox.click()
            except Exception:
                # Some UIs only allow clicking the label wrapper.
                try:
                    label = driver.find_element(
                        By.XPATH,
                        "//label[@for='customize-slug' or @for='customise-slug' or contains(., 'customize')]"
                    )
                    driver.execute_script("arguments[0].click();", label)
                except Exception:
                    driver.execute_script("arguments[0].click();", checkbox)
            time.sleep(0.4)

        # Step 2: Set page slug field
        slug_input = WebDriverWait(driver, 6).until(
            EC.presence_of_element_located((By.XPATH, "//input[@id='page-slug' or @name='page-slug']"))
        )
        scroll_into_view(driver, slug_input)

        # Ensure the field is writable if UI state lags behind checkbox state
        driver.execute_script("arguments[0].removeAttribute('readonly');", slug_input)

        try:
            slug_input.click()
            slug_input.send_keys(MODIFIER_KEY, 'a')
            slug_input.send_keys(Keys.DELETE)
            slug_input.send_keys(slug_value)
        except Exception:
            driver.execute_script(
                "arguments[0].value = arguments[1];"
                "arguments[0].dispatchEvent(new Event('input', {bubbles:true}));"
                "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
                slug_input,
                slug_value,
            )

        # Fire events in all cases to satisfy reactive forms
        driver.execute_script(
            "arguments[0].dispatchEvent(new Event('input', {bubbles:true}));"
            "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
            slug_input,
        )

        final_value = (slug_input.get_attribute('value') or '').strip()
        if final_value != slug_value:
            print(f"WARNING: Slug field value mismatch after set. expected='{slug_value}' actual='{final_value}'")
        else:
            print(f"SUCCESS: Page slug set to '{slug_value}'")
        return True
    except Exception as e:
        print(f"WARNING: Could not set page slug '{slug_value}' in Page Settings: {e}")
        return False


def verify_slug_in_page_settings(driver: webdriver.Chrome, expected_slug: str, phase: str = "verify") -> bool:
    """Read page-slug and log PASS/FAIL based on expected slug."""
    if not expected_slug:
        return False

    try:
        slug_input = WebDriverWait(driver, 4).until(
            EC.presence_of_element_located((By.XPATH, "//input[@id='page-slug' or @name='page-slug']"))
        )
        current_slug = (slug_input.get_attribute('value') or '').strip()
        if current_slug == expected_slug:
            print(f"PASS: Slug verified at {phase}. value='{current_slug}'")
            return True

        print(
            f"FAIL: Slug drift detected at {phase}. "
            f"expected='{expected_slug}' actual='{current_slug}'"
        )
        return False
    except Exception as e:
        print(f"WARNING: Could not verify slug at {phase}: {e}")
        return False

def set_additional_page_settings(driver: webdriver.Chrome, parsed: Dict[str, Any], page_title: str) -> bool:
    """Set additional page settings: Hidden, Public, Dynamic, Promotional, Brand Kit.
    This function should be called after HTML/CSS insertion.
    
    Flow:
    1. Click on the settings icon (fa-cog) for the page
    2. Click on 'Page settings'
    3. Set Hidden toggle
    4. Set Public toggle
    5. Set Dynamic toggle (if present)
    6. Set Promotional toggle (if present)
    7. Set Brand Kit dropdown (if present)
    8. Save settings
    """
    print("\n" + "="*60)
    print("SETTING ADDITIONAL PAGE SETTINGS")
    print("="*60)

    # Step 1: Find and click the settings icon (fa-cog) for the page
    print(f"Step 1: Looking for settings icon for page '{page_title}'...")
    
    # First, try to find the page in the navigation/sidebar
    try:
        # Look for the page item and its associated settings icon
        page_item_xpaths = [
            f"//nav//*[contains(@class,'page') or contains(@class,'item')][normalize-space()='{page_title}']",
            f"//nav//a[normalize-space()='{page_title}']",
            f"//*[normalize-space()='{page_title}']",
        ]

        page_found = False
        for xpath in page_item_xpaths:
            try:
                page_item = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, xpath)))
                scroll_into_view(driver, page_item)
                page_found = True
                print(f"Found page item: {page_title}")
                break
            except TimeoutException:
                continue

        if not page_found:
            print(f"WARNING: Could not find page '{page_title}' in navigation")
            return False

        # Now look for the settings icon (fa-cog) near this page
        settings_icon_xpaths = [
            f"//i[@data-v-50a4fb28 and contains(@class,'fa-cog')]",
            f"//i[contains(@class,'fa-cog')]",
            f"//*[normalize-space()='{page_title}']/following::i[contains(@class,'fa-cog')][1]",
            f"//*[normalize-space()='{page_title}']/ancestor::*[1]//i[contains(@class,'fa-cog')]",
        ]

        settings_icon_clicked = False
        for xpath in settings_icon_xpaths:
            try:
                settings_icon = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, xpath)))
                scroll_into_view(driver, settings_icon)
                driver.execute_script("arguments[0].click();", settings_icon)
                time.sleep(1)
                settings_icon_clicked = True
                print("Successfully clicked settings icon (fa-cog)")
                break
            except TimeoutException:
                continue
            except Exception as e:
                print(f"Error clicking settings icon: {e}")
                continue

        if not settings_icon_clicked:
            print("WARNING: Could not find or click settings icon")
            dump_debug(driver, "debug_settings_icon")
            return False

    except Exception as e:
        print(f"ERROR: Failed to find page or settings icon: {e}")
        return False

    # Step 2: Click on 'Page settings' link
    print("Step 2: Looking for 'Page settings' link...")

    # Wait a bit for the menu to appear
    time.sleep(1)

    page_settings_xpaths = [
        "//a[contains(.,'Page settings')]",
        "//button[contains(.,'Page settings')]",
        "//a[@data-v-f49958d0 and contains(.,'Page settings')]",
        "//a[.//i[contains(@class,'fa-cog')] and contains(.,'Page settings')]",
        "//div[contains(@class,'dropdown')]//a[contains(.,'Page settings')]",
        "//div[contains(@class,'menu')]//a[contains(.,'Page settings')]",
        "//*[contains(text(),'Page settings')]",
    ]

    page_settings_clicked = False
    for xpath in page_settings_xpaths:
        try:
            page_settings_link = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, xpath)))
            scroll_into_view(driver, page_settings_link)
            driver.execute_script("arguments[0].click();", page_settings_link)
            time.sleep(2)
            page_settings_clicked = True
            print("Successfully clicked 'Page settings' link")
            break
        except TimeoutException:
            continue
        except Exception as e:
            print(f"Error clicking Page settings with xpath {xpath}: {e}")
            continue

    if not page_settings_clicked:
        print("WARNING: Could not find 'Page settings' link, trying alternative approach...")
        # Alternative: Maybe the settings panel is already open, or we need to look for the settings form directly
        try:
            # Check if we're already in a settings panel by looking for common settings elements
            settings_form = driver.find_element(By.XPATH, "//label[contains(text(),'Hidden') or contains(text(),'Public')]")
            if settings_form:
                print("INFO: Settings panel appears to be already open")
                page_settings_clicked = True
        except NoSuchElementException:
            print("ERROR: Could not find or click 'Page settings' link and settings panel not visible")
            dump_debug(driver, "debug_page_settings_link")
            return False

    # Now we should be in the Page Settings panel
    # Extract values from JSON
    slug = (parsed.get('slug') or '').strip()
    hidden = parsed.get('hidden')  # Line 589 in JSON
    public = parsed.get('public')  # Line 1042 in JSON
    dynamic = parsed.get('dynamic')  # Line 1044 in JSON (may not be present)
    promotional = parsed.get('promotional')  # Line 1079 in JSON (may not be present)
    brand_kit = parsed.get('brand_kit')  # Line 1065 in JSON (may not be present)

    print(f"\nSettings from JSON:")
    print(f"  Slug: {slug}")
    print(f"  Hidden: {hidden}")
    print(f"  Public: {public}")
    print(f"  Dynamic: {dynamic}")
    print(f"  Promotional: {promotional}")
    print(f"  Brand Kit: {brand_kit}")

    updated_any = False

    # Step 2.5: Set slug in Page Settings via customize-slug + page-slug
    if slug:
        print(f"\nStep 2.5: Setting slug to '{slug}' in Page Settings...")
        if set_slug_in_page_settings(driver, slug):
            updated_any = True
            verify_slug_in_page_settings(driver, slug, phase="pre-save")
    else:
        print("\nStep 2.5: Skipping slug update (slug not present in JSON)")

    # Step 3: Set Hidden toggle
    if hidden is not None:
        print(f"\nStep 3: Setting Hidden toggle to {'ON' if hidden else 'OFF'}...")
        if set_toggle_by_label(driver, "Hidden", bool(hidden)):
            updated_any = True

    # Step 4: Set Public toggle
    if public is not None:
        print(f"\nStep 4: Setting Public toggle to {'ON' if public else 'OFF'}...")
        if set_toggle_by_label(driver, "Public", bool(public)):
            updated_any = True

    # Step 5: Set Dynamic toggle (if present in UI)
    if dynamic is not None:
        print(f"\nStep 5: Setting Dynamic toggle to {'ON' if dynamic else 'OFF'}...")
        # Try to find Dynamic label first
        try:
            dynamic_label = driver.find_element(By.XPATH, "//label[contains(@class,'tw-w-1/3') and contains(text(),'Dynamic')]")
            if dynamic_label:
                if set_toggle_by_label(driver, "Dynamic", bool(dynamic)):
                    updated_any = True
        except NoSuchElementException:
            print("INFO: Dynamic toggle not present in this page's settings")

    # Step 6: Set Promotional toggle (if present in UI)
    if promotional is not None:
        print(f"\nStep 6: Setting Promotional toggle to {'ON' if promotional else 'OFF'}...")
        # Try to find Promotional label first
        try:
            promo_label = driver.find_element(By.XPATH, "//label[contains(@class,'tw-w-1/3') and contains(text(),'Promotional')]")
            if promo_label:
                if set_toggle_by_label(driver, "Promotional", bool(promotional)):
                    updated_any = True
        except NoSuchElementException:
            print("INFO: Promotional toggle not present in this page's settings")

    # Step 7: Set Brand Kit dropdown (if present in UI)
    if brand_kit is not None:
        print(f"\nStep 7: Setting Brand Kit to '{brand_kit}'...")
        try:
            # Check if Brand Kit field exists - try multiple selectors
            brand_kit_select = None
            select_xpaths = [
                "//label[contains(text(),'Brand Kit')]/following::select[1]",
                "//select[@name='brand_kit']",
                "//select[@id='brand_kit']",
                "//label[@for='brand_kit']/following::select[1]",
            ]

            for xpath in select_xpaths:
                try:
                    brand_kit_select = driver.find_element(By.XPATH, xpath)
                    if brand_kit_select:
                        print(f"Found Brand Kit dropdown using xpath: {xpath}")
                        break
                except NoSuchElementException:
                    continue

            if brand_kit_select:
                scroll_into_view(driver, brand_kit_select)

                from selenium.webdriver.support.ui import Select
                sel = Select(brand_kit_select)

                # First, clear any default selection by selecting empty/inherited option
                print("Clearing default Brand Kit selection...")
                try:
                    # Try to select empty value first to clear default
                    sel.select_by_value("")
                    print("Cleared default Brand Kit selection")
                except Exception as e:
                    print(f"INFO: Could not clear by empty value: {e}")
                    # Try selecting first option as fallback
                    try:
                        sel.select_by_index(0)
                        print("Cleared default Brand Kit by selecting first option")
                    except Exception as e2:
                        print(f"INFO: Could not clear by index: {e2}")

                # Now set the value from JSON
                if not brand_kit or brand_kit == "":
                    print("Brand Kit value from JSON is empty - keeping cleared/inherited state")
                    updated_any = True
                else:
                    # Try to select by value matching the JSON value
                    try:
                        sel.select_by_value(brand_kit)
                        print(f"SUCCESS: Selected Brand Kit: {brand_kit}")
                        updated_any = True
                    except Exception as e:
                        print(f"WARNING: Could not select Brand Kit value '{brand_kit}': {e}")
                        # Try to find by visible text
                        try:
                            for option in sel.options:
                                if brand_kit.lower() in option.text.lower():
                                    sel.select_by_visible_text(option.text)
                                    print(f"SUCCESS: Selected Brand Kit by text match: {option.text}")
                                    updated_any = True
                                    break
                        except Exception as e2:
                            print(f"WARNING: Could not match Brand Kit by text: {e2}")
            else:
                print("INFO: Brand Kit dropdown not found in this page's settings")
        except Exception as e:
            print(f"WARNING: Error handling Brand Kit: {e}")
    else:
        print("\nStep 7: Skipping Brand Kit (not in JSON)")

    # Step 8: Save settings
    print("\nStep 8: Saving settings...")
    save_xpaths = [
        "//button[contains(@class,'btn') and (contains(.,'Save') or contains(.,'Enregistrer'))]",
        "//button[contains(.,'Save')]",
        "//button[contains(.,'Apply')]",
    ]

    save_clicked = False
    for xpath in save_xpaths:
        try:
            save_btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, xpath)))
            scroll_into_view(driver, save_btn)
            save_btn.click()
            time.sleep(2)
            print("Successfully clicked Save button")
            save_clicked = True
            break
        except TimeoutException:
            continue
        except Exception as e:
            print(f"Error clicking save: {e}")
            continue

    if not save_clicked:
        print("WARNING: Could not find Save button, but settings may have been updated")

    # Post-save slug verification requested: detect and log drift explicitly.
    if slug:
        verify_slug_in_page_settings(driver, slug, phase="post-save")

    print("="*60)
    print("ADDITIONAL PAGE SETTINGS COMPLETED")
    print("="*60)

    return updated_any or save_clicked

def set_seo_settings(driver: webdriver.Chrome, parsed: Dict[str, Any], page_title: str) -> bool:
    """Set SEO settings for the page.

    Flow:
    1. Click Save button from previous settings panel
    2. Click on the settings icon (fa-cog) for the page again
    3. Click on 'SEO settings'
    4. Fill in SEO fields: Page Title, Description, Keywords, Abstract
    5. Set Exclude from Sitemap toggle
    6. Set Private but Indexable toggle (only if Public=true)
    7. Save settings
    """
    print("\n" + "="*60)
    print("SETTING SEO SETTINGS")
    print("="*60)

    # Step 1: Click Save button from previous panel
    print("Step 1: Saving previous settings...")
    save_xpaths = [
        "//button[contains(@class,'tw-bg-blue-500') and contains(.,'Save')]",
        "//button[contains(@class,'tw-rounded-3xl') and contains(.,'Save')]",
        "//button[@type='button' and contains(.,'Save')]",
        "//button[contains(.,'Save')]",
    ]

    save_clicked = False
    for xpath in save_xpaths:
        try:
            save_btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, xpath)))
            scroll_into_view(driver, save_btn)
            driver.execute_script("arguments[0].click();", save_btn)
            time.sleep(2)  # Wait for save to complete
            print("Successfully clicked Save button")
            save_clicked = True
            break
        except TimeoutException:
            continue
        except Exception as e:
            print(f"Error clicking save: {e}")
            continue

    if not save_clicked:
        print("WARNING: Could not find Save button, continuing anyway...")

    # Step 2: Close any open panels by pressing Escape
    print("\nStep 2: Closing any open panels...")
    try:
        driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(1)
        print("Pressed ESC to close panels")
    except Exception:
        pass

    # Step 3: Click on the settings icon (fa-cog) for the page again
    print(f"\nStep 3: Looking for settings icon for page '{page_title}'...")

    # Wait a bit for the previous panel to close
    time.sleep(1.5)

    try:
        # Look for the page item and its associated settings icon
        # Note: Page title in navigation might be "Page Title (/page-slug)"
        page_item_xpaths = [
            f"//nav//*[contains(@class,'page') or contains(@class,'item')][normalize-space()='{page_title}']",
            f"//nav//a[normalize-space()='{page_title}']",
            f"//*[normalize-space()='{page_title}']",
            # Also try with starts-with in case slug is appended
            f"//nav//*[contains(@class,'page') or contains(@class,'item')][starts-with(normalize-space(), '{page_title}')]",
            f"//nav//a[starts-with(normalize-space(), '{page_title}')]",
        ]
        
        page_found = False
        for xpath in page_item_xpaths:
            try:
                page_item = WebDriverWait(driver, 2).until(EC.presence_of_element_located((By.XPATH, xpath)))
                scroll_into_view(driver, page_item)
                page_found = True
                page_text = page_item.text.strip()
                print(f"Found page item: '{page_text}'")
                break
            except TimeoutException:
                continue
        
        if not page_found:
            print(f"WARNING: Could not find page '{page_title}' in navigation")
            dump_debug(driver, "debug_seo_page_not_found")
            return False

        # Now look for the settings icon (fa-cog) near this page
        settings_icon_xpaths = [
            f"//i[@data-v-50a4fb28 and contains(@class,'fa-cog')]",
            f"//i[contains(@class,'fa-cog')]",
            f"//*[starts-with(normalize-space(), '{page_title}')]/following::i[contains(@class,'fa-cog')][1]",
        ]
        
        settings_icon_clicked = False
        for xpath in settings_icon_xpaths:
            try:
                settings_icon = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, xpath)))
                scroll_into_view(driver, settings_icon)
                driver.execute_script("arguments[0].click();", settings_icon)
                time.sleep(2)  # Increased wait time for menu to appear
                settings_icon_clicked = True
                print("Successfully clicked settings icon (fa-cog)")
                break
            except TimeoutException:
                continue
        
        if not settings_icon_clicked:
            print("WARNING: Could not find or click settings icon")
            dump_debug(driver, "debug_seo_settings_icon")
            return False
        
    except Exception as e:
        print(f"ERROR: Failed to find page or settings icon: {e}")
        return False
    
    # Step 4: Click on 'SEO settings' link
    print("\nStep 4: Looking for 'SEO settings' link...")
    time.sleep(2)  # Wait for menu to fully appear
    
    # The link has an icon (fa-chart-line) and text "SEO settings"
    # The text might be after the icon, so we need to find the link by icon first
    seo_settings_clicked = False
    
    try:
        # Strategy 1: Find the link by the fa-chart-line icon
        print("Strategy 1: Looking for link with fa-chart-line icon...")
        chart_line_links = driver.find_elements(By.XPATH, "//a[.//i[contains(@class,'fa-chart-line')]]")
        print(f"Found {len(chart_line_links)} links with fa-chart-line icon")
        
        for link in chart_line_links:
            # Get all text content including nested elements
            link_html = link.get_attribute('innerHTML')
            link_text = link.text.strip()
            print(f"  Link HTML snippet: {link_html[:100]}...")
            print(f"  Link text: '{link_text}'")
            
            # Check if this is the SEO settings link
            # It should have fa-chart-line icon and "SEO" in text or HTML
            if 'fa-chart-line' in link_html and ('SEO' in link_html or 'SEO' in link_text):
                print(f"  -> This looks like SEO settings link!")
                scroll_into_view(driver, link)
                driver.execute_script("arguments[0].click();", link)
                time.sleep(2)
                seo_settings_clicked = True
                print("Successfully clicked 'SEO settings' link")
                break

        # Strategy 2: If not found, try direct XPath approaches
        if not seo_settings_clicked:
            print("Strategy 2: Trying direct XPath approaches...")
            seo_settings_xpaths = [
                "//a[@data-v-f49958d0 and .//i[contains(@class,'fa-chart-line')]]",
                "//i[contains(@class,'fas') and contains(@class,'fa-chart-line')]/parent::a",
                "//i[@aria-hidden='true' and contains(@class,'fa-chart-line')]/ancestor::a[1]",
            ]
            
            for xpath in seo_settings_xpaths:
                try:
                    print(f"  Trying xpath: {xpath}")
                    seo_link = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.XPATH, xpath)))
                    scroll_into_view(driver, seo_link)
                    driver.execute_script("arguments[0].click();", seo_link)
                    time.sleep(2)
                    seo_settings_clicked = True
                    print("Successfully clicked 'SEO settings' link")
                    break
                except TimeoutException:
                    continue
                except Exception as e:
                    print(f"  Error: {e}")
                    continue
    
    except Exception as e:
        print(f"ERROR finding SEO settings link: {e}")
    
    if not seo_settings_clicked:
        print("ERROR: Could not find or click 'SEO settings' link")
        dump_debug(driver, "debug_seo_settings_link")
        return False
    
    # Extract SEO values from JSON
    seo_page_title = parsed.get('seo_title_val', '')
    seo_page_description = parsed.get('seo_description', '')
    seo_page_keywords = parsed.get('seo_keywords', '')
    seo_page_abstract = parsed.get('seo_abstract', '')
    exclude_sitemap = parsed.get('exclude_sitemap')
    private_but_indexable = parsed.get('private_but_indexable')
    public = parsed.get('public')
    
    print(f"\nSEO Settings from JSON:")
    print(f"  SEO Page Title: '{seo_page_title}'")
    print(f"  SEO Description: '{seo_page_description}'")
    print(f"  SEO Keywords: '{seo_page_keywords}'")
    print(f"  SEO Abstract: '{seo_page_abstract}'")
    print(f"  Exclude from Sitemap: {exclude_sitemap}")
    print(f"  Private but Indexable: {private_but_indexable}")
    print(f"  Public: {public}")
    
    updated_any = False
    
    # Step 5: Fill in SEO fields
    # 5.1: Page Title
    if seo_page_title is not None:
        print(f"\nStep 5.1: Setting SEO Page Title to '{seo_page_title}'...")
        try:
            page_title_input = WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.XPATH, "//input[@name='seo-page-title']")))
            scroll_into_view(driver, page_title_input)
            page_title_input.clear()
            if seo_page_title:
                page_title_input.send_keys(seo_page_title)
            print(f"SUCCESS: Set SEO Page Title")
            updated_any = True
        except TimeoutException:
            print("WARNING: Could not find SEO Page Title input")
    
    # 5.2: Page Description
    if seo_page_description is not None:
        print(f"\nStep 5.2: Setting SEO Page Description...")
        try:
            page_desc_textarea = WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.XPATH, "//textarea[@name='seo-page-description']")))
            scroll_into_view(driver, page_desc_textarea)
            page_desc_textarea.clear()
            if seo_page_description:
                page_desc_textarea.send_keys(seo_page_description)
            print(f"SUCCESS: Set SEO Page Description")
            updated_any = True
        except TimeoutException:
            print("WARNING: Could not find SEO Page Description textarea")
    
    # 5.3: Page Keywords
    if seo_page_keywords is not None:
        print(f"\nStep 5.3: Setting SEO Page Keywords...")
        try:
            page_keywords_input = WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.XPATH, "//input[@name='seo-page-keywords']")))
            scroll_into_view(driver, page_keywords_input)
            page_keywords_input.clear()
            if seo_page_keywords:
                page_keywords_input.send_keys(seo_page_keywords)
            print(f"SUCCESS: Set SEO Page Keywords")
            updated_any = True
        except TimeoutException:
            print("WARNING: Could not find SEO Page Keywords input")
    
    # 5.4: Page Abstract
    if seo_page_abstract is not None:
        print(f"\nStep 5.4: Setting SEO Page Abstract...")
        try:
            page_abstract_textarea = WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.XPATH, "//textarea[@name='seo-page-abstract']")))
            scroll_into_view(driver, page_abstract_textarea)
            page_abstract_textarea.clear()
            if seo_page_abstract:
                page_abstract_textarea.send_keys(seo_page_abstract)
            print(f"SUCCESS: Set SEO Page Abstract")
            updated_any = True
        except TimeoutException:
            print("WARNING: Could not find SEO Page Abstract textarea")
    
    # Step 6: Set Exclude from Sitemap toggle
    if exclude_sitemap is not None:
        print(f"\nStep 6: Setting 'Exclude from Sitemap' toggle to {'ON' if exclude_sitemap else 'OFF'}...")
        # Use the same toggle function as page settings
        if set_toggle_by_label(driver, "Exclude from Sitemap", bool(exclude_sitemap)):
            updated_any = True
        else:
            # Try alternative labels
            alt_labels = ["Exclude Sitemap", "Sitemap Exclude", "Exclude from sitemap"]
            for label in alt_labels:
                if set_toggle_by_label(driver, label, bool(exclude_sitemap)):
                    updated_any = True
                    break
    
    # Step 7: Set Private but Indexable toggle (only if Public=true)
    if private_but_indexable is not None and public:
        print(f"\nStep 7: Setting 'Private but Indexable' toggle to {'ON' if private_but_indexable else 'OFF'}...")
        print(f"  (Only setting because Public={public})")
        # Use the same toggle function
        if set_toggle_by_label(driver, "Private but Indexable", bool(private_but_indexable)):
            updated_any = True
        else:
            # Try alternative labels
            alt_labels = ["Private but indexable", "Indexable", "Private Indexable"]
            for label in alt_labels:
                if set_toggle_by_label(driver, label, bool(private_but_indexable)):
                    updated_any = True
                    break
    elif private_but_indexable is not None and not public:
        print(f"\nStep 7: Skipping 'Private but Indexable' toggle (Public={public}, must be True)")
    
    # Step 8: Save SEO settings
    print("\nStep 8: Saving SEO settings...")
    save_xpaths = [
        "//button[contains(@class,'tw-bg-blue-500') and contains(.,'Save')]",
        "//button[contains(@class,'tw-rounded-3xl') and contains(.,'Save')]",
        "//button[@type='button' and contains(.,'Save')]",
        "//button[contains(.,'Save')]",
    ]
    
    save_clicked = False
    for xpath in save_xpaths:
        try:
            save_btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, xpath)))
            scroll_into_view(driver, save_btn)
            driver.execute_script("arguments[0].click();", save_btn)
            time.sleep(2)
            print("Successfully clicked Save button")
            save_clicked = True
            break
        except TimeoutException:
            continue
    
    if not save_clicked:
        print("WARNING: Could not find Save button")
    
    print("="*60)
    print("SEO SETTINGS COMPLETED")
    print("="*60)
    
    return updated_any or save_clicked

def is_homepage(parsed: Dict[str, Any]) -> bool:
    """Check if the page is a homepage based on slug='index' only."""
    slug = (parsed.get('slug') or '').lower()

    # Only consider it homepage if slug is exactly 'index'
    is_home = (slug == 'index')

    return is_home

def get_all_page_files(pages_dir: str) -> list:
    """Get all JSON files from the pages directory."""
    import glob
    json_files = glob.glob(os.path.join(pages_dir, "*.json"))
    return sorted(json_files)


def get_run_site_id() -> str:
    """Resolve the site id used for progress tracking."""
    if len(sys.argv) > 1 and str(sys.argv[1]).strip():
        return str(sys.argv[1]).strip()
    return str(os.getenv("INSTANCE_ID") or os.getenv("SITE_ID") or "unknown").strip() or "unknown"


def get_progress_file_path(site_id: str) -> Path:
    """Return the progress file path for this import run."""
    return Path(settings.BASE_DIR) / f"site_{site_id}_pages_import.progress"


def load_page_import_progress(progress_file: Path) -> Dict[str, Any]:
    """Load progress data from disk."""
    if not progress_file.exists():
        return {
            "processed_files": [],
            "successful_files": [],
            "skipped_files": [],
            "failed_files": [],
        }

    try:
        with progress_file.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, dict):
                data.setdefault("processed_files", [])
                data.setdefault("successful_files", [])
                data.setdefault("skipped_files", [])
                data.setdefault("failed_files", [])
                return data
    except Exception as error:
        print(f"WARNING: Could not load progress file {progress_file}: {error}")

    return {
        "processed_files": [],
        "successful_files": [],
        "skipped_files": [],
        "failed_files": [],
    }


def save_page_import_progress(progress_file: Path, progress: Dict[str, Any]) -> None:
    """Persist progress atomically so a crash cannot corrupt the checkpoint."""
    progress_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file = progress_file.with_suffix(progress_file.suffix + ".tmp")
    with temp_file.open("w", encoding="utf-8") as handle:
        json.dump(progress, handle, indent=2, ensure_ascii=False)
    temp_file.replace(progress_file)


def mark_page_as_processed(progress: Dict[str, Any], progress_file: Path, page_file: str, status: str) -> None:
    """Track a page as processed and update the checkpoint file."""
    page_name = os.path.basename(page_file)
    if page_name not in progress["processed_files"]:
        progress["processed_files"].append(page_name)

    bucket_name = f"{status}_files"
    if bucket_name in progress and page_name not in progress[bucket_name]:
        progress[bucket_name].append(page_name)

    progress["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_page_import_progress(progress_file, progress)


def extract_page_weight(page_file: str) -> tuple:
    """
    Extract the weight value from a page JSON file.
    
    Returns:
        tuple: (page_file, weight) where weight is int or float, defaults to 999999 if not found
    """
    try:
        with open(page_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # Navigate through nested settings structure to find weight
        settings = data.get('settings', {})
        
        # Try multiple possible locations for weight value
        weight = None
        
        # Location 1: settings.settings.weight
        if isinstance(settings, dict):
            inner_settings = settings.get('settings', {})
            if isinstance(inner_settings, dict):
                weight = inner_settings.get('weight')
        
        # Location 2: settings.weight
        if weight is None:
            weight = settings.get('weight')
        
        # Location 3: storage.data.weight
        if weight is None:
            storage = data.get('storage', {})
            storage_data = storage.get('data', {})
            weight = storage_data.get('weight')
        
        # Convert to float/int, default to 999999 if not found or invalid
        if weight is not None:
            try:
                weight = float(weight) if isinstance(weight, (int, float, str)) else 999999
                return (page_file, weight)
            except (ValueError, TypeError):
                return (page_file, 999999)
        else:
            return (page_file, 999999)
            
    except Exception as e:
        print(f"WARNING: Could not extract weight from {os.path.basename(page_file)}: {e}")
        return (page_file, 999999)


def sort_pages_by_weight(page_files: list) -> list:
    """
    Sort page files by their weight value (from settings.settings.weight).
    
    Pages with lower weight values are processed first.
    Pages without weight default to 999999 (processed last).
    
    Args:
        page_files: List of page file paths
        
    Returns:
        list: Page files sorted by weight (ascending)
    """
    print("\nExtracting page weights...")
    print("-" * 60)
    
    # Extract weights for all pages
    pages_with_weights = []
    for page_file in page_files:
        page_file, weight = extract_page_weight(page_file)
        pages_with_weights.append((page_file, weight))
        page_name = os.path.basename(page_file)
        if weight == 999999:
            print(f"  {page_name}: [NO WEIGHT FOUND]")
        else:
            print(f"  {page_name}: weight={weight}")
    
    # Sort by weight (ascending - lighter pages first)
    pages_with_weights.sort(key=lambda x: x[1])
    
    print("-" * 60)
    print(f"Import order (by weight):\n")
    for idx, (page_file, weight) in enumerate(pages_with_weights, 1):
        page_name = os.path.basename(page_file)
        if weight == 999999:
            print(f"  {idx:2d}. {page_name} [NO WEIGHT]")
        else:
            print(f"  {idx:2d}. {page_name} (weight={weight})")
    
    print("-" * 60 + "\n")
    
    # Return just the sorted page file paths
    return [page_file for page_file, weight in pages_with_weights]

def main():
    env = load_env()
    site_id = get_run_site_id()
    progress_file = get_progress_file_path(site_id)
    progress = load_page_import_progress(progress_file)
    processed_files = set(progress.get("processed_files", []))
    print(f"Using progress file: {progress_file}")

    # Get all page files or single file
    if TARGET_PAGE_JSON_BASENAME:
        # Single page mode
        page_files = [pick_one_page_json(DEFAULT_V1_PAGES_DIR, TARGET_PAGE_JSON_BASENAME)]
        print(f"Processing single page: {TARGET_PAGE_JSON_BASENAME}")
    else:
        # All pages mode
        page_files = get_all_page_files(DEFAULT_V1_PAGES_DIR)
        print(f"Found {len(page_files)} page JSON files to process")

    if processed_files:
        before_count = len(page_files)
        page_files = [page_file for page_file in page_files if os.path.basename(page_file) not in processed_files]
        print(f"Resuming from progress: skipping {before_count - len(page_files)} already processed page(s)")

    if not page_files:
        print("ERROR: No page files found!")
        return

    # Sort pages by weight before processing (for smooth transaction order)
    print("\n" + "="*80)
    print("SORTING PAGES BY WEIGHT")
    print("="*80)
    page_files = sort_pages_by_weight(page_files)
    print("="*80)

    # Separate homepage from other pages
    homepage_file = None
    other_page_files = []

    for page_file in page_files:
        try:
            parsed = parse_page_json(page_file)
            # Skip deleted pages
            if parsed.get('is_deleted'):
                print(f"Skipping deleted page: {os.path.basename(page_file)} (deleted by {parsed.get('deleted_by')})")
                continue
            if is_homepage(parsed):
                homepage_file = page_file
                print(f"Found homepage: {os.path.basename(page_file)} - {parsed.get('title')}")
            else:
                other_page_files.append(page_file)
        except Exception as e:
            # Handle encoding errors gracefully - log to file instead of console
            import traceback
            error_msg = f"WARNING: Could not parse {os.path.basename(page_file)}: {str(e)[:100]}\n"
            error_msg += traceback.format_exc()
            try:
                with open("parse_errors.log", "a", encoding="utf-8") as log_file:
                    log_file.write(error_msg + "\n")
                print(f"WARNING: Could not parse file (see parse_errors.log)")
            except:
                pass
            # Don't skip the file - it might still be valid
            # Try to add it to other_page_files anyway
            other_page_files.append(page_file)
            continue

    # Process homepage first (update existing), then create other pages
    pages_to_process = []

    pages_to_process.extend([(f, False) for f in other_page_files])

    print(f"\nProcessing order:")
    if homepage_file:
        print(f"Homepage found but SKIPPED: {os.path.basename(homepage_file)}")
    print(f"Other pages to create: {len(other_page_files)} pages")
    print("="*60)

    # Start Selenium
    driver = create_driver(headless=False)

    successful_pages = []
    failed_pages = []
    skipped_pages = []

    try:
        login_to_dashboard(driver, env["SITENAME"], env["USERNAME"], env["PASSWORD"], env["INSTANCE_ID"])
        # Open builder in another tab per the user's flow
        open_builder_in_new_tab(driver, env["SITENAME"], env["INSTANCE_ID"])

        # Wait for builder to load
        time.sleep(3)

        # Process each page
        for idx, (page_file, is_home) in enumerate(pages_to_process, 1):
            print("\n" + "="*80)
            print(f"PROCESSING PAGE {idx}/{len(pages_to_process)}")
            print("="*80)
            print(f"File: {os.path.basename(page_file)}")
            print(f"Type: {'HOMEPAGE (Update Existing)' if is_home else 'NEW PAGE (Create)'}")
            print("="*80)

            try:
                # Parse the page JSON
                parsed = parse_page_json(page_file)

                # Check if page is deleted
                if parsed.get('is_deleted'):
                    print(f"\n{'='*60}")
                    print(f"SKIPPING DELETED PAGE: {os.path.basename(page_file)}")
                    print(f"  Deleted At: {parsed.get('deleted_at')}")
                    print(f"  Deleted By: {parsed.get('deleted_by')}")
                    print(f"{'='*60}")
                    skipped_pages.append((page_file, f"Deleted (by {parsed.get('deleted_by')})"))
                    continue

                page_title = parsed.get('title')

                if not page_title:
                    print(f"ERROR: No title found in {page_file}, skipping...")
                    failed_pages.append((page_file, "No title"))
                    continue

                # Print page info with encoding error handling
                try:
                    print(f"Page Title: {page_title}")
                    print(f"Language: {parsed.get('language')}")
                    print(f"Brand: {parsed.get('brand')}")
                    print(f"Indication: {parsed.get('indication')}")
                    print(f"Therapeutic Area: {parsed.get('therapeutic_area')}")
                except Exception as print_err:
                    print(f"Page Title: [Contains special characters]")
                    print(f"Language: {parsed.get('language', 'N/A')}")

                # Check if page already exists (skip for homepage)
                # For multi-lingual sites, skip duplicate check as same title can exist in different languages
                if not is_home and not IS_MULTILINGUAL_SITE:
                    if check_if_page_exists(driver, page_title):
                        print(f"\nWARNING: Page '{page_title}' already exists. Skipping...")
                        skipped_pages.append((page_file, page_title))
                        mark_page_as_processed(progress, progress_file, page_file, "skipped")
                        continue
                elif not is_home and IS_MULTILINGUAL_SITE:
                    print(f"\nINFO: Multi-lingual site mode enabled - allowing duplicate page titles with different languages")

                    # Open menu and click '+ ADD PAGE'
                    ok = open_menu_and_click_add_page(driver)
                    if not ok:
                        print(f"ERROR: Failed to open menu and click '+ ADD PAGE'")
                        failed_pages.append((page_file, "Failed to open ADD PAGE"))
                        continue

                    # Fill the modal and create the page
                    filled = fill_create_page_modal(driver, parsed)
                    if not filled:
                        print(f"ERROR: Failed to fill Create Page modal")
                        failed_pages.append((page_file, "Failed to fill modal"))
                        continue

                    print(f"\nSUCCESS: Page '{page_title}' created!")
                else:
                    # For homepage, we need to navigate to it and edit it
                    print("\nNavigating to existing homepage...")
                    # TODO: Add logic to navigate to homepage if needed
                    # For now, assume we can directly insert content

                # Wait for page to be ready
                time.sleep(3)

                # Insert HTML and CSS content
                html_content = parsed.get('html', '')
                css_content = parsed.get('css', '')

                if html_content or css_content:
                    print("\nConverting V1 content to V2 format...")
                    try:
                        # Convert V1 content to V2 format using the API
                        converted_content = convert_v1_to_v2(html_content, css_content)
                        print("Content successfully converted from V1 to V2 format")
                        
                        # Split back into HTML and CSS for insertion
                        if '<style>' in converted_content:
                            html_part = converted_content.split('<style>')[0].strip()
                            css_part = converted_content.split('<style>')[1].replace('</style>', '').strip()
                        else:
                            html_part = converted_content
                            css_part = ''
                            
                        print("\nInserting converted HTML and CSS content...")
                        content_inserted = insert_html_and_css_in_editor(driver, html_part, css_part)
                        
                        if content_inserted:
                            print("Converted HTML and CSS content successfully inserted!")
                        else:
                            print("WARNING: Could not insert converted content, trying original content...")
                            # Fallback to original content if converted content fails
                            content_inserted = insert_html_and_css_in_editor(driver, html_content, css_content)
                            if content_inserted:
                                print("Original HTML and CSS content successfully inserted!")
                            else:
                                print("ERROR: Failed to insert both converted and original content")
                                failed_pages.append((page_file, "Failed to insert content"))
                                continue
                                
                    except Exception as e:
                        print(f"Error during content conversion: {str(e)}")
                        print("Falling back to original content...")
                        # If conversion fails, try with original content
                        content_inserted = insert_html_and_css_in_editor(driver, html_content, css_content)
                        if content_inserted:
                            print("Original HTML and CSS content successfully inserted!")
                        else:
                            print("ERROR: Failed to insert original content after conversion failed")
                            failed_pages.append((page_file, f"Content conversion and insertion failed: {str(e)[:100]}"))
                            continue
                else:
                    print("No HTML or CSS content found")

                # Set additional page settings (Hidden, Public, Dynamic, Promotional, Brand Kit)
                print("\nSetting additional page settings...")
                settings_updated = set_additional_page_settings(driver, parsed, page_title)
                if settings_updated:
                    print("Additional page settings successfully updated!")
                else:
                    print("WARNING: Could not update all additional page settings")

                # Set SEO settings
                print("\nSetting SEO settings...")
                seo_updated = set_seo_settings(driver, parsed, page_title)
                if seo_updated:
                    print("SEO settings successfully updated!")
                    successful_pages.append((page_file, page_title))
                    mark_page_as_processed(progress, progress_file, page_file, "successful")
                else:
                    print("WARNING: Could not update all SEO settings")
                    # Still consider it successful if content was inserted
                    successful_pages.append((page_file, page_title))
                    mark_page_as_processed(progress, progress_file, page_file, "successful")

                print(f"\nPage {idx}/{len(pages_to_process)} completed!")

                # Small delay between pages
                time.sleep(2)

            except Exception as e:
                # Handle encoding errors gracefully
                try:
                    error_msg = str(e)
                    if 'charmap' in error_msg or 'encode' in error_msg:
                        print(f"\nERROR processing {os.path.basename(page_file)}: Encoding error (Chinese characters)")
                        failed_pages.append((page_file, "Encoding error"))
                    else:
                        print(f"\nERROR processing {os.path.basename(page_file)}: {error_msg[:100]}")
                        failed_pages.append((page_file, error_msg[:100]))
                except:
                    print(f"\nERROR processing file: Unknown error")
                    failed_pages.append((page_file, "Unknown error"))
                # Continue to next page instead of stopping
                continue

        # Final summary
        print("\n" + "="*80)
        print("MIGRATION SUMMARY")
        print("="*80)
        print(f"Total pages processed: {len(pages_to_process)}")
        print(f"Successfully migrated: {len(successful_pages)}")
        print(f"Skipped (already exist): {len(skipped_pages)}")
        print(f"Failed: {len(failed_pages)}")
        print("="*80)

        if successful_pages:
            print("\nSuccessfully migrated pages:")
            for file, title in successful_pages:
                print(f"  [OK] {title} ({os.path.basename(file)})")

        if skipped_pages:
            print("\nSkipped pages (already exist):")
            for file, title in skipped_pages:
                print(f"  [SKIP] {title} ({os.path.basename(file)})")

        if failed_pages:
            print("\nFailed pages:")
            for file, reason in failed_pages:
                print(f"  [FAIL] {os.path.basename(file)}: {reason}")

        print("\n" + "="*80)
        print("MIGRATION COMPLETED!")
        print("="*80)

    finally:
        # Keep the browser open for verification
        print("\nBrowser will stay open for 60 seconds for verification...")
        time.sleep(60)
        driver.quit()


if __name__ == "__main__":
    main()
