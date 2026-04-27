import os
import re
import time
import json
import unicodedata
from bs4 import BeautifulSoup

from openpyxl import Workbook
from urllib.parse import parse_qs, urlparse
from dotenv import load_dotenv
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import *
from openpyxl import load_workbook
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.action_chains import ActionChains


############# EXtract fields from HTML files ##############
load_dotenv()        #loads .env file

# Folder containing HTML files
OUTPUT_FOLDER = "excel_output"
OUTPUT_XLSX = "html_pages_data.xlsx"
EXCEL_TITLE_COLUMN = "Title"
Excel_File ="excel_output/html_pages_data.xlsx"
Sitemap_Excel_File = "excel_output/sitemap_data.xlsx"
GCMA_PATTERN = re.compile(r"\b[A-Z]{2,4}-[A-Z]{2,4}-[A-Z]{2,4}-\d{3,4}\b")
# ✅ Normalize Windows path - fix escape sequences that became tabs
HTML_Files_Folder = os.getenv("HTML_FOLDER").replace("\t", "\\t")
HTML_Files_Folder = os.path.normpath(HTML_Files_Folder)
sitemap_path = os.path.join(HTML_Files_Folder, "sitemap.xml")
# Create output folder if it doesn't exist
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def decode_text(text):
    """Fix mojibake like g√©n√©rales → générales"""
    if not text:
        return ""
    try:
        return text.encode("latin1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text

def get_relative_url(full_url):
   
    if not full_url:
        return ""

    parsed = urlparse(full_url)
    path = parsed.path or ""

    # ✅ Remove leading slash
    if path.startswith("/"):
        path = path[1:]

    # ✅ Remove file extension (.html, .htm, etc.)
    path, _ = os.path.splitext(path)

    return path


def extract_gcma_code(soup):
    for p in soup.find_all("p"):
        text = p.get_text(strip=True)
        match = GCMA_PATTERN.search(text)
        if match:
            return match.group()
    return ""

def extract_keywords(soup):
    meta_keywords = soup.find("meta", attrs={"name": "keywords"})
    if meta_keywords and meta_keywords.get("content"):
        return normalize_keywords(decode_text(meta_keywords["content"].strip()))

    # Optional fallback (comment out if not needed)
    meta_news_keywords = soup.find("meta", attrs={"name": "news_keywords"})
    if meta_news_keywords and meta_news_keywords.get("content"):
        return normalize_keywords(decode_text(meta_news_keywords["content"].strip()))
    return ""

def normalize_keywords(keyword_string):
    keywords = [k.strip().lower() for k in keyword_string.split(",") if k.strip()]
    return ", ".join(sorted(set(keywords)))

def extract_html_data(html_file_path):

    with open(html_file_path, "r", encoding="utf-8", errors="ignore") as file:
        soup = BeautifulSoup(file, "html.parser")

    title = decode_text(soup.title.string.strip()) if soup.title else ""

    
    canonical = ""
    canonical_tag = soup.find("link", rel="canonical")
    if canonical_tag and canonical_tag.get("href"):
        full_url = canonical_tag["href"].strip()
        canonical = get_relative_url(full_url)


    lang = ""
    html_tag = soup.find("html")
    if html_tag and html_tag.get("lang"):
        lang = html_tag["lang"].strip()

    description = ""
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        description = decode_text(meta_desc["content"].strip())

    gcma_code = extract_gcma_code(soup)
    
    keywords = extract_keywords(soup)
    return [
        html_file_path,
        title,
        canonical,
        lang,
        description,
        gcma_code,
        keywords
    ]

# Create Excel workbook and sheet
wb = Workbook()
ws = wb.active
ws.title = "HTML Pages Data"

# Header row
ws.append([
    "HTML File Path",
    "Title",
    "Canonical URL",
    "Language",
    "Description",
    "GCMA Code",
    "Keywords"
])

# Walk through HTML files
for root, _, files in os.walk(HTML_Files_Folder):
    for filename in files:
        if filename.lower().endswith(".html"):
            html_path = os.path.join(root, filename)
            row = extract_html_data(html_path)
            ws.append(row)

# Save Excel file
xlsx_path = os.path.join(OUTPUT_FOLDER, OUTPUT_XLSX)
wb.save(xlsx_path)

print("✅ All HTML files processed successfully.")
print(f"✅ Excel file saved at: {xlsx_path}")

# extract sitemap to excel
def extract_sitemap_to_excel(sitemap_path, output_path="excel_output/sitemap_data.xlsx"):
    '''
    Parses sitemap.xml and writes loc, title (from local HTML), priority,
    and changefreq to an Excel file.
    '''
    import xml.etree.ElementTree as ET

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    sitemap_base_dir = os.path.dirname(sitemap_path)  # e.g. "www.eczee.fr"

    tree = ET.parse(sitemap_path)
    root = tree.getroot()

    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    wb_sitemap = Workbook()
    ws_sitemap = wb_sitemap.active
    ws_sitemap.title = "Sitemap Data"

    # Header row
    ws_sitemap.append(["URL (loc)", "Title", "Priority", "Change Frequency"])

    for url_el in root.findall("sm:url", ns):
        loc        = url_el.findtext("sm:loc",        default="", namespaces=ns)
        priority   = url_el.findtext("sm:priority",   default="", namespaces=ns)
        changefreq = url_el.findtext("sm:changefreq", default="", namespaces=ns)

        # Derive local HTML file path from the URL
        title = ""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(loc)
            path = parsed.path.strip("/")

            if path == "":
                html_file = os.path.join(sitemap_base_dir, "index.html")
            else:
                html_file = os.path.join(sitemap_base_dir, path, "index.html")

            if os.path.exists(html_file):
                with open(html_file, "r", encoding="utf-8", errors="ignore") as f:
                    soup = BeautifulSoup(f, "html.parser")
                if soup.title and soup.title.string:
                    raw = soup.title.string.strip()
                    try:
                        title = raw.encode("latin1").decode("utf-8")
                    except Exception:
                        title = raw
            else:
                print(f"⚠️ HTML not found: {html_file}")
        except Exception as e:
            print(f"⚠️ Could not extract title for {loc}: {e}")

        ws_sitemap.append([loc, title, priority, changefreq])

    wb_sitemap.save(output_path)
    print(f"✅ Sitemap data written to: {output_path}")

############### Login to Webbuilder #################
#Gets the credentials from .env file

# USERNAME = os.getenv("LOGIN_USERNAME")
# PASSWORD = os.getenv("LOGIN_PASSWORD")
sitename = os.getenv("SITENAME")
instance = os.getenv("INSTANCE_ID")
#Pages = os.getenv("JSON_FOLDER")
LOGIN_URL = f"https://{sitename}/login"
# Validate required env vars before building URLs
if not sitename:
    raise ValueError("SITENAME is not set in your .env file. Add: SITENAME=your-domain.com")
if not instance:
    raise ValueError("INSTANCE_ID is not set in your .env file. Add: INSTANCE_ID=your-instance-id")
INSTANCE_URL = f"https://{sitename}/builder/website/{instance}"
# For Mac & windows

def webbuilder_login():
    driver.maximize_window()
    driver.get(LOGIN_URL)
    wait = WebDriverWait(driver, 20)
    pfizerlogin = wait.until(EC.presence_of_element_located((By.LINK_TEXT, "Pfizer Network Login")))
    pfizerlogin.click()
    time.sleep(2)
    driver.execute_script("document.body.style.zoom='80%'")
    time.sleep(8)
    print("Logged In on webbuilder")

def remove_site_suffix(title):
    if not title:
        return ""
    return title.split("|")[0].strip()

def has_special_alphabets(text):
    return any(ord(char) > 127 for char in text)


def load_gcma_map():
    wb = load_workbook(Excel_File)
    ws = wb.active

    headers = [cell.value for cell in ws[1]]
    path_idx = headers.index("HTML File Path")
    gcma_idx = headers.index("GCMA Code")

    gcma_map = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        html_path = row[path_idx]
        gcma = row[gcma_idx]

        if not html_path or not gcma:
            continue

        slug = extract_title_from_excel_path(html_path)

        if slug:
            gcma_map[slug] = gcma.strip()
    return gcma_map

def load_language_map_from_excel():

    wb = load_workbook(Excel_File)
    ws = wb.active

    headers = [cell.value for cell in ws[1]]
    path_idx = headers.index("HTML File Path")
    lang_idx = headers.index("Language")

    page_language_map = {}

    for row in ws.iter_rows(min_row=2, values_only=True):
        html_path = row[path_idx]
        lang = row[lang_idx]

        if not html_path or not lang:
            continue

        slug = extract_title_from_excel_path(html_path)

        if slug:
            page_language_map[slug] = lang.strip().lower()
    return page_language_map

def normalize_excel_language(excel_lang,select_element):
    
    excel_lang = excel_lang.lower().strip()

    # ✅ Get all available option values from Webbuilder
    available_values = {
        option.get_attribute("value").lower()
        for option in select_element.find_elements(By.TAG_NAME, "option")
    }

    # ✅ If full language exists, keep it
    if excel_lang in available_values:
        return excel_lang

    # ✅ Otherwise, fallback to base language
    base_lang = excel_lang.split("-")[0]
    if base_lang in available_values:
        return base_lang

    # ❌ Nothing matches
    return None


# Locate and select language using Selenium select API
def update_language_in_webbuilder(driver, wait, excel_language):
    
    try:
        # ✅ Locate the <select>
        language_select_el = wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "select.form-control")
            )
        )

        select = Select(language_select_el)

        # ✅ Normalize language (pt-br → pt)
        normalized_lang = normalize_excel_language(
            excel_language,
            language_select_el
        )

        if not normalized_lang:
            print(f"⚠️ Language '{excel_language}' not supported in Webbuilder")
            return

        select.select_by_value(normalized_lang)
        print(f"✅ Language set to: {normalized_lang}")

    except NoSuchElementException:
        print("❌ Language dropdown not found in Webbuilder")

def edit_page_setting_in_webbuilder(page_slug,gcma_code, page_language_map):
    print(f"✏️ Editing page in Webbuilder: {page_slug}")
    
    driver.get(INSTANCE_URL)
    driver.execute_script("document.body.style.zoom='80%'")
    
    wait = WebDriverWait(driver,20)
    # Hamburger menu
    hamburg = wait.until(EC.presence_of_element_located((By.CLASS_NAME, "fa-bars")))
    hamburg.click()
    time.sleep(2)
    
    #search Pages 
    searchpage = wait.until(EC.presence_of_element_located((By.ID, "pages-search-toggle")))
    searchpage.click()
    time.sleep(2)
    #Send page title to search box  
    searchtitle = wait.until(EC.presence_of_element_located((By.ID, "page--search-field")))
    searchtitle.send_keys(page_slug)
    time.sleep(2)
    #click on search result
    page_links = wait.until(EC.presence_of_all_elements_located((By.CLASS_NAME, "title-link")))

    clicked = False
    for link in page_links:
        if page_slug in link.text:
            link.click()
            clicked = True
            print(f"✅ Clicked page: {page_slug}")
            break

    if not clicked:
        print(f"❌ Page not found in list: {page_slug}")
        return False
    time.sleep(3)

    # Settings icon
    settingicon = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "i.fa-cog")))
    settingicon.click()
    time.sleep(3)
    
    # Page settings link
    pagesetting = wait.until(
        EC.element_to_be_clickable((
            By.XPATH,
            "//*[contains(normalize-space(),'Page settings')]"
        ))
    )
    pagesetting.click()
    print("✅ Page Settings clicked")
    time.sleep(2)
    
    '''
    # update the Page Title
    try:
        wait = WebDriverWait(driver, 20)

        # 1️⃣ Locate the Title input field
        title_input = wait.until(
            EC.visibility_of_element_located((By.ID, "page-title"))
        )

        # 2️⃣ Click to focus
        title_input.click()

        # 3️⃣ Select all existing text (cross‑platform)
        title_input.send_keys(Keys.CONTROL, "a")   # Windows/Linux
        title_input.send_keys(Keys.COMMAND, "a")   # macOS

        # 4️⃣ Delete existing value
        title_input.send_keys(Keys.BACKSPACE)

        # 5️⃣ Enter the new title
        title_input.send_keys(original_title)

        # 6️⃣ Blur to commit the value (important for Vue)
        driver.execute_script("arguments[0].blur();", title_input)

        print(f"✅ Title updated successfully: {original_title}")

    except TimeoutException:
        print("❌ Could not locate the Title input field")
    '''

    # Title has special character then enable option to remove special char from slug
    if has_special_alphabets(page_slug):
        print("✅ Title contains special alphabets")
        
       
        # Locate the checkbox and slider inside the wrapper
        checkboxes = driver.find_elements(
            By.CSS_SELECTOR,
            "#remove_special_chars_from_slugs input[type='checkbox']"
        )

        sliders = driver.find_elements(
            By.CSS_SELECTOR,
            "#remove_special_chars_from_slugs span.slider"
        )

        if checkboxes and sliders:
            checkbox = checkboxes[0]
            slider = sliders[0]

            # ✅ Check current state
            if not checkbox.is_selected():
                # Scroll into view
                driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});",
                    slider
                )

                # ✅ Click slider only if OFF
                driver.execute_script("arguments[0].click();", slider)
                print("✅ Toggle enabled")

            else:
                print("ℹ️ Toggle already enabled — no action taken")

        else:
            print("⚠️ Toggle not present — skipping safely")


    else:
        print("✅ Title contains only ASCII characters")
    time.sleep(2)
    
    # Update the GCMA code of the individual pages.
    try:
        wait = WebDriverWait(driver,5)

        # 1️⃣ Locate the Title input field
        gcma_input = wait.until(
            EC.visibility_of_element_located((By.ID, "page-gcma"))
        )

        # 2️⃣ Click to focus
        gcma_input.click()

        # 3️⃣ Select all existing text (cross‑platform)
        gcma_input.send_keys(Keys.CONTROL, "a")   # Windows/Linux
        gcma_input.send_keys(Keys.COMMAND, "a")   # macOS

        # 4️⃣ Delete existing value
        gcma_input.send_keys(Keys.BACKSPACE)

        #check the GCMA code is present or not
        if gcma_code.get(page_slug):
            # 5️⃣ Enter the new title
            gcma_input.send_keys(gcma_code.get(page_slug))
            print(f"✅ GCMA Code updated successfully: {gcma_code.get(page_slug)}")
        else:
            print("⚠️ Empty GCMA Code received — nothing to update")
        # 6️⃣ Blur to commit the value (important for Vue)
        driver.execute_script("arguments[0].blur();", gcma_input)

    except TimeoutException:
        print("❌ Could not locate the GCMA Code input field")
    #Update the Language of the pages
    wait = WebDriverWait(driver,5)

    # 🔹 Get language for this page from Excel
    excel_language = page_language_map.get(page_slug)
    DEFAULT_LANGUAGE = "en"
    # ✅ FORCE default language if Excel is empty
    if not excel_language:
        excel_language = DEFAULT_LANGUAGE
        print("ℹ️ Language empty in Excel — defaulting to English (en)")
    update_language_in_webbuilder(driver, wait, excel_language)
    # Save the changes - wait for modal and try multiple selectors
    time.sleep(2)  # Wait for settings modal to fully open
    save_button = None
    save_selectors = [
        (By.XPATH, "//button[translate(normalize-space(),'SAVE','save')='save']"),
        (By.XPATH, "//button[contains(@class,'tw-bg-blue-500') and contains(translate(.,'SAVE','save'),'save')]"),
        (By.CSS_SELECTOR, "button.tw-bg-blue-500"),
        (By.XPATH, "//button[@type='button' and contains(translate(.,'SAVE','save'),'save')]"),
    ]
    for by, selector in save_selectors:
        try:
            save_button = WebDriverWait(driver,5).until(EC.element_to_be_clickable((by, selector)))
            if save_button:
                print(f"✅ Save button found with: {selector}")
                break
        except:
            continue
    if not save_button:
        raise Exception("Could not find Save button")
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", save_button)
    time.sleep(0.5)
    driver.execute_script("arguments[0].click();", save_button)
    print("✅ Save button clicked")
    print("*********************************** Page Setting New page *************************************")
    time.sleep(2)
    return True

def Seo_setting_update(seo_normalize_title,description_map,keyword_map,priority_map, changefreq_map):
    
    driver.get(INSTANCE_URL)
    driver.execute_script("document.body.style.zoom='80%'")

    wait = WebDriverWait(driver,8)
    # Hamburger menu
    SEO_hamburg = wait.until(EC.presence_of_element_located((By.CLASS_NAME, "fa-bars")))
    SEO_hamburg.click()
    time.sleep(2)
    
    #search Pages 
    SEO_searchpage = wait.until(EC.presence_of_element_located((By.ID, "pages-search-toggle")))
    SEO_searchpage.click()
    time.sleep(2)
    #Send page title to search box  
    SEO_searchtitle = wait.until(EC.presence_of_element_located((By.ID, "page--search-field")))
    SEO_searchtitle.send_keys(seo_normalize_title)
    time.sleep(2)
    #click on search result
    SEO_page_links = wait.until(EC.presence_of_all_elements_located((By.CLASS_NAME, "title-link")))

    clicked = False
    for link in SEO_page_links:
        if seo_normalize_title in link.text:
            link.click()
            clicked = True
            print(f"✅ Clicked page: {seo_normalize_title}")
            break

    if not clicked:
        print(f"❌ Page not found in list: {seo_normalize_title}")
        return False
    time.sleep(3)

    # Settings icon
    SEO_settingicon = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "i.fa-cog")))
    SEO_settingicon.click()
    time.sleep(3)
    # locate the <a> for SEO settings
    seo_settings = wait.until(
        EC.presence_of_element_located((
            By.CSS_SELECTOR,
            "ul > li:nth-child(3) > a"
        ))
    )

    # ✅ Scroll just in case
    driver.execute_script(
        "arguments[0].scrollIntoView({block:'center'});",
        seo_settings
    )

    # ✅ FORCE click via JavaScript (required)
    driver.execute_script("arguments[0].click();", seo_settings)

    print("✅ Seo Settings clicked")
    time.sleep(2)
    wait = WebDriverWait(driver,5)
    # Update the SEO Title of the individual pages.
    try:

        # 1️⃣ Locate the Title input field
        Seotitle_input = wait.until(
            EC.visibility_of_element_located((By.NAME, "seo-page-title"))
        )

        # 2️⃣ Click to focus
        Seotitle_input.click()

        # 3️⃣ Select all existing text (cross‑platform)
        Seotitle_input.send_keys(Keys.CONTROL, "a")   # Windows/Linux
        Seotitle_input.send_keys(Keys.COMMAND, "a")   # macOS

        # 4️⃣ Delete existing value
        Seotitle_input.send_keys(Keys.BACKSPACE)

        # 5️⃣ Enter the new title
        Seotitle_input.send_keys(seo_normalize_title)

        # 6️⃣ Blur to commit the value (important for Vue)
        driver.execute_script("arguments[0].blur();", Seotitle_input)

        print(f"✅ SEO Title updated successfully: {seo_normalize_title}")

    except TimeoutException:
        print("❌ Could not locate the SEO Title input field")

    time.sleep(2)
    # Update the SEO Description
    try:
        seo_desc = wait.until(
            EC.presence_of_element_located(
                (By.NAME, "seo-page-description")
            )
        )

        # ✅ Clear existing text safely
        seo_desc.click()
        seo_desc.send_keys(Keys.CONTROL, "a")
        seo_desc.send_keys(Keys.COMMAND, "a")
        seo_desc.send_keys(Keys.BACKSPACE)

        description = description_map.get(seo_normalize_title)
        if description:
            # ✅ Enter new description
            seo_desc.send_keys(description)
            print("✅ SEO Description updated")
        else:
            print("⚠️ Empty description received — nothing to update")
        # ✅ Blur to commit (important for Vue)
        driver.execute_script("arguments[0].blur();", seo_desc)

    except TimeoutException:
        print("❌ SEO Description field not found")

    wait = WebDriverWait(driver, 5)
    # Update the SEO Keywords
    try:
        
        seo_keywords_input = wait.until(
            EC.presence_of_element_located(
                (By.NAME, "seo-page-keywords")   # ✅ adjust if needed
            )
        )

        driver.execute_script("arguments[0].scrollIntoView({block:'center'});",seo_keywords_input)

        # ✅ Clear existing text safely
        driver.execute_script("arguments[0].click();", seo_keywords_input)
        seo_keywords_input.send_keys(Keys.CONTROL, "a")
        seo_keywords_input.send_keys(Keys.COMMAND, "a")
        seo_keywords_input.send_keys(Keys.BACKSPACE)

        if keyword_map.get(seo_normalize_title):
            # ✅ Enter SEO Keywords
            seo_keywords_input.send_keys(keyword_map.get(seo_normalize_title))
            print("✅ SEO Keywords updated")
        else:
            print("⚠️ Empty SEO Keywords received — nothing to update")
        # ✅ Blur to commit (important for Vue)
        driver.execute_script("arguments[0].blur();", seo_keywords_input)

    except TimeoutException:
        print("❌ SEO Keywords field not found")

    # Update Priority
    
    priority_value = priority_map.get(seo_normalize_title)

    if priority_value:
        try:
            priority_input = None
            priority_selectors = [
                (By.NAME, "sitemap_priority"),
                (By.ID, "sitemap_priority"),
                (By.CSS_SELECTOR, "input[name='sitemap_priority']"),
                (By.CSS_SELECTOR, "input#sitemap_priority"),
                (By.XPATH, "//input[@type='range']"),
            ]

            for by, selector in priority_selectors:
                try:
                    priority_input = WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((by, selector))
                    )
                    if priority_input:
                        print(f"✅ Priority field found using: {selector}")
                        break
                except Exception:
                    continue

            if not priority_input:
                print(f"❌ Could not locate Priority slider for: {seo_normalize_title}")
                return

            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});",
                priority_input
            )
            time.sleep(1)

            # ✅ Get slider properties
            min_val = float(priority_input.get_attribute("min") or 0.1)
            max_val = float(priority_input.get_attribute("max") or 1.0)
            step    = float(priority_input.get_attribute("step") or 0.1)

            target_value = float(priority_value)
            target_value = max(min_val, min(max_val, target_value))

            # ✅ Calculate drag distance
            slider_width = priority_input.size["width"]
            value_ratio = (target_value - min_val) / (max_val - min_val)
            x_offset = int(slider_width * value_ratio)

            actions = ActionChains(driver)

            # ✅ REAL mouse drag
            actions.click_and_hold(priority_input)\
                .move_by_offset(x_offset, 0)\
                .release()\
                .perform()

            time.sleep(1)

            # ✅ Debug check
            actual_value = driver.execute_script(
                "return arguments[0].value;", priority_input
            )
            print(f"✅ Slider dragged to value: {float(actual_value)/10}")

        except Exception as e:
            print(f"❌ Error dragging Priority slider: {e}")

    else:
        print(f"⚠️ No priority found for: {seo_normalize_title}")

    # Update Change Frequency (default to 'daily' if not found in Excel)
    
    if changefreq_map:
        changefreq_value = next(iter(changefreq_map.values()))
        print(f"📋 Change Frequency from Excel: {changefreq_value}")
    else:
        changefreq_value = "daily"
        print(f"ℹ️ No change frequency in Excel for: {seo_normalize_title} — using default: daily")

    try:
        freq_select_el = None
        changefreq_selectors = [
            (By.CSS_SELECTOR, "select.tw-w-full.tw-px-2.tw-h-12.tw-border.tw-border-gray-200.tw-rounded"),
            (By.CSS_SELECTOR, "select.tw-w-full"),
            (By.XPATH, "//select[contains(@class,'tw-w-full')]"),
            (By.NAME, "seo-changefreq"),
            (By.CSS_SELECTOR, "select[name='seo-changefreq']"),
            (By.XPATH, "//select[@name='seo-changefreq']"),
            (By.XPATH, "//select[contains(@id,'changefreq')]"),
            (By.XPATH, "//select[contains(@id,'freq')]"),
        ]
        for by, selector in changefreq_selectors:
            try:
                freq_select_el = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((by, selector))
                )
                if freq_select_el:
                    print(f"✅ Change Frequency dropdown found using: {selector}")
                    break
            except Exception:
                continue

        if freq_select_el is None:
            print(f"❌ Could not locate the Change Frequency dropdown for: {seo_normalize_title}")
        else:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", freq_select_el)
            time.sleep(0.3)
            Select(freq_select_el).select_by_value(changefreq_value)
            print(f"✅ Change Frequency updated: {changefreq_value}")
    except Exception as e:
        print(f"❌ Error updating Change Frequency: {e}")

    # Save the changes - wait for modal and try multiple selectors
    time.sleep(2)  # Wait for settings modal to fully open
    save_button = None
    save_selectors = [
        (By.XPATH, "//button[translate(normalize-space(),'SAVE','save')='save']"),
        (By.XPATH, "//button[contains(@class,'tw-bg-blue-500') and contains(translate(.,'SAVE','save'),'save')]"),
        (By.CSS_SELECTOR, "button.tw-bg-blue-500"),
        (By.XPATH, "//button[@type='button' and contains(translate(.,'SAVE','save'),'save')]"),
    ]
    for by, selector in save_selectors:
        try:
            save_button = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((by, selector)))
            if save_button:
                print(f"✅ Save button found with: {selector}")
                break
        except:
            continue
    if not save_button:
        raise Exception("Could not find Save button")
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", save_button)
    time.sleep(0.5)
    driver.execute_script("arguments[0].click();", save_button)
    print("✅ Save button clicked")
    print("*********************************** SEO Setting New page *************************************")
    time.sleep(2)
    return True

def load_description_map_from_excel():
    
    wb = load_workbook(Excel_File)
    ws = wb.active

    headers = [cell.value for cell in ws[1]]
    path_idx = headers.index("HTML File Path")
    desc_idx = headers.index("Description")

    description_map = {}

    for row in ws.iter_rows(min_row=2, values_only=True):
        html_path = row[path_idx]
        desc = row[desc_idx]

        if not html_path or not desc:
            continue

        slug = extract_title_from_excel_path(html_path)

        if slug:
            description_map[slug] = desc.strip()

    return description_map

def load_keyword_map_from_excel():
    
    wb = load_workbook(Excel_File)
    ws = wb.active

    headers = [cell.value for cell in ws[1]]
    path_idx = headers.index("HTML File Path")
    keyword_idx = headers.index("Keywords")

    keyword_map = {}

    for row in ws.iter_rows(min_row=2, values_only=True):
        html_path = row[path_idx]
        keywords = row[keyword_idx]

        if not html_path or not keywords:
            continue

        slug = extract_title_from_excel_path(html_path)

        if slug:
            keyword_map[slug] = normalize_keywords(keywords)
    return keyword_map

def load_sitemap_map():
    
    wb_s = load_workbook(Sitemap_Excel_File)
    ws_s = wb_s.active

    headers = [cell.value for cell in ws_s[1]]
    path_idx       = headers.index("URL (loc)")
    priority_idx   = headers.index("Priority")
    changefreq_idx = headers.index("Change Frequency")

    priority_map   = {}
    changefreq_map = {}

    for row in ws_s.iter_rows(min_row=2, values_only=True):
        html_path  = row[path_idx]
        priority   = row[priority_idx]
        changefreq = row[changefreq_idx]

        if not html_path:
            continue

        slug = extract_title_from_excel_path(html_path)

        if not slug:
            continue

        if priority is not None:
            priority_map[slug] = str(priority).strip()

        if changefreq:
            changefreq_map[slug] = str(changefreq).strip()

    print(f"📘 Loaded {len(priority_map)} priority entries from sitemap_data.xlsx")
    print(f"📘 Loaded {len(changefreq_map)} changefreq entries from sitemap_data.xlsx")

    return priority_map, changefreq_map

##################### Load Title from the Excel ####################################
def extract_title_from_excel_path(html_path):

    html_path = html_path.replace("\\", "/")

    if html_path.endswith("/index.html"):
        return html_path.split("/")[-2]

    # fallback: filename without extension
    return os.path.splitext(os.path.basename(html_path))[0]
    print("********************************* Page Settings Started ******************************************")

def load_titles_from_excel_by_path(excel_file):
    
    wb = load_workbook(excel_file)
    ws = wb.active

    headers = [cell.value for cell in ws[1]]
    path_idx  = headers.index("HTML File Path")
    title_idx = headers.index("Title")

    title_map = {}

    for row in ws.iter_rows(min_row=2, values_only=True):
        html_path = row[path_idx]
        excel_title = row[title_idx]

        if not html_path:
            continue

        page_slug = extract_title_from_excel_path(html_path)
        clean_title = remove_site_suffix(excel_title)

        if page_slug and clean_title:
            title_map[page_slug] = clean_title

    print(f"📘 Loaded {len(title_map)} titles from Excel (via file path) {title_map}")
    print("********************************* Page Settings Started ******************************************")
    return title_map

def process_html_pages_by_path(html_root_folder,title_map, gcma_map, page_language_map):
    print("\n✅ PROCESSING HTML PAGES BY FILE PATH for Page Settings")
    print("*********************************** Page Setting New page *************************************")

    for root, _, files in os.walk(html_root_folder):
        for filename in files:
            if not filename.lower().endswith(".html"):
                continue

            html_path = os.path.join(root, filename)

            # ✅ Extract title from path
            page_title = extract_title_from_excel_path(html_path)

            if not page_title:
                continue

            normalized_page_title = extract_title_from_excel_path(html_path)
            original_excel_title = title_map[normalized_page_title]
            page_found = edit_page_setting_in_webbuilder(
                page_title,
                gcma_map,
                page_language_map
            )
            if not page_found:
                print(f"❌ Page not found in Webbuilder: {page_title}")
                print("➡️ Skipping and moving to next page\n")
                print("*********************************** Page Setting New page *************************************")
                continue
            '''
            normalized_page_title = normalize_title_for_compare(page_title)

            if normalized_page_title in title_map:
                original_excel_title = title_map[normalized_page_title]
                print(f"✅ MATCH → {page_title}")
                page_found = edit_page_setting_in_webbuilder(
                    normalized_page_title,
                    original_excel_title,
                    gcma_map,
                    page_language_map
                )

                # ✅ If page not found → skip safely
                if not page_found:
                    print("➡️ Skipping Page Settings and moving to next page\n")
                    print("*********************************** Page Setting New page *************************************")
                    continue

            else:
                print(f"❌ No Excel mapping for page: {page_title}")
                print("*********************************** Page Setting New page *************************************")
            '''
    print("\n✅ PAGES SETTINGS COMPLETED FOR ALL PAGES")

def process_seo_settings_for_all_pages(html_root_folder,title_map,description_map,keyword_map,priority_map, changefreq_map):
    print("\n✅ PROCESSING HTML PAGES BY FILE PATH for SEO Settings")
    print("*********************************** SEO Setting New page *************************************")

    for root, _, files in os.walk(html_root_folder):
        for filename in files:
            if not filename.lower().endswith(".html"):
                continue

            html_path = os.path.join(root, filename)

            # ✅ Extract title from path
            page_title = extract_title_from_excel_path(html_path)

            if not page_title:
                continue

            normalized_page_title = extract_title_from_excel_path(html_path)
            original_excel_title = title_map[normalized_page_title]
            page_found = Seo_setting_update(
                page_title,
                description_map,
                keyword_map,
                priority_map,
                changefreq_map
            )
            if not page_found:
                print(f"❌ Page not found in Webbuilder: {page_title}")
                print("➡️ Skipping and moving to next page\n")
                print("*********************************** SEO Setting New page *************************************")
                continue
            '''
            normalized_page_title = normalize_title_for_compare(page_title)

            if normalized_page_title in title_map:
                original_excel_title = title_map[normalized_page_title]
                print(f"✅ MATCH → {page_title}")
                page_found = Seo_setting_update(
                    normalized_page_title,original_excel_title,
                    description_map,keyword_map,priority_map, changefreq_map
                )

                # ✅ If page not found → skip safely
                if not page_found:
                    print("➡️ Skipping Page Settings and moving to next page\n")
                    print("*********************************** SEO Setting New page *************************************")
                    continue

            else:
                print(f"❌ No Excel mapping for page: {page_title}")
                print("*********************************** SEO Setting New page *************************************")
            '''
    print("\n✅ SEO SETTINGS COMPLETED FOR ALL PAGES")


##################### Compare the JSON title with Excel title##############################
'''
def process_json_pages(title_map,gcma_map,page_language_map):
    for filename in os.listdir(Pages):
        if not filename.endswith(".json"):
            continue

        json_path = os.path.join(Pages, filename)

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        json_title = data.get("settings", {}).get("title", "")
        if not json_title:
            continue

        normalized_json_title = normalize_title_for_compare(json_title)

        if normalized_json_title in title_map:
            original_excel_title = title_map[normalized_json_title]
            print(f"✅ MATCH → {json_title}")
            edit_page_setting_in_webbuilder(
                normalized_json_title,
                original_excel_title,
                gcma_map,
                page_language_map
            )
        else:
            print(f"❌ NO MATCH → {json_title}")
            print("*********************************** Page Setting New page *************************************")

def process_seo_settings_for_all_pages(title_map,description_map):
    print("\n************************ SEO SETTINGS STARTED ************************")

    for filename in os.listdir(Pages):
        if not filename.endswith(".json"):
            continue

        json_path = os.path.join(Pages, filename)

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        json_title = data.get("settings", {}).get("title", "")
        if not json_title:
            continue

        normalized_json_title = normalize_title_for_compare(json_title)

        if normalized_json_title in title_map:
            original_excel_title = title_map[normalized_json_title]
            print(f"✅ MATCH → {json_title}")
            # navigate to that page if needed inside this function
            Seo_setting_update(normalized_json_title,original_excel_title,description_map)

        else:
            print(f"❌ NO MATCH → {json_title}")
            print("*********************************** SEO Setting New page *************************************")
    print("\n✅ SEO SETTINGS COMPLETED FOR ALL PAGES")
'''

def load_404_from_excel_by_path(excel_file):

    wb = load_workbook(excel_file)
    ws = wb.active

    headers = [cell.value for cell in ws[1]]
    path_idx = headers.index("HTML File Path")
    title_idx = headers.index("Title")
    desc_idx = headers.index("Description")

    ERROR_PATHS = ("/404/index.html", "/errors/404.html")
    for row in ws.iter_rows(min_row=2, values_only=True):
        raw_path = row[path_idx] or ""
        html_path = (row[path_idx] or "").replace("\\", "/").lower()

        # ✅ Match paths like /404/index.html
        if html_path.endswith(ERROR_PATHS):
            return {
                "path":raw_path,
                "title": (row[title_idx] or "").strip(),
                "description": (row[desc_idx] or "").strip()
            }

    # ✅ Fallback if not found
    return {
        "path":"",
        "title": "",
        "description": ""
    }

def update_404_page_in_webbuilder():
    # ✅ Step 1: Read Excel data ONCE
    error_404_data = load_404_from_excel_by_path(Excel_File)
    print("****************************** 404 Page Settings *************************")
    print("404 Error page mapping data:", error_404_data)
    error_path = error_404_data.get("path")
    excel_title = ((error_404_data.get("title")) or "").strip()
    excel_description = (error_404_data.get("description") or "").strip()

    # ✅ Safety: do NOT update if error path is missing
    
    if not error_path:
        print("⚠️ No 404 page path found in Excel — skipping")
        return

    # ✅ PRINT THE ERROR PATH
    print(f"🚨 Updating 404 page for path: {error_path}")
    print(f"✅ 404 Excel Title      : {excel_title}")
    print(f"✅ 404 Excel Description: {excel_description or '[EMPTY — SKIPPED]'}")

    # 404 page SEO setting section - Locatin the page.
    try:
        wait = WebDriverWait(driver, 20)
        # click on down arrow of error page section
        chevron = wait.until(
            EC.presence_of_element_located((
                By.XPATH,
                "//div[contains(@class,'error-pages')]//i[contains(@class,'fa-chevron-right')]/parent::a"
            ))
        )
        # ✅ Scroll just in case
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});",
            chevron
        )
        driver.execute_script("arguments[0].click();", chevron)

        # click on 404 page 
        error_page = wait.until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR,
                "div.error-page-row:first-of-type a"
            ))
        )

        driver.execute_script("arguments[0].click();", error_page)
        # 404 page Settings icon
        settings_btn = wait.until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR,
                "div.error-page-settings div.tw-cursor-pointer"
            ))
        )

        driver.execute_script("arguments[0].click();", settings_btn)
        time.sleep(3)

        page_settings_link = wait.until(
            EC.presence_of_element_located((
                By.XPATH,
                "//div[contains(@class,'page-settings-content')]//i[contains(@class,'fa-arrow-left')]/parent::a"
            ))
        )

        driver.execute_script("arguments[0].click();", page_settings_link)
        print("✅ Page Settings clicked")

    except TimeoutException:
        print("❌ Could not locate the Chevron down arrow")
    time.sleep(3)

    # 404 page title of page setting
    seo_title_input = wait.until(
        EC.visibility_of_element_located((By.ID, "page-title"))
    )
    seo_title_input.click()
    seo_title_input.send_keys(Keys.CONTROL, "a")
    seo_title_input.send_keys(Keys.COMMAND, "a")
    seo_title_input.send_keys(Keys.BACKSPACE)
    seo_title_input.send_keys(excel_title)

    # ✅ Commit change (Vue requires blur)
    driver.execute_script("arguments[0].blur();", seo_title_input)
    print("✅ 404 Page Title updated")

    # ✅ Step 3: Update SEO Title
    seo_title_input = wait.until(
        EC.visibility_of_element_located((By.NAME, "seo-page-title"))
    )
    seo_title_input.click()
    seo_title_input.send_keys(Keys.CONTROL, "a")
    seo_title_input.send_keys(Keys.COMMAND, "a")
    seo_title_input.send_keys(Keys.BACKSPACE)
    seo_title_input.send_keys(excel_title)

    # ✅ Commit change (Vue requires blur)
    driver.execute_script("arguments[0].blur();", seo_title_input)
    print("✅ 404 SEO Title updated")

    # ✅ Step 4: Update SEO Description ONLY if present
    seo_desc = wait.until(
        EC.presence_of_element_located((By.NAME, "seo-page-description"))
    )
    seo_desc.click()
    seo_desc.send_keys(Keys.CONTROL, "a")
    seo_desc.send_keys(Keys.COMMAND, "a")
    seo_desc.send_keys(Keys.BACKSPACE)
    if excel_description:
        seo_desc.send_keys(excel_description)
    else:
        print("ℹ️ 404 SEO Description empty in Excel — leaving Webbuilder value unchanged")
    driver.execute_script("arguments[0].blur();", seo_desc)
    print("✅ 404 SEO Description updated")

    # ✅ Step 5: Save
    save_button = wait.until(
        EC.presence_of_element_located((
            By.XPATH,
            "//div[contains(@class,'top-actions-button')]//button[normalize-space()='SAVE']"
        ))
    )
    # ✅ Use JS click (required for Vue / SPA)
    driver.execute_script("arguments[0].click();", save_button)
    print("✅ 404 Page updated successfully")

################## Main Function ####################
if __name__ == "__main__":
    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()))
    extract_sitemap_to_excel(sitemap_path)
    webbuilder_login()
    global title_map,gcma_map,normalized_page_title, page_slug
    title_map = load_titles_from_excel_by_path(Excel_File)
    gcma_map = load_gcma_map()
    page_language_map = load_language_map_from_excel()
    description_map = load_description_map_from_excel()
    keyword_map = load_keyword_map_from_excel()
    priority_map, changefreq_map = load_sitemap_map()
    process_html_pages_by_path(HTML_Files_Folder,title_map,gcma_map,page_language_map)
    process_seo_settings_for_all_pages(HTML_Files_Folder,title_map,description_map,keyword_map,priority_map, changefreq_map)
    update_404_page_in_webbuilder()
