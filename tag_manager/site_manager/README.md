# Helix Tag Manager Meta Export/Import & Page/Block/Files Migration Utility

## Overview
This project provides utilities for exporting/importing meta data, migrating pages, and handling file/block migration between v1 and v2 Helix sites. It includes Django views, user-facing forms, and Python scripts to automate and streamline these processes.

## Key Features
- **Export Meta**: Trigger an export by providing v1 and v2 site IDs. The system writes these to `input.csv`, runs the export script, and allows you to download the resulting CSV.
- **Import Meta**: Upload a CSV file to import meta data into the system using the import script.
- **Page Migration**: Scripts to automate migration of pages from v1 JSON exports to v2 instances.
- **File/Block Migration**: Scripts to automate file and block migration with batch and duplicate handling.

## File Structure
- `script_to_export.py`: Python script to export meta data based on `input.csv`.
- `script_import_data.py`: Python script to import meta data from a CSV file.
- `import_pages_func.py`: Script to automate page migration from v1 to v2.
- `import_files_func.py`: Script to automate file migration from v1 to v2.
- `requirements.txt`: Python dependencies for the scripts (see below).
- `site_manager/views.py`: Django views for handling export/import requests, status polling, and file downloads.
- `site_manager/templates/site_manager/site_meta_list.html`: Main UI for triggering export/import and viewing meta details.

## Prerequisites
- Python 3.8 or higher
- Google Chrome browser installed
- Django project setup and running
- All scripts require a valid `.env` file with credentials
- Export of V2 site data to be kept in location site_manager/static/block_import

### For File Migration
1. Download all the files from the V1 site to your local machine.
2. Upload files in batches of 10 to the V2 site.
3. Then run the file migration script (`import_files_func.py`).

### For Block Migration
- If the script fails or the browser closes unexpectedly, you must manually delete any blocks created in the V2 site before re-running the script. Otherwise, duplicate blocks will be created.
- **Note:** The team is working on this limitation and will push an update soon.

### Limitations
- Manual intervention may be required for complex/custom fields, login, or UI changes.
- Duplicate blocks may be created if not cleaned up after a failed run.
- Homepage migration is skipped by default to avoid overwriting.

Example `.env` file:
```
SITENAME="webbuilder.pfizer"
INSTANCE_ID=21822
USERNAME=Pfizer Network ID
PASSWORD=Pfizer Network Password
```

## Page Migration Script Details

### What the Script Does
For Each Page:
- **Parse JSON**: Extracts title, slug, language, brand, indication, therapeutic area, HTML, CSS
- **Check Duplicates**: Searches if page already exists (skips if found)
- **Create Page**: Opens menu, clicks "+ ADD PAGE", fills in details, submits form
- **Insert Content**: Edits page, inserts HTML/CSS, saves
- **Move to Next**: Repeats for the next page

**Final Output:**
- ✓ Successfully migrated pages
- ⊘ Skipped pages (already exist)
- ✗ Failed pages (with error reasons)

### Important Notes
- **Cross-Platform Compatibility**: Automatic OS detection, keyboard shortcuts, and path handling
- **ChromeDriver**: WebDriver Manager downloads the correct driver for your OS
- **Browser Behavior**: Chrome opens automatically, controlled by the script, stays open for 60 seconds after completion
- **Login Handling**: Handles SSO/federated login automatically; check credentials if login fails
- **Homepage**: Homepage (slug='index') is skipped by default
- **Error Handling**: Script continues on errors, logs all issues, and summarizes at the end
- **Performance**: Processing 30+ pages may take several minutes

### Troubleshooting
- **ChromeDriver Issues**: Ensure internet connection for webdriver-manager
- **Login Fails**: Verify credentials in `.env`, check for SSO
- **Pages Not Created**: Check for duplicates, verify directory path, review console output
- **HTML/CSS Not Inserted**: Check browser console for JS errors, ensure "Edit Code" is clickable
- **Script Stops Unexpectedly**: Review console output, check selectors, try single page mode

### Advanced Configuration
- **Customizing Selectors**: Edit the `SELECTORS` dictionary in the script as needed
- **Adjusting Timeouts**: Increase `time.sleep()` values if pages load slowly

### Best Practices
- Test with a single page before batch processing
- Backup V1 and V2 data
- Monitor browser during migration
- Verify migrated pages manually
- Save console output for troubleshooting

### Support
If you encounter issues:
1. Check the console output for error messages
2. Review the troubleshooting section above
3. Try single page mode to isolate the problem
4. Verify all configuration settings


## Meta Export/Import Script Details

### Panels Exported and Imported
The export and import scripts handle the following Webbuilder panels by default:
- left-sidebar-settings--optional-and-head-features
- left-sidebar-settings--performance
- left-sidebar-settings--developer
- left-sidebar-settings--metatags
- left-sidebar-settings--seo
- left-sidebar-settings--promotional-popup-manager
- left-sidebar-settings--external-link-manager
- left-sidebar-settings--analytics
- left-sidebar-settings--bootstrap
- left-sidebar-settings--data-source

> **Note:** Below panels are not included by default.
> - left-sidebar-settings--website (Edison lite site id will vary between v1 and v2)
> - left-sidebar-settings--fonts (custom fonts may not transfer)
> - left-sidebar-settings--grv (It can be added if grv is enabled)

### Manual Intervention & Limitations
- **Login:** If automated login fails, the script will prompt you to log in manually and press Enter to continue.
- **Complex/Custom Fields:** Some custom or complex multiselects, hidden fields, or fields without clear names/IDs may not be handled perfectly. Manual review and adjustment may be required after import.
- **Panels Not Included:** Panels that are commented out or not listed in the script are not processed. Add them to the script if needed.
- **Fields requiring manual input:**
  - Enable GRV (optional-and head features)
  - Remove special characters from page slugs (optional-and head features)
  - Enable multilingual (multilingual-manager)
  - ADD PRECONNECT TAGS (performance)
- **UI Changes:** If the Webbuilder UI changes, the scripts may require updates to selectors or logic. Manual intervention may be needed if errors occur.

### Workflow Summary
1. **Export:**
   - For each v1 site ID in `input.csv`, the script visits each panel and exports all field values to a CSV in `Webbuilder_extracted_settings/`.
2. **Import:**
   - For each v2 site ID and panel, the script reads the exported CSV and attempts to set all field values in the Webbuilder UI.
   - Skips certain system fields and always-skipped fields for safety.

Review the exported/imported data and the Webbuilder UI after running the scripts to ensure all settings have been transferred correctly.

## Requirements
Install dependencies with:
```bash
pip install -r requirements.txt
```

### requirements.txt
```
selenium
webdriver-manager
python-dotenv
rapidfuzz
openpyxl
```

## License
See `LICENSES.md` for license information.
