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
import sys
import json
from collections import defaultdict
chrome_options = Options()
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)
wait = WebDriverWait(driver, 10)

PANEL_WAIT_TIME = 10
MULTISELECT_WAIT_TIME = 2

USERNAME = os.getenv('USERNAME')
PASSWORD = os.getenv('PASSWORD')

def write_status(status_file, status, progress, message=None):
    data = {'status': status, 'progress': progress}
    if message:
        data['message'] = message
    with open(status_file, 'w') as f:
        json.dump(data, f)

def main():
    try:
        driver.get('https://webbuilder.pfizer')
        time.sleep(2)
        try:
            driver.execute_script(
                "document.querySelector('div.tw-text-center a.tw-bg-gray-900').click();", 1
            )
            time.sleep(5)
            if 'authorization' in driver.current_url:
                driver.find_element(By.ID, "username").send_keys(USERNAME)
                driver.find_element(By.ID, "password").send_keys(PASSWORD)
                driver.find_element(By.ID, "submit_button").click()
                time.sleep(5)
        except Exception:
            input("Please login manually and press Enter to continue...")

        # Parse site_id from command line
        if len(sys.argv) > 1:
            site_id = sys.argv[1]
        else:
            print("Usage: script_to_export.py <site_id>")
            sys.exit(1)
        status_file = f"site_{site_id}_meta_export.status"
        output_csv = f"site_{site_id}_meta_export.csv"

        panel_types = [
              "left-sidebar-settings--optional-and-head-features",
              "left-sidebar-settings--performance",
              "left-sidebar-settings--developer",
              "left-sidebar-settings--metatags",
              "left-sidebar-settings--seo",
              "left-sidebar-settings--fonts",
              "left-sidebar-settings--main",
              "left-sidebar-settings--promotional-popup-manager",
              "left-sidebar-settings--external-link-manager",
              "left-sidebar-settings--analytics",
              "left-sidebar-settings--bootstrap",
              "left-sidebar-settings--data-source"
        ]

        input_file = "input.csv"
        output_folder = "Webbuilder_extracted_settings"
        os.makedirs(output_folder, exist_ok=True)

        # Expect input.csv to have a header: v1_site_id,v2_site_id
        with open(input_file, 'r', encoding='utf-8') as infile:
            reader = csv.DictReader(infile)
            rows = list(reader)
        total_sites = len(rows)
        for site_idx, row in enumerate(rows):
            v1_site_id = row.get('v1_site_id')
            v2_site_id = row.get('v2_site_id')
            if not v1_site_id or not v2_site_id:
                continue
            site_output_file = os.path.join(output_folder, f"{v1_site_id}.csv")
            field_data = defaultdict(lambda: {"values": set(), "type": None})
            custom_multiselect_rows = []
            total_panels = len(panel_types)
            for panel_idx, panel_type in enumerate(panel_types):
                try:
                    url = f"https://webbuilder.pfizer/builder/website/{v1_site_id}?panel={panel_type}"
                    driver.get(url)
                    time.sleep(PANEL_WAIT_TIME)
                    wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                    inputs = driver.find_elements(By.XPATH, "//input | //textarea | //select")
                    for inp in inputs:
                        name = inp.get_attribute('name') or inp.get_attribute('id') or ''
                        input_type = inp.get_attribute('type') or inp.tag_name
                        value = inp.get_attribute('value') or ''
                        label = ''
                        if inp.tag_name == 'select':
                            try:
                                label_elem = inp.find_element(By.XPATH, "preceding-sibling::label[1]")
                                label = label_elem.text.strip()
                            except:
                                label = ''
                            selected_option = ''
                            options = inp.find_elements(By.TAG_NAME, "option")
                            for opt in options:
                                if opt.is_selected() and not opt.get_attribute('disabled'):
                                    selected_option = opt.text.strip()
                                    break
                            if not selected_option:
                                for opt in options:
                                    if not opt.get_attribute('disabled'):
                                        selected_option = opt.text.strip()
                                        break
                            value = selected_option
                            field_name_export = inp.get_attribute('name') or inp.get_attribute('id')
                            if not field_name_export:
                                try:
                                    label_elem = None
                                    try:
                                        label_elem = inp.find_element(By.XPATH, "preceding-sibling::label[1]")
                                    except:
                                        try:
                                            field_div = inp.find_element(By.XPATH, "ancestor::div[contains(@class, 'field')]")
                                            label_elem = field_div.find_element(By.TAG_NAME, "label")
                                        except:
                                            pass
                                    if label_elem:
                                        label_for = label_elem.get_attribute('for')
                                        if label_for:
                                            field_name_export = label_for
                                except:
                                    pass
                            if not field_name_export:
                                field_name_export = (
                                    label.replace('*', '').replace(':', '').strip().replace(' ', '_').lower()
                                    if label else ''
                                )
                            key = (panel_type, label.strip(), field_name_export.strip(), v2_site_id)
                            field_data[key]["values"].add(value.strip())
                            field_data[key]["type"] = 'select'
                        elif input_type == 'hidden' and name.startswith('team_single_select'):
                            continue
                        else:
                            try:
                                label_elem = driver.find_element(By.XPATH, f"//label[@for='{inp.get_attribute('id')}']")
                                label = label_elem.text.strip()
                            except:
                                label = inp.get_attribute('aria-label') or ''
                            if input_type == 'checkbox':
                                value = 'checked' if inp.is_selected() else 'unchecked'
                                label = ''
                                try:
                                    label_elem = driver.find_element(By.XPATH, f"//label[@for='{inp.get_attribute('id')}']")
                                    label = label_elem.text.strip()
                                except:
                                    try:
                                        ancestor_label = inp.find_element(By.XPATH, "ancestor::label[1]")
                                        label = ancestor_label.text.strip()
                                    except:
                                        try:
                                            parent = inp.find_element(By.XPATH, "..")
                                            if parent.tag_name == 'label':
                                                label = parent.text.strip()
                                        except:
                                            label = inp.get_attribute('aria-label') or ''
                            key = (panel_type, label.strip(), name.strip(), v2_site_id)
                            field_data[key]["values"].add(value.strip())
                            field_data[key]["type"] = input_type
                    multiselect_tags_wraps = driver.find_elements(By.CLASS_NAME, "multiselect__tags-wrap")
                    for wrap in multiselect_tags_wraps:
                        tags = wrap.find_elements(By.CLASS_NAME, "multiselect__tag")
                        for tag in tags:
                            try:
                                label_span = tag.find_element(By.XPATH, './span[1]')
                                label_text = label_span.text.strip()
                                if label_text and not label_text.isdigit():
                                    parent_section = wrap.find_element(By.XPATH, "ancestor::section[1]")
                                    input_elems = parent_section.find_elements(By.XPATH, ".//input[@name]")
                                    field_name = ''
                                    for input_elem in input_elems:
                                        input_type = input_elem.get_attribute('type')
                                        if input_type in ['text', 'hidden'] and input_elem.get_attribute('name'):
                                            field_name = input_elem.get_attribute('name')
                                            break
                                    if not field_name and input_elems:
                                        field_name = input_elems[0].get_attribute('name')
                                    if not field_name:
                                        continue
                                    try:
                                        label_elem = parent_section.find_element(By.XPATH, ".//label")
                                        field_label = label_elem.text.strip()
                                    except:
                                        field_label = ''
                                    custom_multiselect_rows.append([
                                        panel_type,
                                        field_label,
                                        field_name,
                                        'custom_multiselect',
                                        label_text,
                                        v2_site_id
                                    ])
                                    time.sleep(MULTISELECT_WAIT_TIME)
                            except Exception:
                                continue
                    multiselect_containers = driver.find_elements(By.CLASS_NAME, "multiselect")
                    for container in multiselect_containers:
                        try:
                            single_elem = container.find_element(By.CLASS_NAME, "multiselect__single")
                            value_text = single_elem.text.strip()
                            if value_text:
                                parent_elem = container.find_element(By.XPATH, "..")
                                input_elem = None
                                input_elems = parent_elem.find_elements(By.XPATH, ".//input[@name]")
                                for inp in input_elems:
                                    input_type = inp.get_attribute('type')
                                    if input_type in ['text', 'hidden']:
                                        input_elem = inp
                                        break
                                field_label = ''
                                field_name = ''
                                label_elems = parent_elem.find_elements(By.TAG_NAME, "label")
                                for label_elem in label_elems:
                                    label_for = label_elem.get_attribute('for')
                                    if input_elem and label_for == input_elem.get_attribute('name'):
                                        field_label = label_elem.text.strip()
                                        field_name = label_for
                                        break
                                if not field_name:
                                    for label_elem in label_elems:
                                        label_for = label_elem.get_attribute('for')
                                        if label_for:
                                            field_label = label_elem.text.strip()
                                            field_name = label_for
                                            break
                                if not field_label and label_elems:
                                    field_label = label_elems[0].text.strip()
                                if not field_name and input_elems:
                                    field_name = input_elems[0].get_attribute('name')
                                if not field_label and field_name:
                                    field_label = field_name
                                if field_label.strip().lower() == value_text.strip().lower():
                                    field_label = field_name
                                if not field_name and not field_label:
                                    continue
                                custom_multiselect_rows.append([
                                    panel_type,
                                    field_label,
                                    field_name,
                                    'custom_multiselect_single',
                                    value_text,
                                    v2_site_id
                                ])
                        except Exception:
                            pass
                except Exception:
                    # Log error for this panel, but continue with next panel
                    continue
            # After all panels for this site, write output
            try:
                with open(site_output_file, 'w', newline='', encoding='utf-8') as outfile:
                    writer = csv.writer(outfile)
                    writer.writerow(['Panel Type', 'Field Label', 'Field Name', 'Type', 'Value', 'v2_site_id'])
                    # Collect all rows (main fields and custom_multiselect) into a single list
                    all_rows = []
                    for key, data in field_data.items():
                        panel_type, field_label, field_name, v2_site_id = key
                        field_label_sanitized = field_label.replace('\n', ' ').replace('\r', ' ') if field_label else ''
                        type_ = data["type"] if data["type"] else ''
                        if type_ == 'select' or type_ == 'select-one':
                            for value in sorted(data["values"]):
                                all_rows.append([panel_type, field_label_sanitized, field_name, type_, value, v2_site_id])
                        else:
                            values = ','.join(sorted(data["values"]))
                            all_rows.append([panel_type, field_label_sanitized, field_name, type_, values, v2_site_id])
                    # Add custom_multiselect rows
                    for row in custom_multiselect_rows:
                        all_rows.append(row)
                    # Sort all rows by panel_type only
                    all_rows_sorted = sorted(
                        all_rows,
                        key=lambda x: str(x[0])
                    )
                    for row in all_rows_sorted:
                        writer.writerow(row)
                # Copy/move output to project root for download
                import shutil
                shutil.copy(site_output_file, output_csv)
                # Mark as completed for this site
                write_status(status_file, 'completed', 100, 'Export completed')
            except Exception as e:
                write_status(status_file, 'error', 0, f"Error: {e}")
                raise
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
