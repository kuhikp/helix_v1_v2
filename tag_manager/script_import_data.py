from collections import defaultdict
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import csv
import os
import time
import json
from dotenv import load_dotenv
from rapidfuzz import fuzz

chrome_options = Options()
# Uncomment the line below to run in headless mode (no browser window)
# chrome_options.add_argument('--headless=new')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')
load_dotenv()

# Try system chromedriver first, then fall back to ChromeDriverManager
try:
    driver = webdriver.Chrome(options=chrome_options)
except:
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

wait = WebDriverWait(driver, 10)

PANEL_WAIT_TIME = 10
MULTISELECT_WAIT_TIME = 2

USERNAME = os.getenv('USERNAME')
PASSWORD = os.getenv('PASSWORD')
EDISON_SITE_ID = os.getenv('EDISON_SITE_ID', '')

SYSTEM_FIELDS_TO_SKIP = {'_token', 'csrfmiddlewaretoken', 'sessionid'}
ALWAYS_SKIP_FIELDS = {'lexicon_brands[]', 'brands[]', 'lexicon_therapeutic_areas[]', 'lexicon_indications[]'}
MULTISELECT_FIELDS = {'audience_specialties[]', 'lexicon_brands[]', 'brands[]', 'lexicon_therapeutic_areas[]', 'lexicon_indications[]'}

try:
    driver.get('https://webbuilder.pfizer')
    time.sleep(2)
    try:
        driver.execute_script("document.querySelector('div.tw-text-center a.tw-bg-gray-900').click();", 1)
        time.sleep(5)
        if 'authorization' in driver.current_url:
            driver.find_element(By.ID, "username").send_keys(USERNAME)
            driver.find_element(By.ID, "password").send_keys(PASSWORD)
            driver.find_element(By.ID, "submit_button").click()
            time.sleep(5)
    except Exception as e:
        print(f"Login attempt failed: {e}")
        # Check if we're already logged in by looking for webbuilder in URL
        if 'webbuilder.pfizer' in driver.current_url and 'authorization' not in driver.current_url:
            print("Already logged in, continuing...")
        else:
            print("ERROR: Automatic login failed. Please check credentials in .env file.")
            print(f"Current URL: {driver.current_url}")
            raise Exception("Automatic login failed and manual login is not available in automated mode")

    # Load data from website.json instead of CSV files
    input_file = os.environ.get('JSONPATH')
    panel_data = defaultdict(list)
    
    with open(input_file, 'r', encoding='utf-8') as f:
        json_data = json.load(f)
    
    # Convert JSON format to the same structure as CSV reader
    for item in json_data:
        row = {
            'v2_site_id': item.get('v2_site_id', ''),
            'Panel Type': item.get('Panel Type', ''),
            'Field Label': item.get('Field Label', ''),
            'Field Name': item.get('Field Name', ''),
            'Type': item.get('Type', ''),
            'Value': item.get('Value', '')
        }
        key = (row['v2_site_id'], row['Panel Type'])
        panel_data[key].append(row)
    multiselect_values = defaultdict(lambda: defaultdict(list))
    for (v2_site_id, panel_type), fields in panel_data.items():
        for csv_row in fields:
            field_name = csv_row['Field Name']
            field_type = csv_row['Type']
            value = csv_row['Value']
            if (field_type == 'multiselect' or field_type == 'custom_multiselect') and field_name in MULTISELECT_FIELDS:
                for v in value.split(','):
                    v = v.strip()
                    if v:
                        multiselect_values[(v2_site_id, panel_type)][field_name].append(v)
    for (v2_site_id, panel_type), fields in panel_data.items():
        url = f"https://webbuilder.pfizer/builder/website/{v2_site_id}?panel={panel_type}"
        driver.get(url)
        time.sleep(PANEL_WAIT_TIME)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        for csv_row in fields:
            field_name = csv_row['Field Name']
            field_type = csv_row['Type']
            value = csv_row['Value']
            label_text = csv_row.get('Field Label', field_name)
            
            # Skip if no value is present (but preserve intentional whitespace like "   ")
            if value is None or (isinstance(value, str) and len(value) == 0):
                print(f"⊘ Skipping {field_name or 'unnamed field'} - no value")
                continue
            
            if (field_type == 'multiselect' or field_type == 'custom_multiselect') and field_name in MULTISELECT_FIELDS:
                values = multiselect_values[(v2_site_id, panel_type)][field_name]
                value = ','.join(sorted(set(values), key=values.index))
            label_text = csv_row.get('Field Label', '').strip().replace('\n', ' ').replace('\r', ' ')
            if not field_name and not label_text:
                continue
            
            # Debug logging for repository field
            if field_name == 'repository':
                print(f"[DEBUG] repository field found - label: '{label_text}', value: '{value}', type: '{field_type}'")
                print(f"[DEBUG] Using value from JSON as-is (including spaces if present)")
            
            # Skip other always-skip fields
            if field_name in ALWAYS_SKIP_FIELDS and field_type == 'text':
                continue
            if field_type == 'hidden':
                try:
                    label_text = csv_row.get('Field Label', field_name)
                    norm_label = label_text.lower().replace(' ', '').replace('*', '')
                    sections = driver.find_elements(By.XPATH, "//section")
                    for section in sections:
                        label_elems = section.find_elements(By.XPATH, ".//label")
                        for label_elem in label_elems:
                            label_val = label_elem.text.lower().replace(' ', '').replace('*', '')
                            if norm_label in label_val:
                                candidate_selects = section.find_elements(By.TAG_NAME, "select")
                                if candidate_selects:
                                    field_type = 'select'
                                    break
                                candidate_multiselect = section.find_elements(By.XPATH, ".//div[contains(@class, 'multiselect')]")
                                if candidate_multiselect:
                                    field_type = 'custom_multiselect'
                                    break
                        if field_type != 'hidden':
                            break
                except Exception:
                    pass
            try:
                if field_type in ['text', 'textarea', 'url']:
                    elem = None
                    label_text = csv_row.get('Field Label', '').strip().replace('\n', ' ').replace('\r', ' ')
                    try:
                        elem = driver.find_element(By.NAME, field_name)
                    except:
                        elem = None
                    if not elem:
                        fields_divs = driver.find_elements(By.CLASS_NAME, "field")
                        norm_label = label_text.lower().replace(' ', '').replace('*', '')
                        best_score = 0
                        best_elem = None
                        best_label = ''
                        for field_div in fields_divs:
                            try:
                                label_elem = field_div.find_element(By.TAG_NAME, "label")
                                label_val = label_elem.text.strip()
                                norm_label_val = label_val.lower().replace(' ', '').replace('*', '')
                                score = fuzz.ratio(norm_label, norm_label_val)
                                if score > best_score and score > 80:
                                    try:
                                        input_elem = field_div.find_element(By.NAME, field_name)
                                        best_elem = input_elem
                                        best_label = label_val
                                        best_score = score
                                    except Exception:
                                        continue
                            except Exception:
                                continue
                        if best_elem:
                            elem = best_elem
                    if not elem:
                        fields_divs = driver.find_elements(By.CLASS_NAME, "field")
                        norm_label = label_text.lower().replace(' ', '').replace('*', '')
                        for field_div in fields_divs:
                            try:
                                label_elem = field_div.find_element(By.TAG_NAME, "label")
                                label_val = label_elem.text.strip()
                                norm_label_val = label_val.lower().replace(' ', '').replace('*', '')
                                if norm_label in norm_label_val or norm_label_val in norm_label:
                                    input_elem = field_div.find_element(By.NAME, field_name)
                                    elem = input_elem
                                    break
                            except Exception:
                                continue
                    if not elem:
                        continue
                    try:
                        driver.execute_script("var overlays=document.querySelectorAll('iframe, .intercom-launcher-frame, .modal, .popup'); overlays.forEach(o=>o.style.display='none');")
                    except:
                        pass
                    driver.execute_script("arguments[0].scrollIntoView();", elem)
                    for _ in range(10):
                        if elem.is_displayed() and elem.is_enabled():
                            break
                        time.sleep(0.5)
                    if not elem.is_displayed() or not elem.is_enabled():
                        try:
                            parent_section = elem.find_element(By.XPATH, "ancestor::section[1]")
                            candidates = parent_section.find_elements(By.XPATH, ".//input | .//textarea | .//div[@contenteditable='true'] | .//span[@contenteditable='true']")
                            found_fallback = False
                            for cand in candidates:
                                try:
                                    if cand.is_displayed() and cand.is_enabled():
                                        cand_label = ''
                                        try:
                                            cand_label_elem = parent_section.find_element(By.XPATH, ".//label[@for='" + cand.get_attribute('id') + "']")
                                            cand_label = cand_label_elem.text.strip()
                                        except:
                                            pass
                                        if not cand_label:
                                            cand_label = cand.get_attribute('aria-label') or ''
                                        if (cand_label and (label_text.lower() in cand_label.lower() or cand_label.lower() in label_text.lower())) or not cand_label:
                                            try:
                                                if cand.tag_name in ['input', 'textarea']:
                                                    cand.clear()
                                                    cand.send_keys(value)
                                                else:
                                                    driver.execute_script("arguments[0].innerText = arguments[1];", cand, value)
                                                driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", cand)
                                                driver.execute_script("arguments[0].blur();", cand)
                                                found_fallback = True
                                                break
                                            except Exception:
                                                pass
                                except Exception:
                                    continue
                            if found_fallback:
                                continue
                        except Exception:
                            pass
                        try:
                            driver.execute_script("arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('change', { bubbles: true })); arguments[0].blur();", elem, value)
                        except Exception:
                            pass
                        continue
                    try:
                        elem.clear()
                        elem.send_keys(value)
                        driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", elem)
                        driver.execute_script("arguments[0].blur();", elem)
                        if field_name.lower() == "repository":
                            print(f"✓ repo - filled '{field_name}' with value: '{value}'")
                    except Exception:
                        try:
                            driver.execute_script("arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('change', { bubbles: true })); arguments[0].blur();", elem, value)
                            if field_name.lower() == "repository":
                                print(f"✓ repo - filled '{field_name}' with value: '{value}' (JS fallback)")
                        except Exception:
                            pass
                    if field_name.lower() == "domain":
                        time.sleep(2)
                elif field_type == 'checkbox':
                    from selenium.common.exceptions import ElementClickInterceptedException, ElementNotInteractableException, NoSuchElementException
                    try:
                        elem = None
                        label_text = csv_row.get('Field Label', '').strip().replace('\n', ' ').replace('\r', ' ')
                        norm_label = ''.join(e for e in label_text.lower() if e.isalnum())
                        if field_name:
                            checkboxes = driver.find_elements(By.NAME, field_name)
                        else:
                            checkboxes = driver.find_elements(By.XPATH, "//input[@type='checkbox']")
                        for cb in checkboxes:
                            label_val = ''
                            cb_id = cb.get_attribute('id')
                            if cb_id:
                                try:
                                    label_elem = driver.find_element(By.XPATH, f"//label[@for='{cb_id}']")
                                    label_val = label_elem.text.strip()
                                except Exception:
                                    pass
                            if not label_val:
                                try:
                                    label_elem = cb.find_element(By.XPATH, "ancestor::label[1]")
                                    label_val = label_elem.text.strip()
                                except Exception:
                                    pass
                            if not label_val:
                                try:
                                    parent = cb.find_element(By.XPATH, "..")
                                    if parent.tag_name == 'label':
                                        label_val = parent.text.strip()
                                except Exception:
                                    pass
                    except Exception:
                        pass
                    try:
                        elem = None
                        elem_idx = None
                        label_text = csv_row.get('Field Label', '').strip().replace('\n', ' ').replace('\r', ' ')
                        norm_label = ''.join(e for e in label_text.lower() if e.isalnum())
                        matched = False
                        candidate_labels = []
                        candidate_debug = []
                        exact_match_found = False
                        if field_name:
                            checkboxes = driver.find_elements(By.NAME, field_name)
                        else:
                            checkboxes = driver.find_elements(By.XPATH, "//input[@type='checkbox']")
                        for idx, cb in enumerate(checkboxes):
                            label_val = ''
                            cb_id = cb.get_attribute('id')
                            if cb_id:
                                try:
                                    label_elem = driver.find_element(By.XPATH, f"//label[@for='{cb_id}']")
                                    label_val = label_elem.text.strip()
                                except Exception:
                                    pass
                            if not label_val:
                                try:
                                    label_elem = cb.find_element(By.XPATH, "ancestor::label[1]")
                                    label_val = label_elem.text.strip()
                                except Exception:
                                    pass
                            if not label_val:
                                try:
                                    parent = cb.find_element(By.XPATH, "..")
                                    if parent.tag_name == 'label':
                                        label_val = parent.text.strip()
                                except Exception:
                                    pass
                            if not label_val:
                                try:
                                    field_div = cb.find_element(By.XPATH, "ancestor::div[contains(@class, 'form-group') or contains(@class, 'field')][1]")
                                    field_labels = field_div.find_elements(By.TAG_NAME, "label")
                                    for flabel in field_labels:
                                        if flabel.text.strip():
                                            label_val = flabel.text.strip()
                                            break
                                except Exception:
                                    pass
                            if not label_val:
                                try:
                                    sibling_label = cb.find_element(By.XPATH, "preceding-sibling::label[1]")
                                    label_val = sibling_label.text.strip()
                                except Exception:
                                    pass
                            state = 'checked' if cb.is_selected() else 'unchecked'
                            candidate_debug.append({'idx': idx, 'label': label_val, 'state': state, 'id': cb_id, 'outerHTML': cb.get_attribute('outerHTML')})
                        for idx, cb in enumerate(checkboxes):
                            label_val = ''
                            cb_id = cb.get_attribute('id')
                            if cb_id:
                                try:
                                    label_elem = driver.find_element(By.XPATH, f"//label[@for='{cb_id}']")
                                    label_val = label_elem.text.strip()
                                except Exception:
                                    pass
                            if not label_val:
                                try:
                                    label_elem = cb.find_element(By.XPATH, "ancestor::label[1]")
                                    label_val = label_elem.text.strip()
                                except Exception:
                                    pass
                            if not label_val:
                                try:
                                    parent = cb.find_element(By.XPATH, "..")
                                    if parent.tag_name == 'label':
                                        label_val = parent.text.strip()
                                except Exception:
                                    pass
                            if not label_val:
                                try:
                                    field_div = cb.find_element(By.XPATH, "ancestor::div[contains(@class, 'form-group') or contains(@class, 'field')][1]")
                                    field_labels = field_div.find_elements(By.TAG_NAME, "label")
                                    for flabel in field_labels:
                                        if flabel.text.strip():
                                            label_val = flabel.text.strip()
                                            break
                                except Exception:
                                    pass
                            if not label_val:
                                try:
                                    sibling_label = cb.find_element(By.XPATH, "preceding-sibling::label[1]")
                                    label_val = sibling_label.text.strip()
                                except Exception:
                                    pass
                            norm_label_val = ''.join(e for e in label_val.lower() if e.isalnum())
                            candidate_labels.append(label_val)
                            if norm_label and norm_label_val and norm_label == norm_label_val:
                                elem = cb
                                elem_idx = idx
                                matched = True
                                exact_match_found = True
                                break
                        if not matched:
                            from difflib import SequenceMatcher
                            best_score = 0
                            best_idx = None
                            for idx, cb in enumerate(checkboxes):
                                label_val = ''
                                cb_id = cb.get_attribute('id')
                                if cb_id:
                                    try:
                                        label_elem = driver.find_element(By.XPATH, f"//label[@for='{cb_id}']")
                                        label_val = label_elem.text.strip()
                                    except Exception:
                                        pass
                                if not label_val:
                                    try:
                                        label_elem = cb.find_element(By.XPATH, "ancestor::label[1]")
                                        label_val = label_elem.text.strip()
                                    except Exception:
                                        pass
                                if not label_val:
                                    try:
                                        parent = cb.find_element(By.XPATH, "..")
                                        if parent.tag_name == 'label':
                                            label_val = parent.text.strip()
                                    except Exception:
                                        pass
                                if not label_val:
                                    try:
                                        field_div = cb.find_element(By.XPATH, "ancestor::div[contains(@class, 'form-group') or contains(@class, 'field')][1]")
                                        field_labels = field_div.find_elements(By.TAG_NAME, "label")
                                        for flabel in field_labels:
                                            if flabel.text.strip():
                                                label_val = flabel.text.strip()
                                                break
                                    except Exception:
                                        pass
                                if not label_val:
                                    try:
                                        sibling_label = cb.find_element(By.XPATH, "preceding-sibling::label[1]")
                                        label_val = sibling_label.text.strip()
                                    except Exception:
                                        pass
                                norm_label_val = ''.join(e for e in label_val.lower() if e.isalnum())
                                score = SequenceMatcher(None, norm_label, norm_label_val).ratio()
                                threshold = 0.75 if len(norm_label) > 30 else 0.85
                                if norm_label and norm_label_val and score > threshold and score > best_score:
                                    best_score = score
                                    elem = cb
                                    elem_idx = idx
                                    matched = True
                        if matched:
                            pass
                        if not matched and all(lab == '' for lab in candidate_labels):
                            try:
                                parent_section = None
                                try:
                                    parent_section = checkboxes[0].find_element(By.XPATH, "ancestor::section[1]")
                                except Exception:
                                    try:
                                        parent_section = checkboxes[0].find_element(By.XPATH, "ancestor::div[contains(@class, 'field') or contains(@class, 'form-group')][1]")
                                    except Exception:
                                        pass
                                if parent_section:
                                    section_labels = parent_section.find_elements(By.TAG_NAME, 'label')
                                    section_label_texts = [lbl.text.strip() for lbl in section_labels if lbl.text.strip()]
                                    if len(section_label_texts) == len(checkboxes):
                                        for idx, lbl_text in enumerate(section_label_texts):
                                            if label_text.strip() == lbl_text.strip():
                                                elem = checkboxes[idx]
                                                elem_idx = idx
                                                matched = True
                                                break
                                    else:
                                        pass
                                else:
                                    pass
                            except Exception:
                                pass
                        if not matched:
                            pass
                        if not elem.is_displayed():
                            pass
                        elif not elem.is_enabled():
                            pass
                        else:
                            initial_state = elem.is_selected()
                            target_state = str(value).strip().lower() == "checked"
                            if initial_state != target_state or True:
                                try:
                                    if initial_state != target_state:
                                        elem.click()
                                        time.sleep(1)
                                        
                                        # Check if a popup appeared (e.g., for GRV checkbox)
                                        try:
                                            popup = driver.find_element(By.CLASS_NAME, "swal2-actions")
                                            if popup.is_displayed():
                                                # Look for the "Public" button in the popup
                                                try:
                                                    public_button = popup.find_element(By.XPATH, ".//button[contains(@class, 'swal2-cancel') and contains(@class, 'swal2-styled') and (contains(text(), 'Public') or contains(text(), 'public'))]")
                                                    if public_button.is_displayed() and public_button.is_enabled():
                                                        public_button.click()
                                                        print(f"✓ Clicked 'Public' button in popup for '{field_name}'")
                                                        time.sleep(1)
                                                except Exception as btn_e:
                                                    # Try alternate selector
                                                    try:
                                                        public_button = driver.find_element(By.XPATH, "//div[contains(@class, 'swal2-actions')]//button[contains(@class, 'swal2-cancel') and (contains(text(), 'Public') or contains(text(), 'public'))]")
                                                        if public_button.is_displayed() and public_button.is_enabled():
                                                            public_button.click()
                                                            print(f"✓ Clicked 'Public' button in popup for '{field_name}'")
                                                            time.sleep(1)
                                                    except Exception:
                                                        print(f"⚠️ Popup appeared but could not find 'Public' button for '{field_name}'")
                                        except Exception:
                                            # No popup appeared, continue normally
                                            pass
                                        
                                        driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", elem)
                                        driver.execute_script("arguments[0].blur();", elem)
                                        time.sleep(1)
                                    final_state = elem.is_selected()
                                    if final_state != target_state:
                                        elem.click()
                                        time.sleep(1)
                                        
                                        # Check for popup again on second click attempt
                                        try:
                                            popup = driver.find_element(By.CLASS_NAME, "swal2-actions")
                                            if popup.is_displayed():
                                                try:
                                                    public_button = popup.find_element(By.XPATH, ".//button[contains(@class, 'swal2-cancel') and contains(@class, 'swal2-styled') and (contains(text(), 'Public') or contains(text(), 'public'))]")
                                                    if public_button.is_displayed() and public_button.is_enabled():
                                                        public_button.click()
                                                        print(f"✓ Clicked 'Public' button in popup for '{field_name}' (2nd attempt)")
                                                        time.sleep(1)
                                                except Exception:
                                                    pass
                                        except Exception:
                                            pass
                                        
                                        driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", elem)
                                        driver.execute_script("arguments[0].blur();", elem)
                                        time.sleep(1)
                                    final_state = elem.is_selected()
                                    if final_state != target_state:
                                        driver.execute_script("arguments[0].checked = arguments[1]; arguments[0].dispatchEvent(new Event('change', { bubbles: true })); arguments[0].blur();", elem, target_state)
                                        time.sleep(1)
                                except (ElementClickInterceptedException, ElementNotInteractableException) as e:
                                    try:
                                        driver.execute_script("arguments[0].click();", elem)
                                        time.sleep(1)
                                        
                                        # Check for popup after JS click
                                        try:
                                            popup = driver.find_element(By.CLASS_NAME, "swal2-actions")
                                            if popup.is_displayed():
                                                try:
                                                    public_button = popup.find_element(By.XPATH, ".//button[contains(@class, 'swal2-cancel') and contains(@class, 'swal2-styled') and (contains(text(), 'Public') or contains(text(), 'public'))]")
                                                    if public_button.is_displayed() and public_button.is_enabled():
                                                        public_button.click()
                                                        print(f"✓ Clicked 'Public' button in popup for '{field_name}' (JS click)")
                                                        time.sleep(1)
                                                except Exception:
                                                    pass
                                        except Exception:
                                            pass
                                        
                                        driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", elem)
                                        driver.execute_script("arguments[0].blur();", elem)
                                        time.sleep(1)
                                    except Exception as js_e:
                                        pass
                                except Exception:
                                    pass
                            final_state = elem.is_selected()
                            if final_state != target_state:
                                pass
                    except Exception:
                        pass
                elif field_type == 'select':
                    select_elem = None
                    if field_name:
                        try:
                            select_elem = driver.find_element(By.NAME, field_name)
                        except:
                            select_elem = None
                    if not select_elem and field_name:
                        try:
                            select_elem = driver.find_element(By.ID, field_name)
                        except:
                            select_elem = None
                    if not select_elem:
                        # Try to find by label and then locate the select in the same section
                        label_text = csv_row.get('Field Label', '').strip()
                        if label_text:
                            try:
                                sections = driver.find_elements(By.XPATH, "//section | //div[contains(@class, 'field') or contains(@class, 'form-group')]")
                                norm_label = label_text.lower().replace(' ', '').replace('*', '')
                                for section in sections:
                                    try:
                                        label_elem = section.find_element(By.XPATH, ".//label")
                                        label_val = label_elem.text.strip()
                                        norm_label_val = label_val.lower().replace(' ', '').replace('*', '')
                                        if norm_label in norm_label_val or norm_label_val in norm_label:
                                            candidate_selects = section.find_elements(By.TAG_NAME, "select")
                                            if candidate_selects:
                                                select_elem = candidate_selects[0]
                                                break
                                    except Exception:
                                        continue
                            except Exception:
                                pass
                    if not select_elem:
                        selects = driver.find_elements(By.TAG_NAME, "select")
                        norm_label = csv_row.get('Field Label', field_name).lower().replace(' ', '').replace('*', '')
                        best_score = 0
                        best_elem = None
                        best_label = ''
                        for sel in selects:
                            try:
                                label_elem = sel.find_element(By.XPATH, "preceding-sibling::label[1]")
                                label_val = label_elem.text.strip()
                                norm_label_val = label_val.lower().replace(' ', '').replace('*', '')
                                score = fuzz.ratio(norm_label, norm_label_val)
                                if score > best_score and score > 80:
                                    best_elem = sel
                                    best_label = label_val
                                    best_score = score
                            except Exception:
                                continue
                        if best_elem:
                            select_elem = best_elem
                    if select_elem:
                        print(f"✓ Found select element for '{field_name}' (label: '{label_text}')")
                        options = select_elem.find_elements(By.TAG_NAME, "option")
                        matched = False
                        value_norm = value.strip().lower().replace(' ', '')
                        for opt in options:
                            opt_text_norm = opt.text.strip().lower().replace(' ', '')
                            if opt_text_norm == value_norm:
                                opt.click()
                                matched = True
                                print(f"✓ Selected option '{opt.text.strip()}' for '{field_name}'")
                                break
                        if not matched:
                            print(f"❌ No exact match found for select '{field_name}' with value '{value}'. Field will not be changed. Available options: {[opt.text for opt in options]}")
                        else:
                            driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", select_elem)
                            driver.execute_script("arguments[0].blur();", select_elem)
                            selected_option = None
                            for opt in options:
                                if opt.is_selected():
                                    selected_option = opt.text.strip()
                                    break
                            if selected_option and selected_option.lower().replace(' ', '') == value_norm:
                                pass
                            else:
                                print(f"❌ Verification failed: '{field_name}' is set to '{selected_option}', expected '{value}'.")
                    else:
                        print(f"❌ Could not find select element for field '{field_name}' (label: '{label_text}')")
                    continue
                elif field_type == 'custom_multiselect':
                    try:
                        driver.execute_script("var iframe=document.querySelector('iframe.intercom-launcher-frame');if(iframe){iframe.style.display='none';}")
                    except:
                        pass
                    multiselect_div = None
                    hidden_input = None
                    parent_section = None
                    try:
                        hidden_input = driver.find_element(By.XPATH, f"//input[@name='{field_name}' and @type='hidden']")
                        parent_section = hidden_input.find_element(By.XPATH, "ancestor::section[1]")
                        try:
                            multiselect_div = parent_section.find_element(By.XPATH, ".//div[contains(@class, 'multiselect')]")
                        except:
                            pass
                    except:
                        pass
                    if not multiselect_div:
                        try:
                            label_text = csv_row.get('Field Label', field_name)
                            norm_label = label_text.lower().replace(' ', '').replace('*', '')
                            sections = driver.find_elements(By.XPATH, "//section")
                            for section in sections:
                                label_elems = section.find_elements(By.XPATH, ".//label")
                                for label_elem in label_elems:
                                    label_val = label_elem.text.lower().replace(' ', '').replace('*', '')
                                    if norm_label in label_val:
                                        candidate_multiselect = section.find_elements(By.XPATH, ".//div[contains(@class, 'multiselect')]")
                                        candidate_hidden_inputs = section.find_elements(By.XPATH, f".//input[@name='{field_name}' and @type='hidden']")
                                        candidate_text_inputs = section.find_elements(By.XPATH, f".//input[@name='{field_name}' and @type='text' and contains(@style, 'display: none')]")
                                        if candidate_multiselect and (candidate_hidden_inputs or candidate_text_inputs):
                                            multiselect_div = candidate_multiselect[0]
                                            parent_section = section
                                            if candidate_hidden_inputs:
                                                hidden_input = candidate_hidden_inputs[0]
                                            else:
                                                hidden_input = candidate_text_inputs[0]
                                            break
                                if multiselect_div:
                                    break
                        except Exception as e:
                            print(f"⚠️ Fallback section scan failed for '{field_name}': {e}")
                    if not multiselect_div or not hidden_input:
                        try:
                            sections = driver.find_elements(By.XPATH, "//section")
                            for section in sections:
                                try:
                                    label = section.find_element(By.XPATH, f".//label[contains(text(), '{row['Field Label']}')]")
                                    candidate_multiselect = section.find_elements(By.XPATH, ".//div[contains(@class, 'multiselect')]")
                                    candidate_hidden_inputs = section.find_elements(By.XPATH, f".//input[@name='{field_name}' and @type='hidden']")
                                    candidate_text_inputs = section.find_elements(By.XPATH, f".//input[@name='{field_name}' and @type='text' and contains(@style, 'display: none')]")
                                    if candidate_multiselect and (candidate_hidden_inputs or candidate_text_inputs):
                                        multiselect_div = candidate_multiselect[0]
                                        parent_section = section
                                        if candidate_hidden_inputs:
                                            hidden_input = candidate_hidden_inputs[0]
                                        else:
                                            hidden_input = candidate_text_inputs[0]
                                        break
                                except Exception:
                                    continue
                        except Exception as e:
                            print(f"⚠️ Fallback section scan failed for '{field_name}': {e}")
                    if not multiselect_div:
                        print(f"❌ Could not find multiselect container for field '{field_name}' after all methods.")
                        continue
                    try:
                        driver.execute_script("var overlays=document.querySelectorAll('iframe, .intercom-launcher-frame, .modal, .popup, .tw-modal, .tw-overlay, .tw-header, .header, .tw-dialog, .dialog'); overlays.forEach(o=>o.style.display='none');")
                    except Exception:
                        pass
                    try:
                        driver.execute_script("arguments[0].scrollIntoView();", multiselect_div)
                        try:
                            WebDriverWait(driver, 10).until(lambda d: multiselect_div.is_displayed() and multiselect_div.is_enabled())
                        except Exception as e:
                            print(f"[ERROR] Multiselect div for '{field_name}' not visible/enabled: {e}")
                            continue
                        clicked = False
                        try:
                            multiselect_div.click()
                            clicked = True
                        except Exception as e:
                            try:
                                driver.execute_script("arguments[0].click();", multiselect_div)
                                clicked = True
                            except Exception as js_e:
                                print(f"[ERROR] JS click also failed for multiselect '{field_name}': {js_e}")
                        if not clicked:
                            continue
                        time.sleep(1.5)
                        input_elem = multiselect_div.find_element(By.XPATH, ".//input[contains(@class, 'multiselect__input')]")
                        input_ready = False
                        for attempt in range(3):
                            try:
                                if input_elem.is_displayed() and input_elem.is_enabled():
                                    input_ready = True
                                    break
                            except Exception:
                                pass
                            try:
                                driver.execute_script("arguments[0].focus();", input_elem)
                            except Exception:
                                pass
                            try:
                                driver.execute_script("var overlays=document.querySelectorAll('iframe, .intercom-launcher-frame, .modal, .popup, .tw-modal, .tw-overlay, .tw-header, .header, .tw-dialog, .dialog'); overlays.forEach(o=>o.style.display='none');")
                            except Exception:
                                pass
                            try:
                                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", input_elem)
                            except Exception:
                                pass
                            time.sleep(1)
                        if not input_ready:
                            alt_inputs = multiselect_div.find_elements(By.TAG_NAME, 'input')
                            for alt in alt_inputs:
                                try:
                                    if alt.is_displayed() and alt.is_enabled():
                                        input_elem = alt
                                        input_ready = True
                                        break
                                except Exception:
                                    continue
                        if not input_ready:
                            try:
                                driver.execute_script("arguments[0].value = ''; arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", input_elem)
                            except Exception:
                                pass
                            try:
                                print(f"[ERROR] Multiselect input for '{field_name}' not interactable after all attempts.")
                                print(f"[DEBUG] Multiselect container HTML: {multiselect_div.get_attribute('outerHTML')}")
                                print(f"[DEBUG] Input HTML: {input_elem.get_attribute('outerHTML')}")
                            except Exception:
                                pass
                            continue
                    except Exception as e:
                        print(f"❌ Could not find or activate visible input for multiselect '{field_name}': {e}")
                        continue
                    if (v2_site_id, panel_type) in multiselect_values and field_name in multiselect_values[(v2_site_id, panel_type)]:
                        values = [v.strip() for v in multiselect_values[(v2_site_id, panel_type)][field_name] if v.strip()]
                    else:
                        values = [v.strip() for v in value.split(',') if v.strip()]
                    for idx, val in enumerate(values):
                        try:
                            tags_current = multiselect_div.find_elements(By.XPATH, ".//span[contains(@class, 'multiselect__tag')]")
                            tag_texts_current = [t.text.strip() for t in tags_current]
                            if val in tag_texts_current:
                                continue
                            input_elem.clear()
                            input_elem.send_keys(val)
                            found_option = False
                            for attempt in range(2):
                                for _ in range(15):
                                    dropdown_options = multiselect_div.find_elements(By.XPATH, ".//li[contains(@class, 'multiselect__element')]//span[contains(@class, 'multiselect__option')]")
                                    visible_options = [o for o in dropdown_options if o.is_displayed()]
                                    for option in visible_options:
                                        if option.text.strip().lower() == val.lower():
                                            try:
                                                WebDriverWait(driver, 5).until(EC.element_to_be_clickable(option))
                                            except Exception as e:
                                                continue
                                            driver.execute_script("arguments[0].scrollIntoView();", option)
                                            option.click()
                                            found_option = True
                                            time.sleep(1.5)
                                            break
                                    if found_option:
                                        break
                                if found_option:
                                    break
                                input_elem.clear()
                                time.sleep(1)
                                input_elem.send_keys(val)
                            if not found_option:
                                print(f"[WARNING] Option '{val}' not found for '{field_name}' after retries. Check spelling or UI.")
                                try:
                                    dropdown_html = multiselect_div.get_attribute('outerHTML')
                                except Exception as html_e:
                                    print(f"[DEBUG] Could not get dropdown HTML: {html_e}")
                            tags_after = multiselect_div.find_elements(By.XPATH, ".//span[contains(@class, 'multiselect__tag')]")
                            tag_texts = [t.text.strip() for t in tags_after]
                            if val not in tag_texts:
                                print(f"[WARNING] After selection, tag for '{val}' not present in '{field_name}'. Current tags: {tag_texts}")
                        except Exception as e:
                            print(f"[ERROR] Exception while selecting '{val}' for '{field_name}': {e}")
                    tags_final = multiselect_div.find_elements(By.XPATH, ".//span[contains(@class, 'multiselect__tag')]")
                    tag_texts_final = [t.text.strip() for t in tags_final]
                elif field_type == 'custom_multiselect_single':
                    try:
                        found = False
                        label_text = csv_row.get('Field Label', field_name).replace('\n', ' ').replace('\r', ' ')
                        norm_label = label_text.lower().replace(' ', '').replace('*', '')
                        field_name_csv = field_name
                        label_elem = None
                        all_labels = driver.find_elements(By.TAG_NAME, 'label')
                        for lbl in all_labels:
                            lbl_text_norm = lbl.text.lower().replace(' ', '').replace('*', '')
                            lbl_for = lbl.get_attribute('for')
                            if lbl_for == field_name_csv and norm_label in lbl_text_norm:
                                label_elem = lbl
                                break
                        if label_elem:
                            try:
                                multiselect_div = label_elem.find_element(By.XPATH, "following-sibling::div[contains(@class, 'multiselect')]")

                            except Exception:
                                parent_elem = label_elem.find_element(By.XPATH, '..')
                                siblings = parent_elem.find_elements(By.XPATH, "./*")
                                multiselect_div = None
                                for sib in siblings:
                                    if sib.tag_name == 'div' and 'multiselect' in sib.get_attribute('class'):
                                        multiselect_div = sib
                                        break
                            if multiselect_div and multiselect_div.is_displayed() and multiselect_div.is_enabled():
                                try:
                                    driver.execute_script("var overlays=document.querySelectorAll('iframe, .intercom-launcher-frame, .modal, .popup, .tw-modal, .tw-overlay, .tw-header, .header, .tw-dialog, .dialog'); overlays.forEach(o=>o.style.display='none');")
                                except Exception:
                                    pass
                                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", multiselect_div)
                                time.sleep(0.5)
                                try:
                                    tags_elem = None
                                    try:
                                        tags_elem = multiselect_div.find_element(By.CLASS_NAME, 'multiselect__tags')
                                    except Exception:
                                        pass
                                    if not tags_elem:
                                        try:
                                            tags_elem = multiselect_div.find_element(By.CLASS_NAME, 'multiselect__single')
                                        except Exception:
                                            pass
                                    if tags_elem:
                                        try:
                                            tags_elem.click()
                                        except Exception:
                                            driver.execute_script("arguments[0].click();", tags_elem)
                                    else:
                                        try:
                                            multiselect_div.click()
                                        except Exception as click_exc:
                                            driver.execute_script("arguments[0].click();", multiselect_div)
                                except Exception as e:
                                    pass
                                for _ in range(10):
                                    try:
                                        content_wrapper = multiselect_div.find_element(By.CLASS_NAME, 'multiselect__content-wrapper')
                                        if content_wrapper.is_displayed():
                                            break
                                    except Exception:
                                        pass
                                    time.sleep(0.5)
                                time.sleep(0.5)
                                options = multiselect_div.find_elements(By.XPATH, ".//li[contains(@class, 'multiselect__element')]//span[contains(@class, 'multiselect__option')]")
                                visible_options = [opt for opt in options if opt.is_displayed()]
                                matched = False
                                value_norm = value.strip().lower()
                                for option in visible_options:
                                    option_text_norm = option.text.strip().lower()
                                    if option_text_norm == value_norm:
                                        driver.execute_script("arguments[0].scrollIntoView();", option)
                                        option.click()
                                        matched = True
                                        time.sleep(2)
                                        break
                                if not matched:
                                    for option in visible_options:
                                        option_text_norm = option.text.strip().lower()
                                        if value_norm in option_text_norm or option_text_norm in value_norm:
                                            driver.execute_script("arguments[0].scrollIntoView();", option)
                                            option.click()
                                            matched = True
                                            time.sleep(2)
                                            break
                                if not matched:
                                    print(f"\u26a0\ufe0f Option '{value}' not found for custom_multiselect_single '{field_name}'. Available: {[o.text for o in visible_options]}")
                                    try:
                                        content_wrapper = multiselect_div.find_element(By.CLASS_NAME, 'multiselect__content-wrapper')
                                    except Exception:
                                        pass
                                else:
                                    driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", multiselect_div)
                                    driver.execute_script("arguments[0].blur();", multiselect_div)
                                    time.sleep(1)
                                found = True
                            else:
                                parent_elem = label_elem.find_element(By.XPATH, '..')
                                siblings = parent_elem.find_elements(By.XPATH, "./*")
                                print(f"\u274c Could not find interactable multiselect for custom_multiselect_single field '{field_name}' with label '{label_text}'.")
                                print(f"Siblings in parent: {[sib.tag_name + ' ' + (sib.get_attribute('class') or '') for sib in siblings]}")
                                print(f"Multiselect HTML: {multiselect_div.get_attribute('outerHTML') if multiselect_div else 'None'}")
                        else:
                            print(f"\u274c Could not find label for custom_multiselect_single field '{field_name}' with label '{label_text}'.")
                    except Exception as e:
                        print(f"\u274c Error updating custom_multiselect_single field '{field_name}': {e}")
            except Exception as e:
                print(f"❌ Error updating field {field_name}: {e}")
        try:
            save_button = None
            button_selectors = [
                "//button[contains(text(), 'Save')]",
                "//button[contains(text(), 'Update')]",
                "//button[contains(text(), 'Submit')]",
                "//button[contains(@class, 'save')]",
                "//button[contains(@class, 'update')]",
                "//button[contains(@class, 'submit')]",
                "//button[@type='submit']",
                "//button[@aria-label='Save']",
                "//button[@aria-label='Update']",
                "//button[@aria-label='Submit']",
                "//button[contains(@class, 'tw-bg-blue-700')]"
            ]
            for selector in button_selectors:
                try:
                    save_button = driver.find_element(By.XPATH, selector)
                    if save_button.is_displayed() and save_button.is_enabled():
                        break
                except:
                    continue
            if save_button and save_button.is_displayed() and save_button.is_enabled():
                for attempt in range(3):
                    try:
                        driver.execute_script("arguments[0].scrollIntoView();", save_button)
                        time.sleep(1)
                        save_button.click()
                        # Wait for toast/notification or URL change
                        old_url = driver.current_url
                        for _ in range(15):
                            toast = None
                            try:
                                toast = driver.find_element(By.XPATH, "//div[contains(@class, 'toast') or contains(@class, 'notification')]")
                            except:
                                pass
                            if toast and toast.is_displayed():
                                break
                            if driver.current_url != old_url:
                                break
                            time.sleep(1)
                        time.sleep(2)
                        break
                    except Exception as e:
                        time.sleep(2)
            else:
                print("⚠️ Save button not found or not clickable by any selector.")
        except Exception as e:
            print("⚠️ Save button not found or not clickable:", e)
except Exception as e:
    pass
finally:
    driver.quit()
