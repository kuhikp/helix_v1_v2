#!/usr/bin/env python3
"""
fetch_site_settings.py - Smart Site Settings Extractor
Extracts site settings from locally mirrored HTML files following
field-by-field rules defined in the specification comments.
Outputs: site_settings.json in WebBuilder-compatible format.
"""

import os
import re
import json
import copy
import glob
from urllib.parse import urlparse

from bs4 import BeautifulSoup

# ──────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────
SITE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "site_manager", "static", "httrack_export")
OUTPUT_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Webbuilder_extracted_settings", "site_config_export.json")


# Load .env if present
ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
env_vars = {}
if os.path.isfile(ENV_FILE):
    with open(ENV_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip().strip("'\"")

EDISON_SITE_ID = env_vars.get("EDISON_SITE_ID", "")
V2_SITE_ID = env_vars.get("V2_SITE_ID", EDISON_SITE_ID)


# ──────────────────────────────────────────────────────────────
# Template — WebBuilder format
# All rows preserved exactly as provided. Values will be filled.
# ──────────────────────────────────────────────────────────────
TEMPLATE = [
    # ── optional-and-head-features ──
    {"Panel Type": "left-sidebar-settings--optional-and-head-features", "Field Label": "", "Field Name": "_token", "Type": "hidden", "Default Value": ""},
    {"Panel Type": "left-sidebar-settings--optional-and-head-features", "Field Label": "", "Field Name": "", "Type": "text", "Default Value": ""},
    {"Panel Type": "left-sidebar-settings--optional-and-head-features", "Field Label": "", "Field Name": "repository", "Type": "text", "Default Value": ""},
    {"Panel Type": "left-sidebar-settings--optional-and-head-features", "Field Label": "Enable promotional settings", "Field Name": "promotional", "Type": "checkbox", "Default Value": "unchecked"},
    {"Panel Type": "left-sidebar-settings--optional-and-head-features", "Field Label": "Enable Default Canvas Blocks", "Field Name": "defaultCanvasBlocks", "Type": "checkbox", "Default Value": "checked"},
    {"Panel Type": "left-sidebar-settings--optional-and-head-features", "Field Label": "Enable iCreator", "Field Name": "icreator", "Type": "checkbox", "Default Value": "unchecked"},
    {"Panel Type": "left-sidebar-settings--optional-and-head-features", "Field Label": "Enable GRV", "Field Name": "enable-grv", "Type": "checkbox", "Default Value": "unchecked"},
    {"Panel Type": "left-sidebar-settings--optional-and-head-features", "Field Label": "Lock Drag by Default", "Field Name": "lockDragByDefault", "Type": "checkbox", "Default Value": "unchecked"},
    {"Panel Type": "left-sidebar-settings--optional-and-head-features", "Field Label": "Enable Tooltips", "Field Name": "tooltipsEnabled", "Type": "checkbox", "Default Value": "unchecked"},
    {"Panel Type": "left-sidebar-settings--optional-and-head-features", "Field Label": "Enable using modular version of javascript scripts", "Field Name": "selectiveModularScriptEnabled", "Type": "checkbox", "Default Value": "unchecked"},
    {"Panel Type": "left-sidebar-settings--optional-and-head-features", "Field Label": "Include default viewport on website", "Field Name": "viewport", "Type": "checkbox", "Default Value": "checked"},
    {"Panel Type": "left-sidebar-settings--optional-and-head-features", "Field Label": "Include Cross Origin Referrer Tag", "Field Name": "referrer", "Type": "checkbox", "Default Value": "unchecked"},
    {"Panel Type": "left-sidebar-settings--optional-and-head-features", "Field Label": "Auto add Site Title to title tags", "Field Name": "includeTitle", "Type": "checkbox", "Default Value": "unchecked"},
    {"Panel Type": "left-sidebar-settings--optional-and-head-features", "Field Label": "No Snippet Beta", "Field Name": "nosnippet", "Type": "checkbox", "Default Value": "unchecked"},
    {"Panel Type": "left-sidebar-settings--optional-and-head-features", "Field Label": "Enable RTL support", "Field Name": "enableRtlSupport", "Type": "checkbox", "Default Value": "unchecked"},
    {"Panel Type": "left-sidebar-settings--optional-and-head-features", "Field Label": "Enable Preconnect Tags", "Field Name": "enablePreconnectTags", "Type": "checkbox", "Default Value": "unchecked"},
    {"Panel Type": "left-sidebar-settings--optional-and-head-features", "Field Label": "Enable Search", "Field Name": "search", "Type": "checkbox", "Default Value": "unchecked"},
    {"Panel Type": "left-sidebar-settings--optional-and-head-features", "Field Label": "Enable Forms", "Field Name": "helixForms", "Type": "checkbox", "Default Value": "unchecked"},
    {"Panel Type": "left-sidebar-settings--optional-and-head-features", "Field Label": "Disable router automation during MTP", "Field Name": "disableRouterAutomation", "Type": "checkbox", "Default Value": "unchecked"},
    {"Panel Type": "left-sidebar-settings--optional-and-head-features", "Field Label": "Dynamic Pages", "Field Name": "dynamicPages", "Type": "checkbox", "Default Value": "unchecked"},
    {"Panel Type": "left-sidebar-settings--optional-and-head-features", "Field Label": "Enable API Integration", "Field Name": "apiIntegration", "Type": "checkbox", "Default Value": "unchecked"},
    {"Panel Type": "left-sidebar-settings--optional-and-head-features", "Field Label": "Remove special characters from page slugs", "Field Name": "removeSpecialCharsFromSlugs", "Type": "checkbox", "Default Value": "unchecked"},
    {"Panel Type": "left-sidebar-settings--optional-and-head-features", "Field Label": "Auto create redirect during page changes", "Field Name": "autoCreateRedirect", "Type": "checkbox", "Default Value": "checked"},
    {"Panel Type": "left-sidebar-settings--optional-and-head-features", "Field Label": "Select Rich Text Editor Beta", "Field Name": "loginPage", "Type": "custom_multiselect_single", "Default Value": "CKEditor 5"},
    {"Panel Type": "left-sidebar-settings--optional-and-head-features", "Field Label": "When Brandkit variables are defined on a page level:", "Field Name": "loginPage", "Type": "custom_multiselect_single", "Default Value": "Attach Global Brandkit variables after page-level"},

    # # -- multilingual --
    # {"Panel Type": "left-sidebar-settings--multilingual-manager", "Field Label": "Enable multilingual", "Field Name": "enable_multilingual", "Type": "checkbox", "Default Value": "unchecked"},
    
    # # ── performance ──
    {"Panel Type": "left-sidebar-settings--performance", "Field Label": "", "Field Name": "_token", "Type": "hidden", "Default Value": ""},
    {"Panel Type": "left-sidebar-settings--performance", "Field Label": "Enable PSI performance options", "Field Name": "renderCriticalContentFirst", "Type": "checkbox", "Default Value": "unchecked"},
    {"Panel Type": "left-sidebar-settings--performance", "Field Label": "Minify all included CSS files", "Field Name": "renderCriticalContentFirst", "Type": "checkbox", "Default Value": "checked"},
    {"Panel Type": "left-sidebar-settings--performance", "Field Label": "Minify all included JS files", "Field Name": "renderCriticalContentFirst", "Type": "checkbox", "Default Value": "checked"},
    {"Panel Type": "left-sidebar-settings--performance", "Field Label": "Lazy-load all images", "Field Name": "renderCriticalContentFirst", "Type": "checkbox", "Default Value": "unchecked"},
    {"Panel Type": "left-sidebar-settings--performance", "Field Label": "Defer loading website JS", "Field Name": "renderCriticalContentFirst", "Type": "checkbox", "Default Value": "unchecked"},
    {"Panel Type": "left-sidebar-settings--performance", "Field Label": "Enable Fast Deployments", "Field Name": "renderCriticalContentFirst", "Type": "checkbox", "Default Value": "checked"},

    # # -- developer settings --
    {"Panel Type": "left-sidebar-settings--developer", "Field Label": "Allow Edison Previews", "Field Name": "allow_edison_previews", "Type": "checkbox", "Default Value": "checked"},

    # # ── seo ──
    {"Panel Type": "left-sidebar-settings--seo", "Field Label": "", "Field Name": "_token", "Type": "hidden", "Default Value": ""},
    {"Panel Type": "left-sidebar-settings--seo", "Field Label": "", "Field Name": "", "Type": "text", "Default Value": ""},
    {"Panel Type": "left-sidebar-settings--seo", "Field Label": "", "Field Name": "repository", "Type": "text", "Default Value": ""},
    {"Panel Type": "left-sidebar-settings--seo", "Field Label": "", "Field Name": "title", "Type": "text", "Default Value": ""},
    {"Panel Type": "left-sidebar-settings--seo", "Field Label": "Website level GCMA number *", "Field Name": "gcma_metadata_document_number", "Type": "text", "Default Value": ""},
    {"Panel Type": "left-sidebar-settings--seo", "Field Label": "", "Field Name": "lexicon_brands[]", "Type": "text", "Default Value": ""},
    {"Panel Type": "left-sidebar-settings--seo", "Field Label": "", "Field Name": "brands[]", "Type": "text", "Default Value": ""},
    {"Panel Type": "left-sidebar-settings--seo", "Field Label": "", "Field Name": "site_description", "Type": "textarea", "Default Value": ""},
    {"Panel Type": "left-sidebar-settings--seo", "Field Label": "", "Field Name": "site_keywords", "Type": "textarea", "Default Value": ""},
    {"Panel Type": "left-sidebar-settings--seo", "Field Label": "Currency", "Field Name": "currency", "Type": "select", "Default Value": ""},
    {"Panel Type": "left-sidebar-settings--seo", "Field Label": "Customer Type *", "Field Name": "audiences", "Type": "select", "Default Value": ""},
    {"Panel Type": "left-sidebar-settings--seo", "Field Label": "", "Field Name": "audience_specialties[]", "Type": "text", "Default Value": ""},
    {"Panel Type": "left-sidebar-settings--seo", "Field Label": "", "Field Name": "lexicon_therapeutic_areas[]", "Type": "text", "Default Value": ""},
    {"Panel Type": "left-sidebar-settings--seo", "Field Label": "", "Field Name": "lexicon_indications[]", "Type": "text", "Default Value": ""},
    {"Panel Type": "left-sidebar-settings--seo", "Field Label": "Business Unit *", "Field Name": "lexicon_business_unit", "Type": "select", "Default Value": ""},
    {"Panel Type": "left-sidebar-settings--seo", "Field Label": "", "Field Name": "lexicon_brands[]", "Type": "custom_multiselect", "Default Value": ""},
    {"Panel Type": "left-sidebar-settings--seo", "Field Label": "", "Field Name": "brands[]", "Type": "custom_multiselect", "Default Value": ""},
    {"Panel Type": "left-sidebar-settings--seo", "Field Label": "", "Field Name": "audience_specialties[]", "Type": "custom_multiselect", "Default Value": ""},
    {"Panel Type": "left-sidebar-settings--seo", "Field Label": "", "Field Name": "lexicon_therapeutic_areas[]", "Type": "custom_multiselect", "Default Value": ""},
    {"Panel Type": "left-sidebar-settings--seo", "Field Label": "", "Field Name": "lexicon_indications[]", "Type": "custom_multiselect", "Default Value": ""},


    # # ── external-link-manager ──
    {"Panel Type": "left-sidebar-settings--external-link-manager", "Field Label": "Enabled?", "Field Name": "enabled", "Type": "checkbox", "Default Value": "unchecked"},

    # # ── promotional-popup-manager ──
    {"Panel Type": "left-sidebar-settings--promotional-popup-manager", "Field Label": "Enabled?", "Field Name": "enabled", "Type": "checkbox", "Default Value": "unchecked"},

    # # ── analytics ──
    {"Panel Type": "left-sidebar-settings--analytics", "Field Label": "Check here if you use Adobe analytics on your site", "Field Name": "enable-analytics", "Type": "checkbox", "Default Value": "unchecked"},
    {"Panel Type": "left-sidebar-settings--analytics", "Field Label": "Check here if you use \"Adobe Target\"", "Field Name": "adobe-target", "Type": "checkbox", "Default Value": "unchecked"},
    {"Panel Type": "left-sidebar-settings--analytics", "Field Label": "Adobe Analytics Library", "Field Name": "select", "Type": "select", "Default Value": ""},
    {"Panel Type": "left-sidebar-settings--analytics", "Field Label": "URL for production Adobe Launch Script", "Field Name": "prod-url", "Type": "url"},
    {"Panel Type": "left-sidebar-settings--analytics", "Field Label": "Check here if you use GTM on your site", "Field Name": "enable-gtm", "Type": "checkbox", "Default Value": "unchecked"},
    {"Panel Type": "left-sidebar-settings--analytics", "Field Label": "", "Field Name": "prod-gtm-url", "Type": "text", "Default Value": ""},

    # # # ── bootstrap ──
    {"Panel Type": "left-sidebar-settings--bootstrap", "Field Label": "Version", "Field Name": "bootstrap", "Type": "select", "Default Value": "No Bootstrap"},


    # ── main ──
    {"Panel Type": "left-sidebar-settings--main", "Field Label": "", "Field Name": "repository", "Type": "text", "Default Value": ""},
    {"Panel Type": "left-sidebar-settings--main", "Field Label": "Site Name", "Field Name": "site_name", "Type": "text", "Default Value": ""},
    {"Panel Type": "left-sidebar-settings--main", "Field Label": "Domain", "Field Name": "domain", "Type": "text", "Default Value": ""},
    {"Panel Type": "left-sidebar-settings--main", "Field Label": "Brand", "Field Name": "brand", "Type": "text", "Default Value": ""},
    {"Panel Type": "left-sidebar-settings--main", "Field Label": "Country", "Field Name": "country", "Type": "text", "Default Value": ""},
    {"Panel Type": "left-sidebar-settings--main", "Field Label": "Teams", "Field Name": "teams", "Type": "text", "Default Value": ""},
    {"Panel Type": "left-sidebar-settings--main", "Field Label": "Helix Components Version", "Field Name": "helix_components_version", "Type": "text", "Default Value": ""},

    # # -- left-sidebar-settings--website --
    {"Panel Type": "left-sidebar-settings--website", "Field Label": "Site Type", "Field Name": "site_type", "Type": "select", "Default Value": "Website"},
    {"Panel Type": "left-sidebar-settings--website", "Field Label": "Edison Lite Site ID", "Field Name": "repository", "Type": "text", "Default Value": "   "},




    # # ── data-source ──
    # {"Panel Type": "left-sidebar-settings--data-source", "Field Label": "", "Field Name": "_token", "Type": "hidden"},
    # {"Panel Type": "left-sidebar-settings--data-source", "Field Label": "", "Field Name": "", "Type": "text"},
    # {"Panel Type": "left-sidebar-settings--data-source", "Field Label": "", "Field Name": "repository", "Type": "text"},
    # {"Panel Type": "left-sidebar-settings--data-source", "Field Label": "Pfizer.com (https://pfrsvuncoveredcom-test.dev.pfizerstatic.io/files/signup-config.json)", "Field Name": "", "Type": "checkbox"},
    # {"Panel Type": "left-sidebar-settings--data-source", "Field Label": "Test (https://4473704.livepreview.pfizer/files/importer.json)", "Field Name": "", "Type": "checkbox"},
    # {"Panel Type": "left-sidebar-settings--data-source", "Field Label": "Hub (https://5223708.livepreview.pfizer/files/hub.json)", "Field Name": "", "Type": "checkbox"},
    # {"Panel Type": "left-sidebar-settings--data-source", "Field Label": "CDP Hub Sample (https://paxlvdpatientsthemespfizer-preview.dev.pfizerstatic.io/files/data-source.json)", "Field Name": "", "Type": "checkbox"},
    # {"Panel Type": "left-sidebar-settings--data-source", "Field Label": "Test EO Json (https://testdatasource.s3.amazonaws.com/resources.json)", "Field Name": "", "Type": "checkbox"},
    # {"Panel Type": "left-sidebar-settings--data-source", "Field Label": "Test EO Json 2 (https://cdn.pfizer.com/webbuilder/demo_endpoint/resources.json)", "Field Name": "", "Type": "checkbox"},
    # {"Panel Type": "left-sidebar-settings--data-source", "Field Label": "Test EO Json 3 (https://canwebqa04pfizercom-preview.dev.pfizerstatic.io/files/resources.json)", "Field Name": "", "Type": "checkbox"},
    # {"Panel Type": "left-sidebar-settings--data-source", "Field Label": "WB Example Data Source (https://cdn.pfizer.com/webbuilder/demo_endpoint/resources.json)", "Field Name": "", "Type": "checkbox"},
    # {"Panel Type": "left-sidebar-settings--data-source", "Field Label": "Press Releases Listing (https://pfecpfizercomus-dev.pfizersite.io/v1/api/hub/listing/press-release.json)", "Field Name": "", "Type": "checkbox"},
    # {"Panel Type": "left-sidebar-settings--data-source", "Field Label": "Articles Listing (https://pfecpfizercomus-dev.pfizersite.io/v1/api/hub/listing/articles.json)", "Field Name": "", "Type": "checkbox"},
    # {"Panel Type": "left-sidebar-settings--data-source", "Field Label": "Article Listing (https://pfecpfizercomus-dev.pfizersite.io/v1/api/hub/listing/articles.json)", "Field Name": "", "Type": "checkbox"},
    # {"Panel Type": "left-sidebar-settings--data-source", "Field Label": "CDP Article Listing (https://pfecpfizercomus-dev.pfizersite.io/v1/api/hub/featured_stories/listing.json)", "Field Name": "", "Type": "checkbox"},
    # {"Panel Type": "left-sidebar-settings--data-source", "Field Label": "CDP Press Releases Listing (https://pfecpfizercomus-dev.pfizersite.io/v1/api/hub/press_release/listing.json)", "Field Name": "", "Type": "checkbox"},
    # {"Panel Type": "left-sidebar-settings--data-source", "Field Label": "CDP Careers (https://pfecpfizercomus-dev.pfizersite.io/v1/api/hub/listing/career.json)", "Field Name": "", "Type": "checkbox"},
    # {"Panel Type": "left-sidebar-settings--data-source", "Field Label": "CDP Landing Page Listing (https://pfecpfizercomus-dev.pfizersite.io/v1/api/hub/landing_page_layout_builder/listing.json)", "Field Name": "", "Type": "checkbox"},
    # {"Panel Type": "left-sidebar-settings--data-source", "Field Label": "Article Listing - Stage (https://pfecpfizercomus-stage.pfizersite.io/v1/api/hub/featured_stories/listing.json)", "Field Name": "", "Type": "checkbox"},
    # {"Panel Type": "left-sidebar-settings--data-source", "Field Label": "Press Releases - Stage (https://pfecpfizercomus-stage.pfizersite.io/v1/api/hub/press_release/listing.json)", "Field Name": "", "Type": "checkbox"},
    # {"Panel Type": "left-sidebar-settings--data-source", "Field Label": "Landing Page Listing - stage (https://pfecpfizercomus-stage.pfizersite.io/v1/api/hub/landing_page_layout_builder/listing.json)", "Field Name": "", "Type": "checkbox"},
    # {"Panel Type": "left-sidebar-settings--data-source", "Field Label": "Careers - Stage (https://pfecpfizercomus-stage.pfizersite.io/v1/api/hub/listing/career.json)", "Field Name": "", "Type": "checkbox"},
    # {"Panel Type": "left-sidebar-settings--data-source", "Field Label": "Article Listing - PROD (https://pfecpfizercomus.pfizersite.io/v1/api/hub/featured_stories/listing.json)", "Field Name": "", "Type": "checkbox"},
    # {"Panel Type": "left-sidebar-settings--data-source", "Field Label": "Press Releases - PROD (https://pfecpfizercomus.pfizersite.io/v1/api/hub/press_release/listing.json)", "Field Name": "", "Type": "checkbox"},
    # {"Panel Type": "left-sidebar-settings--data-source", "Field Label": "Landing Page Listing - Prod (https://pfecpfizercomus.pfizersite.io/v1/api/hub/landing_page_layout_builder/listing.json)", "Field Name": "", "Type": "checkbox"},
    # {"Panel Type": "left-sidebar-settings--data-source", "Field Label": "Careers - PROD (https://pfecpfizercomus.pfizersite.io/v1/api/hub/listing/career.json)", "Field Name": "", "Type": "checkbox"},
    # {"Panel Type": "left-sidebar-settings--data-source", "Field Label": "Landing Page Listing - 1665 [Careers Demo] (https://uat.pfizer.com:1665/v1/api/hub/landing_page_layout_builder/listing.json)", "Field Name": "", "Type": "checkbox"},
    # {"Panel Type": "left-sidebar-settings--data-source", "Field Label": "CDP Careers - zn553346dev (https://pfecpfizercomus-zn553346dev.pfizersite.io/v1/api/hub/listing/career.json)", "Field Name": "", "Type": "checkbox"},
    # {"Panel Type": "left-sidebar-settings--data-source", "Field Label": "KT Calll Demo (https://testdatasource.s3.amazonaws.com/resources.json)", "Field Name": "", "Type": "checkbox"},
    # {"Panel Type": "left-sidebar-settings--data-source", "Field Label": "Landing Page Listing - Env4 (https://pfecpfizercomus-env4.pfizersite.io/v1/api/hub/landing_page_layout_builder/listing.json)", "Field Name": "", "Type": "checkbox"},
    # {"Panel Type": "left-sidebar-settings--data-source", "Field Label": "Press Releases - Env4 (https://pfecpfizercomus-env4.pfizersite.io/v1/api/hub/press_release/listing.json)", "Field Name": "", "Type": "checkbox"},
    # {"Panel Type": "left-sidebar-settings--data-source", "Field Label": "Article Listing - Env4 (https://pfecpfizercomus-env4.pfizersite.io/v1/api/hub/featured_stories/listing.json)", "Field Name": "", "Type": "checkbox"},
    # {"Panel Type": "left-sidebar-settings--data-source", "Field Label": "Careers - Env4 (https://pfecpfizercomus-env4.pfizersite.io/v1/api/hub/listing/career.json)", "Field Name": "", "Type": "checkbox"},
]



# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────
def collect_html_files(site_dir):
    """Collect all HTML files in the site directory."""
    patterns = ["*.html", "**/*.html"]
    files = []
    for pat in patterns:
        files.extend(glob.glob(os.path.join(site_dir, pat), recursive=True))
    return sorted(set(files))


def parse_html(filepath):
    """Parse an HTML file and return BeautifulSoup object and raw content."""
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    soup = BeautifulSoup(content, "lxml")
    return soup, content


def get_drupal_settings(soup):
    """Extract Drupal settings JSON from the page."""
    script = soup.find("script", {"data-drupal-selector": "drupal-settings-json"})
    if script and script.string:
        try:
            return json.loads(script.string)
        except json.JSONDecodeError:
            pass
    return {}


def get_domain_from_sitemap(site_dir):
    """Extract domain from sitemap.xml."""
    sitemap = os.path.join(site_dir, "sitemap.xml")
    if os.path.isfile(sitemap):
        with open(sitemap, "r", encoding="utf-8") as f:
            content = f.read()
        soup = BeautifulSoup(content, "lxml-xml")
        loc = soup.find("loc")
        if loc:
            parsed = urlparse(loc.text.strip())
            return parsed.netloc
    return ""


# ──────────────────────────────────────────────────────────────
# Main extraction logic
# ──────────────────────────────────────────────────────────────
def extract_values(site_dir):
    """
    Scan local HTML files and return a dict of extracted values.
    Keys use (Panel Type, Field Label) for fields where Field Name
    is shared (e.g. performance) and (Panel Type, Field Name) otherwise.
    """
    html_files = collect_html_files(site_dir)
    print(f"Found {len(html_files)} HTML files")

    main_html = os.path.join(site_dir, "index.html")
    home_html = os.path.join(site_dir, "home", "index.html")
    primary = home_html if os.path.isfile(home_html) else main_html
    soup, raw_content = parse_html(primary)
    drupal_settings = get_drupal_settings(soup)
    grv_config = drupal_settings.get("grv_nextgen", {})

    # Parse ALL pages for aggregate checks
    all_contents = []
    all_soups = []
    for f in html_files:
        try:
            s, c = parse_html(f)
            all_soups.append((f, s))
            all_contents.append((f, c))
        except Exception:
            pass

    # ── Extract all needed values ──

    # Domain
    domain = get_domain_from_sitemap(site_dir)
    if not domain:
        m = re.search(r"origin=https?%3A//([^/&]+)", raw_content)
        if m:
            domain = m.group(1)

    # Language
    html_tag = soup.find("html")
    language = html_tag.get("lang", "") if html_tag else ""

    # Site name from <title>
    site_name = ""
    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        parts = title_tag.string.strip().split("|")
        site_name = parts[-1].strip() if len(parts) > 1 else parts[0].strip()

    # GCMA
    gcma = ""
    gcma_match = re.search(r"GCMA\s+([\w\-]+)", raw_content)
    if gcma_match:
        gcma = gcma_match.group(1)

    # Description
    description = ""
    desc_meta = soup.find("meta", attrs={"name": "description"})
    if desc_meta:
        description = desc_meta.get("content", "")
    if not description:
        og_desc = soup.find("meta", attrs={"property": "og:description"})
        if og_desc:
            description = og_desc.get("content", "")

    # Country from language
    lang_country_map = {
        "pt-br": "Brazil", "en-us": "United States", "en-gb": "United Kingdom",
        "es": "Spain", "es-mx": "Mexico", "fr": "France", "de": "Germany",
        "it": "Italy", "ja": "Japan", "ko": "Korea", "zh-cn": "China",
        "zh-tw": "Taiwan", "ar": "Saudi Arabia", "tr": "Turkey",
        "ru": "Russia", "pl": "Poland", "nl": "Netherlands", "hu": "Hungary",
    }
    country = lang_country_map.get(language.lower(), "") if language else ""

    # Country code (2-letter ISO from language tag)
    country_code = ""
    if language:
        parts = language.lower().split("-")
        if len(parts) >= 2:
            country_code = parts[-1].upper()   # e.g. "pt-br" → "BR"
        elif len(parts) == 1 and len(parts[0]) == 2:
            country_code = parts[0].upper()

    # Brand from GCMA code  (PP-UNP-BRA-0534 → "UNP")
    # need to fix the brand fetch from DMP
    brand = ""
    if gcma:
        gcma_parts = gcma.split("-")
        if len(gcma_parts) >= 2:
            brand = gcma_parts[1]              # second segment is brand code

    # Teams — not present in static HTML; leave empty
    teams = ""

    # Helix Components Version — try <meta name="Generator"> first
    helix_components_version = ""
    gen_meta = soup.find("meta", attrs={"name": re.compile(r"generator", re.I)})
    if gen_meta:
        helix_components_version = gen_meta.get("content", "")
    # Fallback: search all pages for a generator tag
    if not helix_components_version:
        for _, s in all_soups:
            g = s.find("meta", attrs={"name": re.compile(r"generator", re.I)})
            if g:
                helix_components_version = g.get("content", "")
                break

    # Adobe Analytics
    adobe_enabled = "unchecked"
    adobe_launch_url = ""
    for script in soup.find_all("script", src=True):
        src = script.get("src", "")
        if "adobedtm.com" in src:
            adobe_enabled = "checked"
            adobe_launch_url = src
            break

    adobe_staging_url = ""
    for _, c in all_contents:
        matches = re.findall(r'https?://assets\.adobedtm\.com/[^\s"\'<>]+', c)
        for m in matches:
            if "staging" in m.lower() or "development" in m.lower():
                if not adobe_staging_url:
                    adobe_staging_url = m
            elif not adobe_launch_url:
                adobe_launch_url = m

    # GTM
    gtm_enabled = "unchecked"
    gtm_prod_id = ""
    for _, c in all_contents:
        if "googletagmanager.com/gtm.js" in c or "googletagmanager.com/ns.html" in c:
            gtm_enabled = "checked"
            m = re.search(r"GTM-[\w]+", c)
            if m:
                gtm_prod_id = m.group(0)
            break

    # Enable GRV
    enable_grv = "unchecked"
    for _, c in all_contents:
        if "pfizer_grv_nextgen_sso_url" in c:
            enable_grv = "checked"
            break

    # Enable Tooltips
    enable_tooltips = "unchecked"
    for _, c in all_contents:
        if "data-tooltip-data" in c:
            enable_tooltips = "checked"
            break

    # Cross Origin Referrer
    enable_referrer = "unchecked"
    for _, c in all_contents:
        if 'name="referrer"' in c and "origin-when-cross-origin" in c:
            enable_referrer = "checked"
            break

    # Viewport
    has_viewport = "unchecked"
    if soup.find("meta", attrs={"name": "viewport"}):
        has_viewport = "checked"

    # RTL
    enable_rtl = "unchecked"
    if html_tag and html_tag.get("dir", "").lower() == "rtl":
        enable_rtl = "checked"

    # Preconnect
    preconnect_links = []
    for link in soup.find_all("link", rel="preconnect"):
        href = link.get("href", "")
        if href and href not in preconnect_links:
            preconnect_links.append(href)
    enable_preconnect = "checked" if preconnect_links else "unchecked"

    #modify for search, check if search page exists or if any link contains "search"
    # Search
    enable_search = "unchecked"
    # search_html = os.path.join(site_dir, "search", "index.html")
    # if os.path.isfile(search_html):
    #     enable_search = "checked"
    # else:
    #     for _, c in all_contents:
    #         if re.search(r'href=["\'][^"\']*search[^"\']*["\']', c, re.IGNORECASE):
    #             enable_search = "checked"
    #             break

    # Forms
    enable_forms = "unchecked"
    for _, s in all_soups:
        for form in s.find_all("form"):
            cls = " ".join(form.get("class", []))
            if "antibot" not in cls:
                enable_forms = "checked"
                break
        if enable_forms == "checked":
            break

    # Remove special chars (non-English)
    remove_special_chars = "unchecked"
    # if language and not language.lower().startswith("en"):
    #     remove_special_chars = "checked"

    # Lazy-load
    lazy_load = "unchecked"
    for _, c in all_contents:
        if 'loading="lazy"' in c or "loading='lazy'" in c:
            lazy_load = "checked"
            break

    # External link manager — check if leaving-site / external link modal exists
    external_link_enabled = "unchecked"
    for _, c in all_contents:
        if "_blank" in c.lower():
            external_link_enabled = "checked"
            break

    # ── Build the value lookup ──
    # Uses (Panel Type, Field Name) as primary key, falls back to (Panel Type, Field Label)
    values = {}

    # --- analytics ---
    values[("left-sidebar-settings--analytics", "enable-analytics", "")] = adobe_enabled
    values[("left-sidebar-settings--analytics", "adobe-target", "")] = "unchecked"
    values[("left-sidebar-settings--analytics", "select", "")] = "AppMeasurement" if adobe_enabled == "checked" else ""
    values[("left-sidebar-settings--analytics", "non-prod-url", "")] = adobe_staging_url
    values[("left-sidebar-settings--analytics", "prod-url", "")] = adobe_launch_url
    values[("left-sidebar-settings--analytics", "enable-gtm", "")] = gtm_enabled
    values[("left-sidebar-settings--analytics", "non-prod-gtm-url", "")] = ""
    values[("left-sidebar-settings--analytics", "prod-gtm-url", "")] = gtm_prod_id

    # -- developer settings --
    values[("left-sidebar-settings--developer", "allow_edison_previews", "")] = "checked"

    # --- bootstrap ---
    values[("left-sidebar-settings--bootstrap", "bootstrap", "")] = "none"

    # --- main ---
    MAIN = "left-sidebar-settings--main"
    values[(MAIN, "site_name", "")] = site_name
    # values[(MAIN, "site_type", "")] = "Website"
    values[(MAIN, "domain", "")] = domain
    values[(MAIN, "brand", "")] = brand
    values[(MAIN, "country", "")] = country_code if country_code else country
    values[(MAIN, "teams", "")] = teams
    values[(MAIN, "helix_components_version", "")] = helix_components_version
    values[(MAIN, "site_", "")] = helix_components_version

    # --- data-source (all unchecked) ---
    # No specific lookup — all data-source checkboxes default to "unchecked"

    # --- external-link-manager ---
    values[("left-sidebar-settings--external-link-manager", "enabled", "Enabled?")] = external_link_enabled

    # --- optional-and-head-features ---
    OPT = "left-sidebar-settings--optional-and-head-features"
    values[(OPT, "promotional", "")] = "unchecked"
    values[(OPT, "defaultCanvasBlocks", "")] = "checked"
    values[(OPT, "icreator", "")] = "unchecked"
    values[(OPT, "enable-grv", "")] = enable_grv
    values[(OPT, "lockDragByDefault", "")] = "unchecked"
    values[(OPT, "tooltipsEnabled", "")] = enable_tooltips
    values[(OPT, "selectiveModularScriptEnabled", "")] = "unchecked"
    values[(OPT, "viewport", "")] = has_viewport
    values[(OPT, "referrer", "")] = enable_referrer
    values[(OPT, "includeTitle", "")] = "unchecked"
    values[(OPT, "nosnippet", "")] = "unchecked"
    values[(OPT, "enableRtlSupport", "")] = enable_rtl
    values[(OPT, "enablePreconnectTags", "")] = enable_preconnect
    values[(OPT, "search", "")] = enable_search
    values[(OPT, "helixForms", "")] = enable_forms
    values[(OPT, "disableRouterAutomation", "")] = "unchecked"
    values[(OPT, "dynamicPages", "")] = "unchecked"
    values[(OPT, "apiIntegration", "")] = "unchecked"
    values[(OPT, "removeSpecialCharsFromSlugs", "")] = remove_special_chars
    values[(OPT, "autoCreateRedirect", "")] = "checked"
    # custom_multiselect_single — match by Field Label since Field Name is shared
    values[(OPT, "", "Select Rich Text Editor Beta")] = "CKEditor 5"
    values[(OPT, "", "When Brandkit variables are defined on a page level:")] = "Attach Global Brandkit variables after page-level"

    # --- performance --- (all share Field Name, so match by Field Label)
    PERF = "left-sidebar-settings--performance"
    values[(PERF, "", "Enable PSI performance options")] = "unchecked"
    values[(PERF, "", "Minify all included CSS files")] = "checked"
    values[(PERF, "", "Minify all included JS files")] = "checked"
    values[(PERF, "", "Lazy-load all images")] = lazy_load
    values[(PERF, "", "Defer loading website JS")] = "unchecked"
    values[(PERF, "", "Enable Fast Deployments")] = "checked"

    # --- promotional-popup-manager ---
    values[("left-sidebar-settings--promotional-popup-manager", "enabled", "Enabled?")] = "unchecked"

    # --- seo ---
    SEO = "left-sidebar-settings--seo"
    values[(SEO, "title", "")] = site_name
    values[(SEO, "gcma_metadata_document_number", "")] = gcma
    values[(SEO, "site_description", "")] = description
    values[(SEO, "site_keywords", "")] = ""
    values[(SEO, "country", "")] = country
    values[(SEO, "currency", "")] = ""
    values[(SEO, "audiences", "")] = ""
    values[(SEO, "lexicon_business_unit", "")] = ""

    # -- website --
    # custom_multiselect_single — match by Field Label since Field Name is shared
    WEB = "left-sidebar-settings--website"
    values[(WEB, "", "Site Type")] = "Website"
    values[(WEB, "repository", "")] = "   "  # 3 spaces to trigger "value provided but empty" warning in WebBuilder

    # Print summary of detected values
    print(f"\nExtracted values from HTML:")
    print(f"  Domain:         {domain}")
    print(f"  Site Name:      {site_name}")
    print(f"  Language:       {language}")
    print(f"  Country:        {country}")
    print(f"  Country Code:   {country_code}")
    print(f"  Brand:          {brand}")
    print(f"  Teams:          {teams or '(empty)'}")
    print(f"  Helix Version:  {helix_components_version}")
    print(f"  GCMA:           {gcma}")
    print(f"  Adobe Launch:   {adobe_launch_url[:60]}..." if len(adobe_launch_url) > 60 else f"  Adobe Launch:   {adobe_launch_url}")
    print(f"  Adobe Enabled:  {adobe_enabled}")
    print(f"  GTM Enabled:    {gtm_enabled}")
    print(f"  Enable GRV:     {enable_grv}")
    print(f"  Viewport:       {has_viewport}")
    print(f"  RTL:            {enable_rtl}")
    print(f"  Preconnect:     {enable_preconnect} ({len(preconnect_links)} links)")
    print(f"  Search:         {enable_search}")
    print(f"  Forms:          {enable_forms}")
    print(f"  Ext Link Mgr:   {external_link_enabled}")
    print(f"  Lazy-load:      {lazy_load}")
    print(f"  Special Chars:  {remove_special_chars}")

    return values


def build_output(values, v2_site_id):
    """
    Walk the TEMPLATE, fill in Value from extracted values, return
    the final list in WebBuilder format.
    """
    output = []

    for entry in TEMPLATE:
        row = copy.deepcopy(entry)
        panel = row["Panel Type"]
        fname = row["Field Name"]
        flabel = row["Field Label"]
        ftype = row["Type"]

        val = None

        # Strategy 1: Exact match by (Panel, FieldName, "")
        if fname:
            val = values.get((panel, fname, ""))

        # Strategy 2: Match by (Panel, FieldName, FieldLabel) — for shared Field Names
        if val is None and fname and flabel:
            val = values.get((panel, fname, flabel))

        # Strategy 3: Match by (Panel, "", FieldLabel) — performance/multiselect fields
        if val is None and flabel:
            val = values.get((panel, "", flabel))

        # Strategy 4: Defaults for unmatched fields
        if val is None:
            if ftype == "hidden" and fname == "_token":
                val = ""
            elif ftype == "checkbox":
                val = "unchecked"
            else:
                val = ""

        row["Value"] = val
        # Carry over Default Value from TEMPLATE (empty string if not defined)
        if "Default Value" not in row:
            row["Default Value"] = ""
        row["v2_site_id"] = v2_site_id
        output.append(row)

    return output


# ──────────────────────────────────────────────────────────────
# Print summary
# ──────────────────────────────────────────────────────────────
def print_summary(output):
    """Print a readable summary grouped by Panel Type."""
    print("\n" + "=" * 80)
    print("  SITE SETTINGS — WebBuilder Format")
    print("=" * 80)

    current_panel = ""
    filled = 0
    total = 0

    for row in output:
        panel = row["Panel Type"].replace("left-sidebar-settings--", "")
        if panel != current_panel:
            current_panel = panel
            print(f"\n{'─' * 70}")
            print(f"  [{panel.upper()}]")
            print(f"{'─' * 70}")

        label = row["Field Label"] or row["Field Name"] or "(empty)"
        val = row["Value"]
        total += 1
        if val:
            filled += 1

        default_val = row.get("Default Value", "")
        display_label = label if len(label) <= 40 else label[:37] + "..."
        display_val = val if len(str(val)) <= 25 else str(val)[:22] + "..."
        display_def = default_val if len(str(default_val)) <= 25 else str(default_val)[:22] + "..."
        status = "✓" if val else "·"
        print(f"  {status} {display_label:<42} = {display_val:<27} (default: {display_def})")

    print(f"\n{'=' * 80}")
    print(f"  Total: {filled}/{total} fields with values")
    print(f"  Output: {OUTPUT_JSON}")
    print("=" * 80)


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Fetching site settings from local HTML files...")
    print(f"v2_site_id: {V2_SITE_ID}")

    values = extract_values(SITE_DIR)
    output = build_output(values, V2_SITE_ID)

    # Write JSON
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print_summary(output)
    print(f"\n✅ JSON output saved to: {OUTPUT_JSON}")
