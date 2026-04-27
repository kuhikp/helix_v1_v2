#!/usr/bin/env python3
"""
Selenium script for file upload functionality to Pfizer WebBuilder
Author: Generated for file upload automation
"""
import shutil
import os
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from dotenv import load_dotenv
import glob
from pathlib import Path

class PfizerWebBuilderUploader:
    def __init__(self, headless=False):
        """Initialize the uploader with Chrome driver"""
        load_dotenv()
        
        # Setup Chrome options
        self.chrome_options = Options()
        if headless:
            self.chrome_options.add_argument("--headless")
        self.chrome_options.add_argument("--no-sandbox")
        self.chrome_options.add_argument("--disable-dev-shm-usage")
        self.chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        self.chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        self.chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Initialize driver
        self.driver = webdriver.Chrome(options=self.chrome_options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        self.wait = WebDriverWait(self.driver, 20)
        
        # Get configuration from environment
        self.file_folder = os.getenv('FILEFOLDER', './file')
        self.instance_id = os.getenv('INSTANCE_ID', '')
        self.username = os.getenv('USERNAME', '')
        self.password = os.getenv('PASSWORD', '')
        
        if not self.instance_id:
            raise ValueError("INSTANCE_ID must be set in .env file")
    
    def safe_click(self, element):
        """Safely click an element, handling overlapping elements"""
        try:
            # First try normal click
            element.click()
            return True
        except WebDriverException as e:
            if "element click intercepted" in str(e):
                print("  - Click intercepted, trying alternative methods...")
                
                # Method 1: Scroll element into view and try again
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
                    time.sleep(1)
                    element.click()
                    return True
                except WebDriverException:
                    pass
                
                # Method 2: Use JavaScript click
                try:
                    self.driver.execute_script("arguments[0].click();", element)
                    return True
                except WebDriverException:
                    pass
                
                # Method 3: Try clicking at element center with offset
                try:
                    actions = ActionChains(self.driver)
                    actions.move_to_element(element).click().perform()
                    return True
                except WebDriverException:
                    pass
                
                print(f"  - All click methods failed: {e}")
                return False
            else:
                print(f"  - Click failed with different error: {e}")
                return False
    
    def get_files_to_upload(self):
        """Get list of files from the file folder"""
        file_folder_path = Path(self.file_folder)
        if not file_folder_path.exists():
            raise FileNotFoundError(f"File folder not found: {self.file_folder}")
        
        # Get all files (excluding directories)
        files = [f for f in file_folder_path.iterdir() if f.is_file()]
        
        if not files:
            raise FileNotFoundError(f"No files found in folder: {self.file_folder}")
        
        print(f"Found {len(files)} files to upload:")
        for i, file in enumerate(files, 1):
            print(f"  {i}. {file.name}")
        
        return files
    
    def login(self):
        """Handle the login process with SSO detection"""
        try:
            print("Step 1: Checking authentication status...")
            
            # First, try to navigate directly to the file manager to check if already logged in
            file_manager_url = f"https://webbuilder.pfizer/builder/website/{self.instance_id}?panel=left-sidebar-settings--file-manager"
            self.driver.get(file_manager_url)
            time.sleep(3)
            
            # Check if we're redirected to login page or already authenticated
            current_url = self.driver.current_url
            print(f"Current URL after navigation: {current_url}")
            
            if self.is_already_logged_in():
                print("User is already authenticated via SSO!")
                return
            
            print("Step 2: User not logged in, proceeding with authentication...")
            self.driver.get("https://webbuilder.pfizer/login")
            
            print("Step 3: Clicking Pfizer Network Login button...")
            # Wait for and click the Pfizer Network Login button
            login_button = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//a[contains(@href, '/sso/login')]"))
            )
            login_button.click()
            
            print("Step 4: Waiting for SSO redirect...")
            time.sleep(3)  # Wait for redirect
            
            # Check again if SSO automatically logged us in
            if self.is_already_logged_in():
                print("SSO authentication successful!")
                return
            
            # If username and password are provided, attempt to fill them
            if self.username and self.password:
                print("Step 5: Filling in credentials...")
                try:
                    username_field = self.wait.until(
                        EC.presence_of_element_located((By.NAME, "username"))
                    )
                    password_field = self.driver.find_element(By.NAME, "password")
                    
                    username_field.clear()
                    username_field.send_keys(self.username)
                    
                    password_field.clear()
                    password_field.send_keys(self.password)
                    
                    # Look for login/submit button
                    submit_button = self.driver.find_element(By.XPATH, "//button[@type='submit' or contains(@class, 'login') or contains(text(), 'Login') or contains(text(), 'Sign In')]")
                    submit_button.click()
                    
                    # Wait and check if login was successful
                    time.sleep(5)
                    if self.is_already_logged_in():
                        print("Credential-based login successful!")
                        return
                    
                except (TimeoutException, NoSuchElementException) as e:
                    print(f"Could not find username/password fields or login button: {e}")
                    print("Please login manually and press Enter to continue...")
                    input("Press Enter after logging in manually...")
            else:
                print("No credentials provided. Please login manually and press Enter to continue...")
                input("Press Enter after logging in manually...")
            
            print("Login completed successfully!")
            time.sleep(2)  # Wait for login to complete
            
        except Exception as e:
            print(f"Error during login: {e}")
            raise
    
    def is_already_logged_in(self):
        """Check if the user is already logged in by examining current URL and page content"""
        try:
            current_url = self.driver.current_url
            
            # Check if we're on a login page (indicates not logged in)
            login_indicators = [
                '/login',
                '/auth',
                '/sso/login',
                '/signin',
                'login.html',
                'authentication'
            ]
            
            # If URL contains login indicators, user is not logged in
            for indicator in login_indicators:
                if indicator.lower() in current_url.lower():
                    print(f"Login page detected in URL: {current_url}")
                    return False
            
            # Check for login form elements (indicates not logged in)
            try:
                login_forms = self.driver.find_elements(By.XPATH, "//form[contains(@action, 'login') or contains(@class, 'login')]")
                username_fields = self.driver.find_elements(By.NAME, "username")
                password_fields = self.driver.find_elements(By.NAME, "password")
                
                if login_forms or username_fields or password_fields:
                    print("Login form detected on page")
                    return False
            except (TimeoutException, NoSuchElementException, WebDriverException):
                pass
            
            # Check for authenticated content (webbuilder interface)
            try:
                # Look for webbuilder-specific elements that indicate successful login
                authenticated_elements = [
                    "//div[contains(@class, 'webbuilder')]",
                    "//div[contains(@id, 'webbuilder')]",
                    "//nav[contains(@class, 'navbar')]",
                    "//div[contains(@class, 'dashboard')]",
                    "//button[contains(text(), 'Add New File')]"
                ]
                
                for xpath in authenticated_elements:
                    elements = self.driver.find_elements(By.XPATH, xpath)
                    if elements:
                        print(f"Authenticated interface detected: {xpath}")
                        return True
                        
            except (TimeoutException, NoSuchElementException, WebDriverException):
                pass
            
            # Check if we're on the expected webbuilder domain and path
            if 'webbuilder.pfizer' in current_url and '/builder/website/' in current_url:
                print("On webbuilder interface - likely authenticated")
                return True
            
            print("Authentication status unclear, assuming not logged in")
            return False
            
        except Exception as e:
            print(f"Error checking authentication status: {e}")
            return False
    
    def navigate_to_file_manager(self):
        """Navigate to the file manager page"""
        try:
            print("Step 5: Ensuring we're on the file manager page...")
            file_manager_url = f"https://webbuilder.pfizer/builder/website/{self.instance_id}?panel=left-sidebar-settings--file-manager"
            
            # Check if we're already on the file manager page
            current_url = self.driver.current_url
            if file_manager_url not in current_url:
                print("Navigating to file manager...")
                self.driver.get(file_manager_url)
            else:
                print("Already on file manager page")
            
            # Wait for page to load
            time.sleep(3)
            print("File manager page ready!")
            
        except Exception as e:
            print(f"Error navigating to file manager: {e}")
            raise

    def check_file_exists(self, filename):
        """Check if a file already exists (optimized)"""
        try:
            # Find the file search input field
            search_input = self.wait.until(
                EC.presence_of_element_located((By.ID, "file-search-text-input"))
            )
            
            # Clear and search
            search_input.clear()
            search_input.send_keys(filename)
            
            # Reduced wait time
            time.sleep(1.5)
            
            # Check if file exists
            try:
                file_element = self.driver.find_element(
                    By.XPATH, f"//span[@class='filename' and text()='{filename}']"
                )
                if file_element:
                    print(f"  ⏭️  {filename} exists - skipping")
                    search_input.clear()
                    time.sleep(0.3)
                    return True
            except NoSuchElementException:
                pass
            
            # Clear search
            search_input.clear()
            time.sleep(0.3)
            return False
            
        except Exception as e:
            print(f"  - Error checking {filename}: {e}")
            return False       
        try:
            print(f"  - Checking if file '{filename}' already exists...")
            
            # Find the file search input field
            search_input = self.wait.until(
                EC.presence_of_element_located((By.ID, "file-search-text-input"))
            )
            
            # Clear the search field and enter filename
            search_input.clear()
            search_input.send_keys(filename)
            
            # Wait for search results to load and table to update
            time.sleep(3)
            
            # Additional wait to ensure table is fully loaded
            try:
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, "//tr[@class='tw-w-full file-tr-list']"))
                )
            except TimeoutException:
                print("  - Table rows not found, continuing with search...")
            
            # Look for the filename in the table using the correct selector
            try:
                # Check if file exists in the table using the span.filename selector
                file_element = self.driver.find_element(
                    By.XPATH, f"//span[@class='filename' and text()='{filename}']"
                )
                if file_element:
                    print(f"  - ✓ File '{filename}' already exists - SKIPPING")
                    # Clear the search field after finding the file
                    search_input.clear()
                    time.sleep(1)
                    return True
            except NoSuchElementException:
                # Try alternative selectors if exact match fails
                try:
                    file_element = self.driver.find_element(
                        By.XPATH, f"//span[@class='filename' and contains(text(), '{filename}')]"
                    )
                    if file_element:
                        print(f"  - ✓ File '{filename}' already exists - SKIPPING")
                        # Clear the search field after finding the file
                        search_input.clear()
                        time.sleep(1)
                        return True
                except NoSuchElementException:
                    print(f"  - File '{filename}' not found - will upload")
            
            # Clear the search field after checking
            search_input.clear()
            time.sleep(1)
            
            return False
            
        except Exception as e:
            print(f"  - Error checking file existence: {e}")
            # If we can't check, assume file doesn't exist and try to upload
            # But still try to clear the search field
            try:
                search_input = self.driver.find_element(By.ID, "file-search-text-input")
                search_input.clear()
            except (NoSuchElementException, WebDriverException):
                pass
            return False
    
    def handle_large_file_popup(self):
        """Handle the 'Large File Upload' popup that appears for large files"""
        try:
            print("  - Checking for 'Large File Upload' popup...")
            
            # Wait a moment for popup to appear after file selection
            time.sleep(3)
            
            # Look for various possible popup selectors
            popup_selectors = [
                "//div[contains(text(), 'Large File Upload')]",
                "//div[contains(@class, 'modal') and contains(., 'Large File Upload')]",
                "//div[contains(@class, 'popup') and contains(., 'Large File Upload')]",
                "//div[contains(@class, 'dialog') and contains(., 'Large File Upload')]",
                "//div[contains(@role, 'dialog') and contains(., 'Large File Upload')]",
                "//div[contains(text(), 'large file')]",  # Case insensitive
                "//*[contains(text(), 'Large File Upload')]"  # Any element
            ]
            
            popup_found = False
            # First try immediate detection
            for selector in popup_selectors:
                try:
                    popup_elements = self.driver.find_elements(By.XPATH, selector)
                    if popup_elements:
                        print("  - 'Large File Upload' popup detected!")
                        popup_found = True
                        break
                except (TimeoutException, NoSuchElementException, WebDriverException):
                    continue
            
            # If not found immediately, wait a bit more and try again
            if not popup_found:
                print("  - Waiting longer for popup to appear...")
                time.sleep(2)
                for selector in popup_selectors:
                    try:
                        popup_elements = self.driver.find_elements(By.XPATH, selector)
                        if popup_elements:
                            print("  - 'Large File Upload' popup detected after additional wait!")
                            popup_found = True
                            break
                    except (TimeoutException, NoSuchElementException, WebDriverException):
                        continue
            
            if popup_found:
                # Look for OK button with various possible selectors
                ok_button_selectors = [
                    "//button[contains(text(), 'OK')]",
                    "//button[contains(text(), 'Ok')]",
                    "//button[contains(text(), 'ok')]",
                    "//button[contains(@class, 'ok')]",
                    "//button[contains(@id, 'ok')]",
                    "//input[@type='button' and contains(@value, 'OK')]",
                    "//input[@type='button' and contains(@value, 'Ok')]",
                    "//button[contains(text(), 'Proceed')]",
                    "//button[contains(text(), 'Continue')]",
                    "//button[contains(text(), 'Accept')]",
                    "//div[contains(@class, 'modal')]//button[1]",  # First button in modal
                    "//div[contains(@class, 'popup')]//button[1]",  # First button in popup
                    "//div[contains(@class, 'dialog')]//button[1]",  # First button in dialog
                ]
                
                ok_clicked = False
                for selector in ok_button_selectors:
                    try:
                        ok_button = WebDriverWait(self.driver, 2).until(
                            EC.element_to_be_clickable((By.XPATH, selector))
                        )
                        if self.safe_click(ok_button):
                            print("  - Clicked OK button on 'Large File Upload' popup")
                            ok_clicked = True
                            time.sleep(1)  # Wait for popup to close
                            break
                    except (TimeoutException, NoSuchElementException):
                        continue
                
                if not ok_clicked:
                    print("  - Warning: Found popup but couldn't find OK button")
                    # Try pressing Enter as fallback
                    try:
                        self.driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ENTER)
                        print("  - Pressed Enter as fallback for popup")
                    except (TimeoutException, NoSuchElementException, WebDriverException):
                        print("  - Could not handle popup automatically")
            else:
                print("  - No 'Large File Upload' popup detected")
                
        except Exception as e:
            print(f"  - Error handling popup: {e}")
            # Continue anyway, popup handling is optional

    def copy_files_from_httrack(self, source_folder='css'):

    
        try:
            # Define source and destination paths
            base_dir = os.path.dirname(os.path.abspath(__file__))
            source_dir = os.path.join(base_dir, 'site_manager', 'static', 'httrack_export', source_folder)
            dest_dir = os.path.join(base_dir, 'site_manager', 'static', 'files')
            
            print(f"\n=== Copying files from httrack_export/{source_folder} ===")
            print(f"Source: {source_dir}")
            print(f"Destination: {dest_dir}")
            
            # Check if source directory exists
            if not os.path.exists(source_dir):
                print(f"❌ Source directory does not exist: {source_dir}")
                return 0, 0
            
            # Create destination directory if it doesn't exist
            os.makedirs(dest_dir, exist_ok=True)
            print(f"✓ Destination directory ready")
            
            # Get all files from source directory
            source_path = Path(source_dir)
            files = [f for f in source_path.iterdir() if f.is_file()]
            
            if not files:
                print(f"⚠️  No files found in {source_dir}")
                return 0, 0
            
            print(f"Found {len(files)} files to copy")
            
            copied_count = 0
            skipped_count = 0
            
            for file in files:
                dest_file = os.path.join(dest_dir, file.name)
                
                # Check if file already exists in destination
                if os.path.exists(dest_file):
                    print(f"  ⏭️  Skipped {file.name} (already exists)")
                    skipped_count += 1
                else:
                    shutil.copy2(file, dest_file)
                    print(f"  ✓ Copied {file.name}")
                    copied_count += 1
            
            print(f"\n=== Copy Summary ===")
            print(f"Total files: {len(files)}")
            print(f"Copied: {copied_count}")
            print(f"Skipped: {skipped_count}")
            
            return copied_count, skipped_count
            
        except Exception as e:
            print(f"❌ Error copying files: {e}")
            return 0, 0
      
    def upload_batch(self, file_paths, fast_mode=True):
        """Upload a batch of up to 10 files at once"""
        try:
            file_names = [f.name for f in file_paths]
            print(f"Uploading batch of {len(file_paths)} files: {', '.join(file_names)}")
            
            # Small initial wait
            time.sleep(0.5 if fast_mode else 2)
            
            # Click "Add New File" button
            add_file_button = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Add New File') or contains(@class, 'add-file') or contains(@aria-label, 'Add New File')]"))
            )
            if not self.safe_click(add_file_button):
                raise WebDriverException("Failed to click 'Add New File' button")
            
            # Wait after Add New File
            time.sleep(0.5 if fast_mode else 2)
            
            # Click "Browse Files" button
            browse_button = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'browse files') or contains(text(), 'Browse Files') or contains(@class, 'browse')]"))
            )
            if not self.safe_click(browse_button):
                raise WebDriverException("Failed to click 'Browse Files' button")
            
            # Wait after Browse
            time.sleep(0.3 if fast_mode else 1)
            
            # Find file input and send all file paths at once (newline-separated for multi-select)
            file_input = self.wait.until(
                EC.presence_of_element_located((By.XPATH, "//input[@type='file']"))
            )
            all_paths = "\n".join(str(f.absolute()) for f in file_paths)
            file_input.send_keys(all_paths)
            
            # Handle potential "Large File Upload" popup
            self.handle_large_file_popup()
            
            # Wait before Save
            time.sleep(0.5 if fast_mode else 2)
            
            # Click Save button
            save_button = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Save') or contains(@class, 'save')]"))
            )
            if not self.safe_click(save_button):
                raise WebDriverException("Failed to click 'Save' button")
            
            # Wait for upload to complete (longer for batch)
            time.sleep(3 if fast_mode else 5)
            
            print(f"✓ Uploaded batch: {', '.join(file_names)}")
            return len(file_paths), 0
            
        except Exception as e:
            print(f"✗ Error uploading batch: {e}")
            return 0, len(file_paths)
        
    def upload_all_files_in_batches(self, batch_size=10, pause_between_batches=3, fast_mode=True):
        """Upload all files in batches of up to 10 files at a time"""
        files = self.get_files_to_upload()
        total_files = len(files)

        successful_uploads = 0
        failed_uploads = 0

        # WebBuilder supports max 10 files per upload
        if batch_size <= 0 or batch_size > 10:
            batch_size = 10

        total_batches = (total_files + batch_size - 1) // batch_size
        print(f"\n=== Batch upload: {total_files} files, {total_batches} batches of {batch_size} ===")

        for batch_index in range(total_batches):
            start = batch_index * batch_size
            end = min(start + batch_size, total_files)
            batch_files = files[start:end]

            print(f"\n=== Batch {batch_index + 1}/{total_batches} ({len(batch_files)} files) ===")

            try:
                succeeded, failed = self.upload_batch(batch_files, fast_mode=fast_mode)
                successful_uploads += succeeded
                failed_uploads += failed
            except Exception as e:
                print(f"✗ Batch {batch_index + 1} failed: {e}")
                failed_uploads += len(batch_files)

            # Pause between batches
            if batch_index < total_batches - 1:
                print(f"Waiting {pause_between_batches}s before next batch...")
                time.sleep(pause_between_batches)

        print("\n=== Upload Summary ===")
        print(f"Total files processed: {total_files}")
        print(f"Successful uploads: {successful_uploads}")
        print(f"Failed uploads: {failed_uploads}")

        return successful_uploads, failed_uploads

    def close(self):
        """Close the browser"""
        if self.driver:
            self.driver.quit()
            print("Browser closed.")

def main():
    """Main function to run the file upload process"""
    uploader = None
    
    try:
        print("=== Pfizer WebBuilder File Upload Script ===\n")
        
        # Initialize uploader
        uploader = PfizerWebBuilderUploader(headless=False)
        # Copy files from httrack_export directories to files directory
        print("Step 0: Copying files from httrack_export...")
        
        total_copied = 0
        total_skipped = 0
        
        # Copy CSS files
        print("\n--- Copying CSS files ---")
        copied, skipped = uploader.copy_files_from_httrack('css')
        total_copied += copied
        total_skipped += skipped
        
        # Copy JS files
        print("\n--- Copying JS files ---")
        copied, skipped = uploader.copy_files_from_httrack('js')
        total_copied += copied
        total_skipped += skipped

        # Copy image files
        print("\n--- Copying image files ---")
        copied, skipped = uploader.copy_files_from_httrack('images')
        total_copied += copied
        total_skipped += skipped
        
        # Optional: Copy fonts if needed
        # print("\n--- Copying font files ---")
        # copied, skipped = uploader.copy_files_from_httrack('fonts')
        # total_copied += copied
        # total_skipped += skipped
        
        print(f"\n=== Total Files Copied: {total_copied}, Skipped: {total_skipped} ===\n")
        
        if total_copied == 0 and total_skipped == 0:
            print("⚠️  No files were copied. Check source directories.")
        
        # Login process
        uploader.login()
        
        # Navigate to file manager
        uploader.navigate_to_file_manager()
        
        # Upload all files in batches of 10
        batch_size = int(os.getenv("UPLOAD_BATCH_SIZE", "10"))
        pause_between_batches = int(os.getenv("BATCH_PAUSE_SECONDS", "5"))

        successful, failed = uploader.upload_all_files_in_batches(
            batch_size=batch_size,
            pause_between_batches=pause_between_batches
        )        
        if failed == 0 and successful > 0:
            print("\n🎉 All files uploaded successfully!")
        else:
            print(f"\n⚠️  Upload completed with {failed} failures.")
        
    except KeyboardInterrupt:
        print("\n⚠️  Script interrupted by user.")
    except Exception as e:
        print(f"\n❌ Script failed with error: {e}")
    finally:
        if uploader:
            uploader.close()

if __name__ == "__main__":
    main()