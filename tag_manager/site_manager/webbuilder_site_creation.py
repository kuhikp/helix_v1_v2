import sys
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import json
import re
import os
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)

# Load environment variables from .env file
load_dotenv()

# Fetch credentials from environment
USERNAME = os.environ.get('USERNAME')
PASSWORD = os.environ.get('PASSWORD')
if not USERNAME or not PASSWORD:
    raise Exception("USERNAME and PASSWORD must be set in your .env file.")

def select_multiselect_option(driver, wrapper_id, option_text):
    """Selects an option from a custom multiselect dropdown."""
    try:
        # Open dropdown wrapper
        wrapper = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, wrapper_id))
        )
        wrapper.click()
        # Click to show options
        select_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CLASS_NAME, "multiselect__select"))
        )
        select_btn.click()
        # Select the desired option
        option = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((
                By.XPATH,
                f"//span[contains(@class, 'multiselect__option') and contains(., '{option_text}')]"
            ))
        )
        option.click()
        # Close the dropdown
        close_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(@class, 'btn-primary') and contains(text(), 'Close')]"))
        )
        close_btn.click()
        logging.info(f"Selected option: {option_text}")
    except Exception as e:
        logging.error(f"Dropdown selection failed for {option_text}: {e}")

def get_field_value(fields, field_name):
    """Extract field value from the fields array by field_name.
    Handles both formats: lowercase 'field_name' and capitalized 'Field Name'"""
    for field in fields:
        # Try lowercase keys first (standard format)
        if field.get('field_name') == field_name:
            value = field.get('value', '')
            # Return value if it's not empty, otherwise try default_value
            if value:
                return value
            return field.get('default_value', '')
        # Try capitalized keys (CSV-to-JSON format)
        if field.get('Field Name') == field_name:
            value = field.get('Value', '')
            if value:
                return value
            return ''
    return ''

def get_field_value_by_label(fields, field_label):
    """Extract field value from the fields array by field_label.
    Handles both formats: lowercase 'field_label' and capitalized 'Field Label'"""
    for field in fields:
        # Try lowercase keys first (standard format)
        if field.get('field_label') == field_label:
            value = field.get('value', '')
            if value:
                return value
            return field.get('default_value', '')
        # Try capitalized keys (CSV-to-JSON format)
        if field.get('Field Label') == field_label:
            value = field.get('Value', '')
            if value:
                return value
            return ''
    return ''
    return ''

# Get JSON file path from command line or environment variable
if len(sys.argv) > 1:
    json_path = sys.argv[1]
else:
    json_path = os.environ.get('JSONPATH')
    if not json_path:
        print("Usage: python webbuilder_site_creation_from_export.py <json_file_path>")
        print("Or set JSONPATH environment variable")
        sys.exit(1)

# Load exported site data
logging.info(f"Loading site data from: {json_path}")
with open(json_path, 'r', encoding='utf-8') as jsonfile:
    site_data = json.load(jsonfile)

# Handle both formats: array (CSV-to-JSON) or dict with 'fields' key
if isinstance(site_data, list):
    # CSV-to-JSON format: array of field objects
    fields = site_data
    site_info = {}
    # Extract site_id from first field if available
    if fields:
        site_info['v2_site_id'] = fields[0].get('v2_site_id', '')
        # Try to find domain field
        for field in fields:
            if field.get('Field Name') == 'domain' or field.get('field_name') == 'domain':
                site_info['domain'] = field.get('Value') or field.get('value', '')
                break
else:
    # Standard format: dict with 'fields' array
    fields = site_data.get('fields', [])
    site_info = site_data.get('_info', {})

# Extract form data from the exported JSON
site_name = get_field_value(fields, 'site_name') or site_info.get('domain', 'Migrated Site')
domain = get_field_value(fields, 'domain') or site_info.get('domain', 'migrated-site.pfizer.com')
site_description = get_field_value(fields, 'site_description') or get_field_value(fields, 'description') or 'Migrated website'

# Try to get brand and country from fields
brand = get_field_value(fields, 'brand') or get_field_value_by_label(fields, 'Brand') or 'Pfizer'
country_code = get_field_value(fields, 'country') or 'US'
edison_site_id = get_field_value(fields, 'edison_lite_site_id') or ''

logging.info(f"Extracted - Site: {site_name}, Domain: {domain}, Brand: {brand}, Country: {country_code}")

# Map country code to full name (add more mappings as needed)
country_mapping = {
    'US': 'United States',
    'BR': 'Brazil',
    'GB': 'United Kingdom',
    'CA': 'Canada',
    'DE': 'Germany',
    'FR': 'France',
    'IT': 'Italy',
    'ES': 'Spain',
    'MX': 'Mexico',
    'JP': 'Japan',
    'CN': 'China',
    'IN': 'India',
    'AU': 'Australia',
}
country_name = country_mapping.get(country_code, 'United States')

form_data = {
    'NAME': site_name,
    'TEAM': "TCS Development Team",  # Default team
    'BRAND': "ABRILADA",
    'COUNTRY': country_name,
    'HELIX_COMPONENTS_VERSION': "Helix V2",  # Default to V2
    'DOMAIN': domain,
    # 'EDISON_LITE_SITE_ID': edison_site_id,
    'DESCRIPTION': site_description
}

logging.info(f"Form data prepared: {form_data}")

# Start Chrome WebDriver
chrome_options = Options()
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

# Try to initialize ChromeDriver with error handling
try:
    # Try system chromedriver first
    try:
        driver = webdriver.Chrome(options=chrome_options)
        logging.info("Using system ChromeDriver")
    except:
        # Fall back to ChromeDriverManager
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        logging.info("Using ChromeDriverManager")
except Exception as driver_error:
    logging.error(f"ChromeDriver initialization failed: {driver_error}")
    print("\n" + "="*60)
    print("CHROMEDRIVER ERROR")
    print("="*60)
    print("If you see 'Can not connect to the Service' error:")
    print("1. Run: xattr -d com.apple.quarantine /Users/nishavaghela/.wdm/drivers/chromedriver/mac64/*/chromedriver-mac-arm64/chromedriver")
    print("2. Or manually approve ChromeDriver in System Settings > Privacy & Security")
    print("3. Then run this script again")
    print("="*60 + "\n")
    raise

try:
    driver.get("https://webbuilder.pfizer/webbuilder/create")
    logging.info("Navigated to Webbuilder")
    
    import time
    time.sleep(3)
    
    # Check if already on create page (already logged in)
    if 'create' in driver.current_url or 'New Website' in driver.page_source:
        logging.info("Already logged in, skipping login step")
    else:
        # Login
        try:
            # Click Pfizer Network Login
            login_button = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Pfizer Network Login')]"))
            )
            login_button.click()
            logging.info("Clicked Pfizer Network Login")
            
            time.sleep(3)  # Wait for redirect
            
            # Try multiple possible username field names
            username_field = None
            for field_name in ["pf.username", "username", "user", "email"]:
                try:
                    username_field = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.NAME, field_name))
                    )
                    logging.info(f"Found username field: {field_name}")
                    break
                except:
                    continue
            
            if username_field:
                username_field.clear()
                username_field.send_keys(USERNAME)
                logging.info(f"Entered username: {USERNAME}")
                
                # Try multiple possible password field names
                password_field = None
                for field_name in ["pf.pass", "password", "pass", "pwd"]:
                    try:
                        password_field = driver.find_element(By.NAME, field_name)
                        logging.info(f"Found password field: {field_name}")
                        break
                    except:
                        continue
                
                if password_field:
                    password_field.clear()
                    password_field.send_keys(PASSWORD)
                    logging.info("Entered password")
                    
                    # Submit login form
                    password_field.send_keys(Keys.RETURN)
                    logging.info("Submitted login form")
                    
                    # Wait for redirect after login
                    time.sleep(15)
                    logging.info(f"Current URL after login: {driver.current_url}")
                else:
                    raise Exception("Password field not found")
            else:
                raise Exception("Username field not found")
        except Exception as e:
            logging.error(f"Login failed: {e}")
            # Check if we're already logged in
            if 'webbuilder.pfizer' in driver.current_url and 'authorization' not in driver.current_url and 'login' not in driver.current_url.lower():
                logging.info("Already logged in (detected by URL), continuing...")
            else:
                logging.error("ERROR: Automatic login failed. Please check credentials in .env file.")
                logging.error(f"Current URL: {driver.current_url}")
                raise Exception("Automatic login failed and manual login is not available in automated mode")
    
    # After login, navigate to create page if not already there
    time.sleep(2)
    current_url = driver.current_url
    logging.info(f"Current URL: {current_url}")
    
    if '/create' not in current_url and '/new' not in current_url:
        logging.info("Not on create page, navigating...")
        driver.get("https://webbuilder.pfizer/webbuilder/create")
        time.sleep(3)
        logging.info(f"Navigated to create page: {driver.current_url}")

    # Click Start from scratch
    scratch_clicked = False
    for attempt in range(3):
        try:
            logging.info(f"Attempting to click 'Start from scratch' (attempt {attempt + 1})")
            
            # Multiple selectors to try
            selectors = [
                "//div[contains(@class, 'choice-box')]//div[contains(text(), 'Start from scratch')]",
                "//*[contains(text(), 'Start from scratch')]",
                "//button[contains(., 'Start from scratch')]",
                "//a[contains(., 'Start from scratch')]",
                "//div[contains(., 'scratch')]",
                "//*[contains(@class, 'scratch')]",
            ]
            
            for selector in selectors:
                try:
                    elements = driver.find_elements(By.XPATH, selector)
                    for elem in elements:
                        if 'start' in elem.text.lower() and 'scratch' in elem.text.lower():
                            driver.execute_script("arguments[0].scrollIntoView(true);", elem)
                            time.sleep(1)
                            
                            # Try regular click first
                            try:
                                elem.click()
                            except:
                                # Fallback to JavaScript click
                                driver.execute_script("arguments[0].click();", elem)
                            
                            logging.info(f"Clicked 'Start from scratch' using selector: {selector}")
                            scratch_clicked = True
                            time.sleep(3)
                            break
                except:
                    continue
                
                if scratch_clicked:
                    break
            
            if scratch_clicked:
                break
                
            time.sleep(2)
        except Exception as e:
            logging.error(f"Attempt {attempt + 1} failed: {e}")
            if attempt < 2:
                time.sleep(2)
    
    if not scratch_clicked:
        logging.warning("Could not automatically click 'Start from scratch', but continuing...")
        time.sleep(5)  # Give time to manually click if needed
    
    # Wait for form to load
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CLASS_NAME, "submit-information"))
        )
        logging.info("Form loaded")
        time.sleep(2)
    except Exception as e:
        logging.warning(f"Form class not found, trying alternative: {e}")
        time.sleep(3)  # Give form time to load anyway
    
    # Fill out form fields
    try:
        name_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "name"))
        )
        name_field.clear()
        name_field.send_keys(form_data['NAME'])
        logging.info(f"✓ Entered site name: {form_data['NAME']}")
    except Exception as e:
        logging.error(f"✗ Failed to enter site name: {e}")

    try:
        select_multiselect_option(driver, "webbuilder-dropdown-wrapper--team", form_data['TEAM'])
        logging.info(f"✓ Selected team: {form_data['TEAM']}")
    except Exception as e:
        logging.error(f"✗ Failed to select team: {e}")
    
    try:
        select_multiselect_option(driver, "webbuilder-dropdown-wrapper--brands", form_data['BRAND'])
        logging.info(f"✓ Selected brand: {form_data['BRAND']}")
    except Exception as e:
        logging.error(f"✗ Failed to select brand: {e}")

    try:
        country_select = Select(WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "country"))
        ))
        country_select.select_by_visible_text(form_data['COUNTRY'])
        logging.info(f"✓ Selected country: {form_data['COUNTRY']}")
    except Exception as e:
        logging.error(f"✗ Failed to select country: {e}")

    try:
        helix_select = Select(WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "helix_version"))
        ))
        helix_select.select_by_visible_text(form_data['HELIX_COMPONENTS_VERSION'])
        logging.info(f"✓ Selected Helix version: {form_data['HELIX_COMPONENTS_VERSION']}")
    except Exception as e:
        logging.error(f"✗ Failed to select Helix version: {e}")

    try:
        domain_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "domain"))
        )
        domain_field.clear()
        domain_field.send_keys(form_data['DOMAIN'])
        logging.info(f"✓ Entered domain: {form_data['DOMAIN']}")
    except Exception as e:
        logging.error(f"✗ Failed to enter domain: {e}")

    try:
        repo_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "repository"))
        )
        repo_field.clear()
        repo_field.send_keys(form_data['EDISON_LITE_SITE_ID'])
        logging.info(f"✓ Entered Edison Lite Site ID")
    except Exception as e:
        logging.error(f"✗ Failed to enter repository: {e}")

    try:
        desc_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "description"))
        )
        desc_field.clear()
        desc_field.send_keys(form_data['DESCRIPTION'])
        logging.info(f"✓ Entered description")
    except Exception as e:
        logging.error(f"✗ Failed to enter description: {e}")

    # Submit the form
    submit_clicked = False
    for attempt in range(3):
        try:
            logging.info(f"Attempting to submit form (attempt {attempt + 1})")
            
            selectors = [
                "//button[contains(@class, 'btn-primary') and contains(text(), 'Continue')]",
                "//button[contains(text(), 'Continue')]",
                "//button[@type='submit']",
                "//*[contains(text(), 'Continue')]"
            ]
            
            for selector in selectors:
                try:
                    submit_button = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.XPATH, selector))
                    )
                    driver.execute_script("arguments[0].scrollIntoView(true);", submit_button)
                    time.sleep(1)
                    
                    try:
                        submit_button.click()
                    except:
                        driver.execute_script("arguments[0].click();", submit_button)
                    
                    logging.info(f"✓ Clicked Continue button using: {selector}")
                    submit_clicked = True
                    break
                except:
                    continue
            
            if submit_clicked:
                break
                
            time.sleep(2)
        except Exception as e:
            logging.error(f"Submit attempt {attempt + 1} failed: {e}")
            if attempt < 2:
                time.sleep(2)
    
    if not submit_clicked:
        logging.error("✗ Could not click Continue button automatically")
        time.sleep(5)

    # Wait for page to finish processing
    try:
        WebDriverWait(driver, 30).until(
            lambda d: re.search(r'/website/\d+/?$', d.current_url)
        )
    except Exception as e:
        logging.warning(f"Timeout waiting for site creation page: {e}")
    
    WebDriverWait(driver, 15).until(lambda d: d.execute_script('return document.readyState') == 'complete')

    # Extract site ID from URL
    current_url = driver.current_url
    match = re.search(r'/website/(\d+)', current_url)
    
    if match:
        site_id = int(match.group(1))
        logging.info(f"✓ Webbuilder Site Created Successfully!")
        logging.info(f"✓ Extracted Webbuilder Site ID: {site_id}")
        builder_url = f"https://webbuilder.pfizer/builder/website/{site_id}/"
        print("\n" + "="*60)
        print(f"SUCCESS! Site created with ID: {site_id}")
        print(f"Builder URL: {builder_url}")
        # print("="*60 + "\n")
        
        # Update the source JSON file with new site ID
        try:
            logging.info(f"Updating {json_path} with new site ID: {site_id}")
            
            # Re-read the original JSON file
            with open(json_path, 'r', encoding='utf-8') as f:
                original_data = json.load(f)
            
            old_site_id = None
            # Update v2_site_id based on format
            if isinstance(original_data, list):
                # CSV-to-JSON format: update all v2_site_id fields
                updated_count = 0
                for item in original_data:
                    if 'v2_site_id' in item:
                        if old_site_id is None:
                            old_site_id = item['v2_site_id']
                        item['v2_site_id'] = str(site_id)
                        updated_count += 1
                logging.info(f"✓ Updated {updated_count} v2_site_id fields from '{old_site_id}' to '{site_id}'")
            else:
                # Standard format: update _info section
                if '_info' in original_data:
                    old_site_id = original_data['_info'].get('v2_site_id')
                    original_data['_info']['v2_site_id'] = str(site_id)
                # Also update all fields
                updated_count = 0
                if 'fields' in original_data:
                    for field in original_data['fields']:
                        if 'v2_site_id' in field:
                            field['v2_site_id'] = str(site_id)
                            updated_count += 1
                logging.info(f"✓ Updated v2_site_id from '{old_site_id}' to '{site_id}' in {updated_count} fields")
            
            # Write back to file
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(original_data, f, indent=2, ensure_ascii=False)
            
            logging.info(f"✓ Saved updated JSON to: {json_path}")
        except Exception as e:
            logging.error(f"Could not update JSON file: {e}")
            import traceback
            traceback.print_exc()
        
    #     # Update input.csv with new mapping
    #     try:
    #         import csv
    #         # input_csv = os.path.join(os.path.dirname(os.path.abspath(__file__)), "input.csv")
    #         v1_site_id = site_info.get('v2_site_id', '').split('-')[0] if site_info else ''
            
    #         if not v1_site_id:
    #             # Try to extract from filename
    #             v1_site_id = os.path.basename(json_path).replace('.json', '')
            
    #         # Read existing data
    #         rows = []
    #         try:
    #             with open(input_csv, 'r', encoding='utf-8') as f:
    #                 reader = csv.DictReader(f)
    #                 rows = list(reader)
    #         except FileNotFoundError:
    #             pass
            
    #         # Add new mapping
    #         rows.append({'v1_site_id': v1_site_id, 'v2_site_id': str(site_id)})
            
    #         # Write back
    #         with open(input_csv, 'w', newline='', encoding='utf-8') as f:
    #             writer = csv.DictWriter(f, fieldnames=['v1_site_id', 'v2_site_id'])
    #             writer.writeheader()
    #             writer.writerows(rows)
            
    #         logging.info(f"✓ Updated input.csv: {v1_site_id} -> {site_id}")
    #     except Exception as e:
    #         logging.warning(f"Could not update input.csv: {e}")
    else:
        logging.error(f"✗ Webbuilder Site ID not found in URL: {current_url}")
        print("\n" + "="*60)
        print(f"ERROR: Could not extract site ID from URL")
        print(f"Current URL: {current_url}")
        print("="*60 + "\n")

except Exception as e:
    logging.error(f"Error during site creation: {e}")
    print(f"\n✗ ERROR: {e}\n")
