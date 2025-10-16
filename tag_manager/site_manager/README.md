# Helix Tag Manager Meta Export/Import Utility

## Overview
This project provides utilities for exporting and importing meta data between v1 and v2 Helix sites. It includes Django views, user-facing forms, and Python scripts to automate the process of exporting meta data from one site and importing it into another.

## Key Features
- **Export Meta**: Trigger an export by providing v1 and v2 site IDs. The system writes these to `input.csv`, runs the export script, and allows you to download the resulting CSV.
- **Import Meta**: Upload a CSV file to import meta data into the system using the import script.
- **Status Polling**: The UI polls the backend to show export progress and enables download when ready.
- **User Interface**: All actions are available via the Django admin interface with Bootstrap modals and AJAX for a smooth user experience.

## File Structure
- `script_to_export.py`: Python script to export meta data based on `input.csv`.
- `script_import_data.py`: Python script to import meta data from a CSV file.
- `requirements.txt`: Python dependencies for the scripts (see below).
- `site_manager/views.py`: Django views for handling export/import requests, status polling, and file downloads.
- `site_manager/templates/site_manager/site_meta_list.html`: Main UI for triggering export/import and viewing meta details.

## Usage
### 1. Export Meta
- Go to the Site Meta Details page in the Django admin.
- Click the **Export Meta** button.
- Enter the v1 and v2 site IDs in the modal form and submit.
- The system will start the export, show progress, and enable the **Download Export** button when ready.

### 2. Import Meta
- Click the **Import Meta** button and upload the exported CSV file.
- The system will process the file and import the meta data.

### 3. Status & Download
- Export progress is shown in real time.
- When export is complete, click **Download Export** to get the CSV file.

## Requirements
Install dependencies with:

```
pip install -r requirements.txt
```

### requirements.txt
```
selenium
webdriver-manager
python-dotenv
rapidfuzz
```

## Notes
- Make sure you have Chrome installed for Selenium WebDriver.
- The scripts expect `input.csv` for export and a compatible CSV for import.
- All file paths are relative to the Django project's `BASE_DIR`.

## Troubleshooting
- If you see `Invalid request method`, ensure you are using the provided UI forms (which use POST) and not accessing endpoints directly via GET.
- For any errors, check the Django logs and the output of the Python scripts for more details.

## Meta Export/Import Details

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
> left-sidebar-settings--website (Edison lite site id will vary between v1 and v2)
> left-sidebar-settings--fonts (custom fonts may not transfer)
> left-sidebar-settings--grv (It can be added if grv is enabled)
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

## License
See `LICENSES.md` for license information.
