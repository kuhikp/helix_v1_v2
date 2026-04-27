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
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

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


logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("helix_page_importer")


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


def parent_folder_title(html_file: Path) -> str:
    folder_name = html_file.parent.name.strip()
    if folder_name:
        return folder_name
    return html_file.stem.strip() or "untitled"


def locate_homepage_index(html_files: list[Path], input_folder: Path) -> Path:
    root_index = input_folder / "index.html"
    if root_index in html_files:
        return root_index

    candidate_indexes = [path for path in html_files if path.name.lower() == "index.html"]
    if not candidate_indexes:
        raise RuntimeError("Could not find homepage index.html in the input folder.")

    candidate_indexes.sort(
        key=lambda path: (
            len(path.relative_to(input_folder).parts),
            str(path.relative_to(input_folder)).lower(),
        )
    )
    return candidate_indexes[0]


def build_import_plan(input_folder: Path) -> list[PageImportItem]:
    html_files = collect_html_files(input_folder)
    if not html_files:
        raise RuntimeError(f"No .html/.htm files found under: {input_folder}")

    homepage_file = locate_homepage_index(html_files, input_folder)

    subpages = [path for path in html_files if path != homepage_file]
    subpages.sort(key=lambda path: str(path.relative_to(input_folder)).lower())

    plan: list[PageImportItem] = [
        PageImportItem(
            html_file=homepage_file,
            title=parent_folder_title(homepage_file),
            is_homepage=True,
        )
    ]

    for html_file in subpages:
        plan.append(
            PageImportItem(
                html_file=html_file,
                title=parent_folder_title(html_file),
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


def import_page_html(page, html_content: str) -> None:
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
        default=Path("manual_page_intervention.csv"),
        help="CSV path for pages requiring manual intervention.",
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
    return parser.parse_args()


def main() -> None:
    load_environment()
    args = parse_args()

    input_folder = args.input_folder.resolve()
    manual_csv = args.manual_intervention_csv.resolve()

    if not input_folder.exists() or not input_folder.is_dir():
        raise FileNotFoundError(f"Input folder not found or not a directory: {input_folder}")

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
    homepage = import_plan[0]
    subpages = import_plan[1:]

    logger.info("Homepage HTML: %s", homepage.html_file)
    logger.info("Homepage derived title (not entered in UI): %s", homepage.title)
    logger.info("Subpages to import: %d", len(subpages))

    manual_csv.parent.mkdir(parents=True, exist_ok=True)

    success_homepage = False
    success_subpages = 0
    manual_interventions = 0

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=bool(args.headless))
        context = browser.new_context()
        context.grant_permissions(["clipboard-read", "clipboard-write"])
        page = context.new_page()

        try:
            login_to_webbuilder(page, username=username, password=password)
            goto_website_builder(page, instance_id=instance_id)

            homepage_html = read_html_file(homepage.html_file)
            click_edit_page(page)
            import_page_html(page, homepage_html)
            success_homepage = True
            logger.info("Homepage import completed from: %s", homepage.html_file)

            for index, item in enumerate(subpages, start=1):
                logger.info("Subpage [%d/%d] %s <- %s", index, len(subpages), item.title, item.html_file)
                html_content = read_html_file(item.html_file)

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
                import_page_html(page, html_content)
                success_subpages += 1

        finally:
            browser.close()

    logger.info("=" * 80)
    logger.info("Import completed.")
    logger.info("Homepage imported: %s", "YES" if success_homepage else "NO")
    logger.info("Subpages imported: %d / %d", success_subpages, len(subpages))
    logger.info("Manual interventions: %d", manual_interventions)
    logger.info("Manual CSV path: %s", manual_csv)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logger.error("Fatal error: %s", exc)
        sys.exit(1)