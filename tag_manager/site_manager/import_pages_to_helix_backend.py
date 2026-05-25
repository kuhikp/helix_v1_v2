#!/usr/bin/env python3
"""
Import converted HTML pages into Helix backend using Playwright.

Workflow:
1. Login to Webbuilder using credentials from .env
2. Open the configured website editor
3. Import homepage HTML from the detected homepage index.html
4. Create subpages for all remaining HTML files using parent-folder titles
5. Import each subpage HTML after page creation

Notes:
- Homepage title is derived from the parent folder but not entered in UI.
- For subpages, the page title is always the parent folder name.
- If Save Page is disabled, the page is logged to a CSV for manual intervention.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from playwright.sync_api import Locator, sync_playwright


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

WEBBUILDER_DASHBOARD_URL = "https://webbuilder.pfizer/webbuilder/dashboard"
WEBBUILDER_USERNAME_ENV = "USERNAME"
WEBBUILDER_PASSWORD_ENV = "PASSWORD"
WEBBUILDER_INSTANCE_ID_ENV = "INSTANCE_ID"

WEBBUILDER_LOGIN_WAIT_MS = 5000
WEBBUILDER_MENU_WAIT_MS = 2000
WEBBUILDER_EDITOR_LOAD_WAIT_MS = 5000
WEBBUILDER_EDIT_MODE_WAIT_MS = 6000
WEBBUILDER_SHORT_WAIT_MS = 1000

EDIT_PAGE_BUTTON_XPATH = '//*[@id="wrapper"]/nav/div[2]/span/button'
HAMBURGER_MENU_XPATH = '//*[@id="wrapper"]/nav/div[1]/div[2]/div/div[1]/i'
ADD_PAGE_BUTTON_XPATH = (
    '//*[@id="webbuilder-editor-content-wrapper"]/div/div[1]/div/div/div[2]'
    '/div/div/div/div[1]/div/button'
)
PAGE_TITLE_XPATH = '//*[@id="page-title"]'
INDICATION_CONTAINER_XPATH = (
    '//*[@id="webbuilder-editor-content-wrapper"]/div/div[1]/div/div/div[3]/div/div[2]'
    '/div/div/div[2]/section[1]/div[2]/div[2]/section/div'
)
THERAPEUTIC_AREA_CONTAINER_XPATH = (
    '//*[@id="webbuilder-editor-content-wrapper"]/div/div[1]/div/div/div[3]/div/div[2]'
    '/div/div/div[2]/section[1]/div[2]/div[3]/section/div'
)
SAVE_PAGE_BUTTON_XPATH = (
    '//*[@id="webbuilder-editor-content-wrapper"]/div/div[1]/div/div/div[3]/div/div[1]/div/button'
)

IMPORT_EDITOR_CLICK_XPATH = (
    '//*[@id="gjs-mdl-c"]/div/div/div[6]/div[1]/div/div/div/div[5]/div/pre'
)
IMPORT_TEXTAREA_FILL_XPATH = '//*[@id="gjs-mdl-c"]/div/div/div[1]/textarea'
OPEN_LAYER_MANAGER_BUTTON_XPATH = '//*[@id="grapes-js-vue-wrapper"]/div[1]/div/div[1]/div[2]/div[3]/div/span[3]'
SELECT_BODY_LAYER_XPATH = '//*[@id="grapes-js-vue-wrapper"]/div[1]/div/div[1]/div[2]/div[5]/div[3]/div[1]/div[1]/div/div'
OPEN_STYLE_MANAGER_BUTTON_XPATH = '//*[@id="grapes-js-vue-wrapper"]/div[1]/div/div[1]/div[2]/div[3]/div/span[1]'
ADD_CLASS_BUTTON_XPATH = '//*[@id="gjs-clm-add-tag"]'
CLASS_INPUT_XPATH = '//*[@id="gjs-clm-new"]'
BODY_CLASS_ACTION_WAIT_MS = 700


logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("helix_page_importer")

PROCESS_STOP_MESSAGE = "Process Stopped Abruptly"
IMPORT_PROGRESS_FILE_NAME = ".helix_import_progress.json"
BODY_CLASSES_FILE_NAME = "body_classes.json"


def _raise_process_stopped(_signum, _frame) -> None:
    raise RuntimeError(PROCESS_STOP_MESSAGE)


def configure_abort_signal_handlers() -> None:
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _raise_process_stopped)
        except Exception:
            continue


def load_import_progress(progress_file: Path) -> tuple[bool, set[str]]:
    if not progress_file.exists():
        return False, set()

    try:
        payload = json.loads(progress_file.read_text(encoding="utf-8", errors="ignore"))
        if not isinstance(payload, dict):
            return False, set()

        homepage_processed = bool(payload.get("homepage_processed", False))
        processed_subpages_raw = payload.get("processed_subpages") or []
        if not isinstance(processed_subpages_raw, list):
            processed_subpages_raw = []

        processed_subpages = {str(item) for item in processed_subpages_raw if str(item).strip()}
        return homepage_processed, processed_subpages
    except Exception as progress_error:
        logger.warning("Unable to read import progress file %s: %s", progress_file, progress_error)
        return False, set()


def save_import_progress(progress_file: Path, homepage_processed: bool, processed_subpages: set[str]) -> None:
    progress_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "homepage_processed": bool(homepage_processed),
        "processed_subpages": sorted(processed_subpages),
        "processed_count": len(processed_subpages),
        "updated_at": int(time.time()),
    }
    temp_file = progress_file.with_name(progress_file.name + ".tmp")
    temp_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temp_file.replace(progress_file)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@dataclass
class PageImportItem:
    html_file: Path
    title: str
    is_homepage: bool


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def load_environment() -> None:
    project_root = Path(__file__).resolve().parent.parent
    load_dotenv(project_root / ".env")


def collect_html_files(input_folder: Path) -> list[Path]:
    html_suffixes = {".html", ".htm"}
    files = [
        path
        for path in input_folder.rglob("*")
        if path.is_file() and not path.is_symlink() and path.suffix.lower() in html_suffixes
    ]
    return sorted(files)


def normalize_site_identifier(value: str) -> str:
    text = (value or "").strip().lower()
    if not text:
        return ""

    parse_target = text if "://" in text else f"https://{text}"
    parsed = urlparse(parse_target)
    host = (parsed.netloc or parsed.path or "").strip().lower()
    host = host.split("/", 1)[0].split(":", 1)[0].strip(".")
    if host.startswith("www."):
        host = host[4:]
    return host


def resolve_nested_import_source_folder(input_folder: Path, expected_site_url: str = "") -> Path:
    """Resolve nested site folder when import root points to generated_helix_output."""
    if (input_folder / BODY_CLASSES_FILE_NAME).exists():
        return input_folder

    child_dirs = sorted(
        [child for child in input_folder.iterdir() if child.is_dir()],
        key=lambda p: p.name.lower(),
    )

    body_class_candidates = [
        child for child in child_dirs if (child / BODY_CLASSES_FILE_NAME).exists()
    ]

    requested_site = normalize_site_identifier(expected_site_url)
    if requested_site:
        by_name_matches = [
            child for child in child_dirs
            if normalize_site_identifier(child.name) == requested_site
        ]
        if len(by_name_matches) == 1:
            logger.info("Matched site URL '%s' to converted folder: %s", expected_site_url, by_name_matches[0])
            return by_name_matches[0]

        if len(by_name_matches) > 1:
            raise RuntimeError(
                "Multiple converted folders matched site URL '%s': %s"
                % (expected_site_url, ", ".join(folder.name for folder in by_name_matches))
            )

        raise RuntimeError(
            "No converted folder matched site URL '%s'. Available folders: %s"
            % (expected_site_url, ", ".join(folder.name for folder in child_dirs[:20]))
        )

    if len(body_class_candidates) == 1:
        logger.info("Detected nested converted site folder: %s", body_class_candidates[0])
        return body_class_candidates[0]

    if len(body_class_candidates) > 1:
        raise RuntimeError(
            "Multiple nested converted site folders found. "
            "Pass --input-folder pointing to the exact site folder."
        )

    html_candidates: list[Path] = []
    for child in child_dirs:
        has_html = any(
            path.is_file() and path.suffix.lower() in {".html", ".htm"}
            for path in child.rglob("*")
        )
        if has_html:
            html_candidates.append(child)

    if len(html_candidates) == 1:
        logger.info("Detected nested HTML source folder: %s", html_candidates[0])
        return html_candidates[0]

    if len(html_candidates) > 1:
        raise RuntimeError(
            "Multiple nested folders with HTML files found. "
            "Pass --input-folder pointing to the exact site folder."
        )

    return input_folder


def parent_folder_title(html_file: Path) -> str:
    folder_name = html_file.parent.name.strip()
    if folder_name:
        return folder_name
    return html_file.stem.strip() or "untitled"


def derive_page_title(html_file: Path, input_folder: Path) -> str:
    """Derive page title from folder for index pages, or filename for root standalone files."""
    if html_file.name.lower() == "index.html":
        return parent_folder_title(html_file)

    if html_file.parent == input_folder:
        return html_file.stem.strip() or "untitled"

    return parent_folder_title(html_file)


def derive_body_class_key_from_html_file(html_file: Path, input_folder: Path) -> str:
    rel = html_file.relative_to(input_folder)
    if rel.name.lower() == "index.html":
        parent_name = rel.parent.name.strip()
        if parent_name:
            return parent_name
        return "index.html"
    return rel.name


def load_body_classes_map(input_folder: Path) -> dict[str, list[str]]:
    body_classes_file = input_folder / BODY_CLASSES_FILE_NAME
    if not body_classes_file.exists():
        logger.info("Body classes JSON not found at %s; skipping class-apply step.", body_classes_file)
        return {}

    try:
        payload = json.loads(body_classes_file.read_text(encoding="utf-8", errors="ignore"))
        if not isinstance(payload, dict):
            return {}

        normalized: dict[str, list[str]] = {}
        for key, value in payload.items():
            if isinstance(value, list):
                normalized[str(key)] = [str(item).strip() for item in value if str(item).strip()]
        return normalized
    except Exception as load_error:
        logger.warning("Unable to read body classes JSON (%s): %s", body_classes_file, load_error)
        return {}


def locate_homepage_index(html_files: list[Path], input_folder: Path) -> "Path | None":
    root_index = input_folder / "index.html"
    if root_index in html_files:
        return root_index

    # Homepage must be the root-level index.html only.
    # Nested */index.html files are treated as subpages.
    return None


def build_import_plan(input_folder: Path) -> list[PageImportItem]:
    html_files = collect_html_files(input_folder)
    if not html_files:
        raise RuntimeError(f"No .html/.htm files found under: {input_folder}")

    homepage_file = locate_homepage_index(html_files, input_folder)

    non_index_files = [
        path for path in html_files if path.name.lower() != "index.html"
    ]
    skipped_non_index_files = [
        path for path in non_index_files if path.parent != input_folder
    ]
    if skipped_non_index_files:
        logger.info(
            "Skipping %d non-index HTML files for page creation: %s",
            len(skipped_non_index_files),
            ", ".join(str(path.relative_to(input_folder)) for path in skipped_non_index_files[:8]),
        )

    index_subpages = [
        path
        for path in html_files
        if path != homepage_file and path.name.lower() == "index.html"
    ]
    root_non_index_subpages = [
        path for path in non_index_files if path.parent == input_folder
    ]
    subpages = index_subpages + root_non_index_subpages
    subpages.sort(key=lambda path: str(path.relative_to(input_folder)).lower())

    plan: list[PageImportItem] = []

    if homepage_file is not None:
        plan.append(
            PageImportItem(
                html_file=homepage_file,
                title=parent_folder_title(homepage_file),
                is_homepage=True,
            )
        )
    else:
        logger.warning(
            "No index.html found in '%s' — homepage import will be skipped. "
            "Manual intervention required to import the homepage separately.",
            input_folder,
        )

    for html_file in subpages:
        plan.append(
            PageImportItem(
                html_file=html_file,
                title=derive_page_title(html_file, input_folder),
                is_homepage=False,
            )
        )

    return plan


def read_html_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def append_manual_intervention_row(csv_path: Path, title: str, html_file: Path, reason: str) -> None:
    file_exists = csv_path.exists()
    with csv_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        if not file_exists:
            writer.writerow(["Page Title", "HTML File", "Reason"])
        writer.writerow([title, str(html_file), reason])


def ensure_click(page, locator: Locator, description: str, wait_ms: int = WEBBUILDER_SHORT_WAIT_MS) -> None:
    locator.click()
    logger.info("Clicked: %s", description)
    page.wait_for_timeout(wait_ms)


def is_disabled(locator: Locator) -> bool:
    count = locator.count()
    if count == 0:
        return True

    try:
        disabled_prop = bool(locator.evaluate("el => !!el.disabled"))
    except Exception:
        disabled_prop = False

    disabled_attr = locator.get_attribute("disabled")
    aria_disabled = (locator.get_attribute("aria-disabled") or "").strip().lower()
    class_attr = (locator.get_attribute("class") or "").lower()

    if disabled_prop:
        return True
    if disabled_attr is not None:
        return True
    if aria_disabled == "true":
        return True
    if "disabled" in class_attr:
        return True

    return False


def is_meaningful_selection_text(text: str) -> bool:
    normalized = " ".join((text or "").split()).strip().lower()
    if not normalized:
        return False

    placeholders = {
        "select",
        "select...",
        "please select",
        "choose",
        "choose...",
        "indication",
        "therapeutic area",
        "select indication",
        "select therapeutic area",
    }
    return normalized not in placeholders and not normalized.startswith("search")


def has_selected_value(page, container_xpath: str) -> bool:
    container = page.locator(f"xpath={container_xpath}")
    if container.count() == 0:
        return False

    # Common selected-value renderers used in dropdown/multiselect widgets.
    selected_text_selectors = (
        ".multiselect__single",
        ".multiselect__tag",
        ".vs__selected",
        ".select2-selection__rendered",
        "li.selected span",
        "li.is-selected span",
        "[aria-selected='true'] span",
    )

    for selector in selected_text_selectors:
        selected_nodes = container.locator(selector)
        for idx in range(selected_nodes.count()):
            text = selected_nodes.nth(idx).inner_text().strip()
            if is_meaningful_selection_text(text):
                return True

    value_nodes = container.locator("input[value], textarea")
    for idx in range(value_nodes.count()):
        value = (value_nodes.nth(idx).get_attribute("value") or "").strip()
        if is_meaningful_selection_text(value):
            return True

    data_value = (container.get_attribute("data-value") or "").strip()
    if is_meaningful_selection_text(data_value):
        return True

    return False


def pick_first_li_with_non_empty_span(page, container_xpath: str, label: str) -> bool:
    container = page.locator(f"xpath={container_xpath}")
    container.click()
    page.wait_for_timeout(WEBBUILDER_SHORT_WAIT_MS)

    options = container.locator("li:has(span)")
    if options.count() == 0:
        # Fallback for UIs that render dropdown options outside the source container.
        options = page.locator("li:has(span)")

    option_count = options.count()
    for index in range(option_count):
        option = options.nth(index)
        span = option.locator("span").first
        if span.count() == 0:
            continue

        text = span.inner_text().strip()
        if not text:
            continue

        option.click()
        page.wait_for_timeout(WEBBUILDER_SHORT_WAIT_MS)
        title_input = page.locator(f"xpath={PAGE_TITLE_XPATH}")
        title_input.click()
        page.wait_for_timeout(WEBBUILDER_SHORT_WAIT_MS)
        logger.info("Selected default %s: %s", label, text)
        return True

    logger.warning("No option with text found for %s.", label)
    return False


# ---------------------------------------------------------------------------
# Webbuilder automation
# ---------------------------------------------------------------------------


def login_to_webbuilder(page, username: str, password: str) -> None:
    """Use the same login flow as convert_html_to_helix_backend.py."""
    logger.info("Navigating to Webbuilder dashboard...")
    page.goto(WEBBUILDER_DASHBOARD_URL)
    page.wait_for_timeout(WEBBUILDER_LOGIN_WAIT_MS)

    try:
        page.click('xpath=//*[@id="app"]/div[1]/div[1]/div[1]/div/div[2]/a')
        page.wait_for_timeout(WEBBUILDER_LOGIN_WAIT_MS)
    except Exception:
        logger.info("Login entry link was not clickable; continuing with current session state.")

    page.fill('xpath=//*[@id="username"]', username)
    page.fill('xpath=//*[@id="password"]', password)
    page.press('xpath=//*[@id="password"]', "Enter")
    page.wait_for_timeout(WEBBUILDER_MENU_WAIT_MS)
    logger.info("Webbuilder login flow completed.")


def goto_website_builder(page, instance_id: str) -> None:
    editor_url = f"https://webbuilder.pfizer/builder/website/{instance_id}"
    logger.info("Navigating to website builder: %s", editor_url)
    page.goto(editor_url)
    page.wait_for_timeout(WEBBUILDER_EDITOR_LOAD_WAIT_MS)


def click_edit_page(page) -> None:
    edit_button = page.locator(f"xpath={EDIT_PAGE_BUTTON_XPATH}")
    edit_button.click()
    page.wait_for_timeout(WEBBUILDER_EDIT_MODE_WAIT_MS)
    logger.info("Editor mode opened.")


def apply_body_classes(page, body_classes: list[str]) -> None:
    if not body_classes:
        return

    try:
        page.locator(f"xpath={OPEN_LAYER_MANAGER_BUTTON_XPATH}").click()
    except Exception:
        page.locator('[data-tooltip="Open Layer Manager"]').click()
    page.wait_for_timeout(BODY_CLASS_ACTION_WAIT_MS)

    page.locator(f"xpath={SELECT_BODY_LAYER_XPATH}").click()
    page.wait_for_timeout(BODY_CLASS_ACTION_WAIT_MS)

    try:
        page.locator(f"xpath={OPEN_STYLE_MANAGER_BUTTON_XPATH}").click()
    except Exception:
        page.locator('[data-tooltip="Open Style Manager"]').click()
    page.wait_for_timeout(BODY_CLASS_ACTION_WAIT_MS)

    add_class_btn = page.locator(f"xpath={ADD_CLASS_BUTTON_XPATH}")
    class_input = page.locator(f"xpath={CLASS_INPUT_XPATH}")

    for class_name in body_classes:
        add_class_btn.click()
        page.wait_for_timeout(BODY_CLASS_ACTION_WAIT_MS)
        try:
            class_input.click(force=True)
            class_input.fill(class_name)
            class_input.press("Enter")
        except Exception:
            page.keyboard.type(class_name)
            page.keyboard.press("Enter")
        page.wait_for_timeout(BODY_CLASS_ACTION_WAIT_MS)

    logger.info("Applied %d body classes in Style Manager.", len(body_classes))


def import_page_html(page, html_content: str, body_classes: list[str] | None = None) -> None:
    import_btn = page.locator('[data-tooltip="Import"]')
    import_btn.click()
    page.wait_for_timeout(WEBBUILDER_SHORT_WAIT_MS)

    import_field = page.locator(f"xpath={IMPORT_EDITOR_CLICK_XPATH}")
    import_field.click()
    page.wait_for_timeout(WEBBUILDER_SHORT_WAIT_MS)

    import_fill = page.locator(f"xpath={IMPORT_TEXTAREA_FILL_XPATH}")
    import_fill.fill(html_content)
    page.locator(".gjs-btn-import").click()
    page.wait_for_timeout(WEBBUILDER_SHORT_WAIT_MS)
    logger.info("Imported HTML into current page.")
    apply_body_classes(page, body_classes or [])


def create_subpage(page, title: str) -> tuple[bool, str]:
    ensure_click(
        page,
        page.locator(f"xpath={HAMBURGER_MENU_XPATH}"),
        "Hamburger menu",
        WEBBUILDER_MENU_WAIT_MS,
    )
    ensure_click(
        page,
        page.locator(f"xpath={ADD_PAGE_BUTTON_XPATH}"),
        "Add Page button",
        WEBBUILDER_MENU_WAIT_MS,
    )

    title_input = page.locator(f"xpath={PAGE_TITLE_XPATH}")
    title_input.click()
    page.wait_for_timeout(WEBBUILDER_SHORT_WAIT_MS)
    title_input.fill(title)
    page.wait_for_timeout(WEBBUILDER_SHORT_WAIT_MS)
    logger.info("Filled page title: %s", title)

    indication_already_selected = has_selected_value(page, INDICATION_CONTAINER_XPATH)
    therapeutic_already_selected = has_selected_value(page, THERAPEUTIC_AREA_CONTAINER_XPATH)
    logger.info(
        "Existing values detected - Indication: %s, Therapeutic Area: %s",
        "YES" if indication_already_selected else "NO",
        "YES" if therapeutic_already_selected else "NO",
    )

    save_button = page.locator(f"xpath={SAVE_PAGE_BUTTON_XPATH}")
    if is_disabled(save_button):
        logger.info("Save Page is disabled. Applying default dropdown selections.")

        # adding default "Indiciation"
        pick_first_li_with_non_empty_span(page, INDICATION_CONTAINER_XPATH, "Indiciation")

        # adding default "Therapeutic Area"
        pick_first_li_with_non_empty_span(page, THERAPEUTIC_AREA_CONTAINER_XPATH, "Therapeutic Area")

        page.wait_for_timeout(WEBBUILDER_SHORT_WAIT_MS)
        if is_disabled(save_button):
            return False, "Save Page button is still disabled after default selections"

    try:
        save_button.click()
        page.wait_for_timeout(WEBBUILDER_LOGIN_WAIT_MS)
    except Exception as exc:
        return False, f"Failed to click Save Page: {exc}"

    logger.info("Subpage saved: %s", title)
    return True, ""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import converted HTML pages into Helix backend using Playwright."
    )
    parser.add_argument(
        "--input-folder",
        required=True,
        type=Path,
        help="Folder containing converted HTML files to import.",
    )
    parser.add_argument(
        "--manual-intervention-csv",
        type=Path,
        default=None,
        help="CSV path for pages requiring manual intervention. Defaults to manual_page_intervention.csv inside the resolved input folder.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode.",
    )
    parser.add_argument(
        "--instance-id",
        help="Override INSTANCE_ID from .env.",
    )
    parser.add_argument(
        "--site-url",
        help="Optional website URL used to match a folder inside generated output.",
    )
    return parser.parse_args()


def main() -> None:
    configure_abort_signal_handlers()
    load_environment()
    args = parse_args()

    input_folder = args.input_folder.resolve()

    if not input_folder.exists() or not input_folder.is_dir():
        raise FileNotFoundError(f"Input folder not found or not a directory: {input_folder}")

    expected_site_url = (
        (args.site_url or os.getenv("HELIX_INPUT_SITE_URL") or os.getenv("INPUT_SITE_URL") or "")
        .strip()
    )
    resolved_input_folder = resolve_nested_import_source_folder(
        input_folder,
        expected_site_url=expected_site_url,
    )
    if resolved_input_folder != input_folder:
        logger.info("Using nested import source folder: %s", resolved_input_folder)
    input_folder = resolved_input_folder

    # Place the CSV inside the resolved site output folder unless explicitly provided
    if args.manual_intervention_csv is not None:
        manual_csv = args.manual_intervention_csv.resolve()
    else:
        manual_csv = input_folder / "manual_page_intervention.csv"
    logger.info("Manual intervention CSV: %s", manual_csv)

    username = (os.getenv(WEBBUILDER_USERNAME_ENV) or "").strip()
    password = (os.getenv(WEBBUILDER_PASSWORD_ENV) or "").strip()
    instance_id = (args.instance_id or os.getenv(WEBBUILDER_INSTANCE_ID_ENV) or "").strip()

    if not username or not password:
        raise RuntimeError(
            f"{WEBBUILDER_USERNAME_ENV} and {WEBBUILDER_PASSWORD_ENV} must be set in .env"
        )
    if not instance_id:
        raise RuntimeError(
            f"{WEBBUILDER_INSTANCE_ID_ENV} must be set in .env (or pass --instance-id)"
        )

    import_plan = build_import_plan(input_folder)
    # Homepage is the first item only when is_homepage=True
    if import_plan and import_plan[0].is_homepage:
        homepage = import_plan[0]
        subpages = import_plan[1:]
    else:
        homepage = None
        subpages = import_plan
    body_classes_map = load_body_classes_map(input_folder)

    progress_file = input_folder / IMPORT_PROGRESS_FILE_NAME
    homepage_done, processed_subpage_paths = load_import_progress(progress_file)
    if homepage_done or processed_subpage_paths:
        logger.info(
            "Loaded import progress from %s (homepage_processed=%s, subpages=%d)",
            progress_file,
            "YES" if homepage_done else "NO",
            len(processed_subpage_paths),
        )

    if homepage is not None:
        logger.info("Homepage HTML: %s", homepage.html_file)
        logger.info("Homepage derived title (not entered in UI): %s", homepage.title)
    else:
        logger.warning("Homepage: NOT FOUND — index.html missing; will log manual intervention and proceed with subpages.")
    logger.info("Subpages to import: %d", len(subpages))

    manual_csv.parent.mkdir(parents=True, exist_ok=True)

    success_homepage = False
    success_subpages = 0
    manual_interventions = 0

    # Log manual intervention immediately if homepage is missing
    if homepage is None:
        manual_interventions += 1
        append_manual_intervention_row(
            manual_csv,
            "Homepage",
            input_folder / "index.html",
            "index.html not found in generated output — homepage must be imported manually.",
        )
        logger.warning(
            "Manual intervention logged: homepage index.html not found. "
            "CSV: %s", manual_csv,
        )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=bool(args.headless))
        context = browser.new_context()
        context.grant_permissions(["clipboard-read", "clipboard-write"])
        page = context.new_page()

        try:
            login_to_webbuilder(page, username=username, password=password)
            goto_website_builder(page, instance_id=instance_id)

            if homepage is None:
                success_homepage = False
                logger.info("Skipping homepage import (index.html not found).")
            elif homepage_done:
                success_homepage = True
                logger.info("Skipping homepage import (already processed): %s", homepage.html_file)
            else:
                homepage_html = read_html_file(homepage.html_file)
                homepage_body_class_key = derive_body_class_key_from_html_file(homepage.html_file, input_folder)
                homepage_body_classes = body_classes_map.get(homepage_body_class_key, [])
                click_edit_page(page)
                import_page_html(page, homepage_html, homepage_body_classes)
                success_homepage = True
                homepage_done = True
                save_import_progress(progress_file, homepage_done, processed_subpage_paths)
                logger.info("Homepage import completed from: %s", homepage.html_file)

            for index, item in enumerate(subpages, start=1):
                logger.info("Subpage [%d/%d] %s <- %s", index, len(subpages), item.title, item.html_file)
                rel_subpage = item.html_file.relative_to(input_folder).as_posix()

                if rel_subpage in processed_subpage_paths:
                    logger.info("Skipping subpage already processed: %s", rel_subpage)
                    success_subpages += 1
                    continue

                html_content = read_html_file(item.html_file)
                body_class_key = derive_body_class_key_from_html_file(item.html_file, input_folder)
                item_body_classes = body_classes_map.get(body_class_key, [])

                goto_website_builder(page, instance_id=instance_id)

                created, reason = create_subpage(page, item.title)
                if not created:
                    manual_interventions += 1
                    append_manual_intervention_row(manual_csv, item.title, item.html_file, reason)
                    logger.warning("Manual intervention required for '%s': %s", item.title, reason)
                    try:
                        page.keyboard.press("Escape")
                        page.wait_for_timeout(WEBBUILDER_SHORT_WAIT_MS)
                    except Exception:
                        pass
                    continue

                click_edit_page(page)
                import_page_html(page, html_content, item_body_classes)
                success_subpages += 1
                processed_subpage_paths.add(rel_subpage)
                save_import_progress(progress_file, homepage_done, processed_subpage_paths)

        finally:
            browser.close()

    logger.info("=" * 80)
    logger.info("Import completed.")
    if homepage is None:
        logger.info("Homepage imported: NO (index.html not found — manual intervention required)")
    else:
        logger.info("Homepage imported: %s", "YES" if success_homepage else "NO")
    logger.info("Subpages imported: %d / %d", success_subpages, len(subpages))
    logger.info("Manual interventions: %d", manual_interventions)
    logger.info("Manual CSV path: %s", manual_csv)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        if str(exc).strip() == PROCESS_STOP_MESSAGE:
            logger.error(PROCESS_STOP_MESSAGE)
        else:
            logger.error("Fatal error: %s", exc)
        sys.exit(1)