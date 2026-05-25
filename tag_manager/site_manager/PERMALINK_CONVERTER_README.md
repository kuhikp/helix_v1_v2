# Image Permalink Converter

## Overview

The Image Permalink Converter is a Step 5 tool in the Meta Page workflow that automatically converts image permalinks from v1 to v2 format. It processes all page JSON files, identifies image URLs that match the permalink pattern, maps old UUIDs to new ones, and updates the HTML content with the new v2 site ID and UUIDs.

## Features

- **Automated Conversion**: Processes all pages in the `data/pages` directory
- **UUID Mapping**: Automatically maps v1 UUIDs to v2 UUIDs based on file correspondence
- **v2 Site ID Integration**: Updates all permalinks with the v2 site ID from environment variables
- **Error Handling**: Graceful handling of missing mappings with detailed error reporting
- **Progress Tracking**: Real-time status updates during conversion
- **Batch Processing**: Efficiently processes multiple pages in a single operation
- **Backup Safety**: Original files modified in-place (ensure backup before running)

## How It Works

### Step-by-Step Process

1. **Directory Validation**
   - Verifies that required directories exist:
     - `site_manager/static/block_import/data/pages/`
     - `site_manager/static/block_import/data/files/`
     - `site_manager/static/block_import/data/files_v2/`

2. **UUID Mapping**
   - Reads all files from the `files/` directory (v1 UUIDs)
   - Reads all files from the `files_v2/` directory (v2 UUIDs)
   - Builds a mapping between v1 and v2 UUIDs based on filename correspondence
   - Supports both direct matches and processed file variants

3. **Page Processing**
   - Iterates through all `.json` files in the `pages/` directory
   - Parses JSON structure: `storage.data.html`
   - Extracts all image src attributes from HTML

4. **Permalink Extraction**
   - Uses regex to identify permalinks matching the pattern:
     ```
     https://webbuilder.pfizer/webbuilder/asset-proxy/{siteid}/{uuid}
     ```
   - Collects old UUIDs and site IDs

5. **UUID Conversion**
   - For each old UUID, looks up the corresponding v2 UUID in the mapping
   - If mapping found: creates new permalink with v2 site ID
   - If mapping not found: logs warning and skips

6. **HTML Update**
   - Replaces old permalinks with new ones in the HTML content
   - Updates the JSON structure with modified HTML
   - Saves updated file back to disk

7. **Result Reporting**
   - Provides detailed success/failure metrics
   - Lists all pages processed with their conversion status
   - Returns summary of successful and failed conversions

### Permalink Pattern

**Original (v1) Format:**
```
https://webbuilder.pfizer/webbuilder/asset-proxy/17493499/a433818c-beda-42cf-a135-e95773f4de48
```

**Converted (v2) Format:**
```
https://webbuilder.pfizer/webbuilder/asset-proxy/19008382/b544929d-cfea-53dg-b246-f96884g5ef59
```

Where:
- `17493499` → `19008382` (old siteid → new siteid from V2_SITE_ID)
- `a433818c-beda-42cf-a135-e95773f4de48` → `b544929d-cfea-53dg-b246-f96884g5ef59` (old UUID → new UUID from mapping)

## Configuration

### Environment Variables

Required environment variable in `.env`:

```
V2_SITE_ID=19008382
```

Add this to your `.env` file if not already present. This is the site ID that will be used in all converted permalinks.

### Directory Structure

Ensure the following directory structure exists:

```
site_manager/
  static/
    block_import/
      data/
        pages/                    # Page JSON files to process
        files/                    # v1 file references
        files_v2/                 # v2 file references
```

### File Naming Conventions

**Pages Directory:**
- Files should be named with UUID: `{uuid}.json`
- Example: `0a1125fb-2356-47ce-9a8f-fc8fddbd2f4e.json`

**Files Directory (v1):**
- Files should be named with UUID or processed variants: `{uuid}.json` or `processed_{uuid}.json`
- Example: `a433818c-beda-42cf-a135-e95773f4de48.json`

**Files_v2 Directory:**
- Files should be named with new UUID: `{new_uuid}.json`
- Example: `b544929d-cfea-53dg-b246-f96884g5ef59.json`

## Usage

### Access the Tool

1. Navigate to: `http://127.0.0.1:8000/sites/{site_id}/meta/`
2. Look for **Step 5: Convert Image Permalinks**
3. Click the **"Convert Permalinks"** button

### Running the Conversion

#### Via Web Interface

1. **Open the Converter Page**
   - URL: `http://127.0.0.1:8000/sites/{site_id}/meta/convert-permalinks/`

2. **Review Prerequisites**
   - Verify all required directories exist
   - Check that V2_SITE_ID is configured

3. **Start Conversion**
   - Click the **"Start Conversion"** button
   - Confirm the action when prompted

4. **Monitor Progress**
   - The page will show a progress indicator
   - Status updates automatically every 2 seconds
   - Wait for conversion to complete

5. **View Results**
   - Successful conversion shows green success message
   - Failed conversion shows red error message
   - Detailed results show each page's conversion status

6. **Next Steps**
   - Click "Run Conversion Again" to retry
   - Click "Clear Results" to reset the interface

#### Via Python/Management Command

You can also run the converter programmatically:

```python
from site_manager.permalink_converter import convert_permalinks

result = convert_permalinks(site_id=1445)

print(f"Success: {result['success']}")
print(f"Message: {result['message']}")
print(f"Successful: {result['successful_count']}")
print(f"Failed: {result['failed_count']}")
print(f"Details: {result['details']}")
```

## API Reference

### View: `/sites/{site_id}/meta/convert-permalinks/`

**Method:** GET

**Description:** Display the permalink converter interface

**Parameters:**
- `site_id` (int): Site ID

**Response:** HTML page with conversion interface

### Endpoint: `/sites/{site_id}/meta/convert-permalinks/start/`

**Method:** POST

**Description:** Start the conversion process asynchronously

**Parameters:**
- `site_id` (int): Site ID

**Response:**
```json
{
  "success": true,
  "message": "Permalink conversion started. Please wait..."
}
```

### Endpoint: `/sites/{site_id}/meta/convert-permalinks/status/`

**Method:** GET

**Description:** Check the status of ongoing conversion

**Parameters:**
- `site_id` (int): Site ID

**Response (In Progress):**
```json
{
  "status": "in_progress",
  "message": "Conversion in progress..."
}
```

**Response (Complete):**
```json
{
  "status": "complete",
  "result": {
    "success": true,
    "message": "Conversion complete: 45 successful, 0 failed",
    "successful_count": 45,
    "failed_count": 0,
    "details": [
      "Updated 0a1125fb-2356-47ce-9a8f-fc8fddbd2f4e.json: 3 permalinks converted",
      "Updated 0b8437f3-8d8e-42a3-b17e-ba6b6497260d.json: 2 permalinks converted",
      ...
    ],
    "v2_site_id": "19008382"
  }
}
```

### Endpoint: `/sites/{site_id}/meta/convert-permalinks/clear/`

**Method:** POST

**Description:** Clear conversion status and result files

**Parameters:**
- `site_id` (int): Site ID

**Response:**
```json
{
  "success": true,
  "message": "Conversion status cleared successfully."
}
```

## Error Handling

### Common Issues and Solutions

#### 1. **V2_SITE_ID not configured**

**Error Message:** `V2_SITE_ID environment variable not set`

**Solution:**
```bash
# Add to .env file
V2_SITE_ID=19008382

# Restart Django server for changes to take effect
```

#### 2. **files_v2 directory not found**

**Error Message:** `Error: files_v2 directory not found`

**Solution:**
```bash
# Create the directory
mkdir -p site_manager/static/block_import/data/files_v2

# Ensure it contains the v2 UUID files
```

#### 3. **No UUID mapping found**

**Error Message:** `Error: No UUID mapping found`

**Solution:**
- Verify file naming conventions match expected pattern
- Check that files in `files/` and `files_v2/` have proper UUID names
- Ensure sufficient overlap between v1 and v2 files for mapping

#### 4. **JSON parsing errors**

**Issue:** Some pages fail with JSON decode errors

**Solution:**
- Validate JSON files in the `pages/` directory
- Use `json` command-line tool to verify file integrity:
  ```bash
  python -m json.tool pages/0a1125fb-2356-47ce-9a8f-fc8fddbd2f4e.json
  ```

#### 5. **Conversion hangs or times out**

**Issue:** Process doesn't complete within expected time

**Solution:**
- Check server logs for errors
- For large datasets, increase timeout in `DEFAULT_TIMEOUT` setting
- Process pages in batches instead of all at once

## Performance Considerations

### Expected Performance

- **Small sites** (< 50 pages): < 1 minute
- **Medium sites** (50-500 pages): 1-5 minutes
- **Large sites** (500+ pages): 5-30 minutes

### Optimization Tips

1. **Ensure files_v2 exists**: Pre-create the mapping to avoid building it on each run
2. **Use SSD storage**: Faster disk I/O for JSON file processing
3. **Batch processing**: Run multiple sites in sequence rather than parallel
4. **Memory**: Ensure sufficient RAM for large JSON files

## Logging

The converter logs detailed information during operation. Check application logs for:

```
DEBUG: Extracted X permalinks from page Y
INFO: Built UUID mapping with Z entries
WARNING: No v2 UUID mapping found for UUID X
INFO: Conversion complete: X successful, Y failed out of Z total
```

## File Modifications

### What Gets Modified

- **JSON page files**: The `storage.data.html` section is updated with new permalinks
- **Metadata**: JSON structure and metadata are preserved
- **CSS/Styles**: Not affected by the conversion
- **Other HTML elements**: Only image permalinks are modified

### What's NOT Modified

- Original file names
- File structure or hierarchy
- Non-permalink image URLs
- CSS or styling information
- Page metadata

## Backup and Recovery

### Before Running

**Create a backup:**
```bash
# Backup the pages directory
cp -r site_manager/static/block_import/data/pages \
      site_manager/static/block_import/data/pages.backup
```

### After Conversion

**Verify changes:**
```bash
# Review specific page changes
diff pages.backup/0a1125fb-2356-47ce-9a8f-fc8fddbd2f4e.json \
     pages/0a1125fb-2356-47ce-9a8f-fc8fddbd2f4e.json
```

**Rollback if needed:**
```bash
# Restore backup
rm -r site_manager/static/block_import/data/pages
mv site_manager/static/block_import/data/pages.backup \
   site_manager/static/block_import/data/pages
```

## Advanced Usage

### Custom Implementation

Extend the converter for custom logic:

```python
from site_manager.permalink_converter import PermalinkConverter

class CustomConverter(PermalinkConverter):
    def _convert_permalink(self, old_url, old_uuid, uuid_mapping):
        # Custom conversion logic
        new_uuid = custom_mapping.get(old_uuid)
        if new_uuid:
            return f"https://custom-domain.com/assets/{new_uuid}"
        return None

converter = CustomConverter(
    pages_dir="/path/to/pages",
    files_dir="/path/to/files",
    files_v2_dir="/path/to/files_v2",
    v2_site_id="12345"
)

success, failed, messages = converter.convert_all_pages()
```

### Programmatic Usage

Run conversion from a management command:

```python
# management/commands/convert_permalinks.py
from django.core.management.base import BaseCommand
from site_manager.permalink_converter import convert_permalinks

class Command(BaseCommand):
    help = 'Convert permalinks for a site'
    
    def add_arguments(self, parser):
        parser.add_argument('site_id', type=int, help='Site ID')
    
    def handle(self, *args, **options):
        result = convert_permalinks(options['site_id'])
        self.stdout.write(result['message'])
        for detail in result['details']:
            self.stdout.write(f"  - {detail}")
```

## Troubleshooting

### Debug Mode

Enable debug logging:

```python
import logging
logging.getLogger('site_manager.permalink_converter').setLevel(logging.DEBUG)
```

### Common Questions

**Q: Will the conversion affect other sites?**
A: No, the conversion only processes files for the specific site ID.

**Q: Can I run conversions for multiple sites simultaneously?**
A: Not recommended. Run them sequentially to avoid resource contention.

**Q: What if a page has no images?**
A: Pages without matching permalinks are skipped safely with an info message.

**Q: How do I verify the conversion worked?**
A: Compare the page JSON before and after, or check the permalink URLs in the HTML content.

## Support

For issues or questions:

1. Check the logs: `django.log`
2. Review the detailed error messages in the conversion results
3. Verify directory structure and file naming
4. Ensure environment variables are set correctly
5. Check file permissions on the data directories

## Version History

- **v1.0** (2024-05): Initial release
  - Core conversion functionality
  - Web interface with progress tracking
  - UUID mapping and validation
