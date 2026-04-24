Blocks_import is a utility workflow used to generate HTML block files and import them into the application so they can be served by the server.

📌 Overview
This process involves:

Updating directory paths in Block_script.py
Generating HTML block files
Copying generated files into the correct static directory
Running the server to load the blocks


✅ Prerequisites
Before you begin, make sure you have:

Python installed and configured
Access to the project repository
Block_script.py available
Required server dependencies already installed


🚀 Getting Started
1. Update Configuration
Open Block_script.py and update the following variables:
ROOT_DIR = "<path_to_project_root>"
OUTPUT_DIR = "<path_to_generated_html_output>"

Notes:

ROOT_DIR should point to the root of the project.
OUTPUT_DIR should be the directory where HTML files will be generated.


2. Generate HTML Files
Run the script to generate the HTML files:
python Block_script.py

Once completed, HTML files will be available in the specified OUTPUT_DIR.

3. Copy Generated Files
Copy all generated HTML files to the following location:

tag_manager/site_manager/static/block_import/data/modules

4. Run the Server
Start the application server using the appropriate command for your project, for example:

python manage.py runserver

🔍 Verification

Open the application in your browser
Confirm that the imported blocks are displayed correctly
Check server logs for any missing file or path-related errors


❗ Troubleshooting
Blocks not visible

Ensure the HTML files exist in:
static/block_import/data/modules

Path errors

Double-check ROOT_DIR and OUTPUT_DIR values in Block_script.py

Changes not reflecting

Restart the server
Clear browser cache if necessary

📝 Notes

Avoid manually editing generated HTML files unless required.
Re-run Block_script.py whenever block definitions are updated.

📂 Suggested Directory Structure (Optional)

block_import/
├── data/
│   └── modules/
│       ├── block1.html
│       ├── block2.html
│       └── ...

