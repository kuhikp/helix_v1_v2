import sys
print("PYTHON EXECUTABLE:", sys.executable)
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
import json
import re
import sqlite3
logging.basicConfig(level=logging.INFO)

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
    except Exception as e:
        logging.error(f"Dropdown selection failed for {option_text}: {e}")

# Load form data from config file
with open('site_manager/webbuilder_site_creation_config.json', 'r', encoding='utf-8') as jsonfile:
    form_data = json.load(jsonfile)

# Start Chrome WebDriver
driver = webdriver.Chrome()
driver.get("https://webbuilder.pfizer/webbuilder/create")
# Remove headless for GUI mode
# chrome_options.add_argument("--headless")
try:
    # Click Pfizer Network Login
    WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Pfizer Network Login')]"))
    ).click()
    # Enter credentials
    WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.NAME, "username"))
    ).send_keys("your_username")  # Replace with your username
    driver.find_element(By.NAME, "password").send_keys("your_password" + Keys.RETURN)  # Replace with your password
except Exception as e:
    logging.error("Login failed: %s", e)

try:
    # Click New Website
    WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'New Website')]"))
    ).click()
    # Click Start from scratch
    WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'choice-box')]//div[contains(text(), 'Start from scratch')]"))
    ).click()
    # Wait for form to load
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CLASS_NAME, "submit-information"))
    )
    # Fill out form fields
    WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.NAME, "name"))
    ).send_keys(form_data['NAME'])

    select_multiselect_option(driver, "webbuilder-dropdown-wrapper--team", form_data['TEAM'])
    select_multiselect_option(driver, "webbuilder-dropdown-wrapper--brands", form_data['BRAND'])

    Select(WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.NAME, "country"))
    )).select_by_visible_text(form_data['COUNTRY'])

    Select(WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.NAME, "helix_version"))
    )).select_by_visible_text(form_data['HELIX_COMPONENTS_VERSION'])

    WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.NAME, "domain"))
    ).send_keys(form_data['DOMAIN'])

    WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.NAME, "repository"))
    ).send_keys(form_data['EDISON_LITE_SITE_ID'])

    WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.NAME, "description"))
    ).send_keys(form_data['DESCRIPTION'])

    # Submit the form
    WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'btn-primary') and contains(text(), 'Continue')]"))
    ).click()
except Exception as e:
    logging.error("Form fill failed: %s", e)

# Wait for page to finish processing before quitting
try:
    WebDriverWait(driver, 15).until(
        lambda d: re.search(r'/website/\\d+/?$', d.current_url)
    )
except Exception as e:
    logging.warning(f"Timeout waiting for site creation page: {e}")
WebDriverWait(driver, 15).until(lambda d: d.execute_script('return document.readyState') == 'complete')

# After form submission and navigation
current_url = driver.current_url

# Extract site ID from URL
match = re.search(r'/website/(\d+)', current_url)
if match:
    site_id = int(match.group(1))
    logging.info(f"Extracted Webbuilder Site ID: {site_id}")
    correct_url = f"https://webbuilder.pfizer/builder/website/{site_id}/"
    print(correct_url)
else:
    logging.error(f"Webbuilder Site ID not found in URL: {current_url}")
driver.quit()
