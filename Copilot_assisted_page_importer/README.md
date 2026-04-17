# Copilot Helix Backend Converter

This project converts a folder of HTML pages into Helix-compatible HTML and then imports those converted pages into Helix backend.

The workflow has two scripts that must run in order:
1. `src/convert_html_to_helix_backend.py`
2. `src/import_pages_to_helix_backend.py`

It is designed from your requirements:
- Reuses robust model-calling and error/failover style inspired by the chatbot flow.
- Supports model selection, including GPT and Claude Sonnet options.
- Reads Helix component templates from CSV.
- Preprocesses reference HTML in place by replacing image URLs with Webbuilder permalinks before model conversion starts.
- Recursively converts all `.html` files from an input folder.
- Writes output into a new folder with the same subfolder structure.
- Shows model response previews in terminal.
- Adds post-processing safeguards to reduce issues with missing closing tags and missing/duplicate ids.
- Supports resilient retries for rate limits and endpoint failover.
- Supports retry-friendly flags like `--skip-existing` and `--skip-model-analysis`.

## Included Reference Data

This new project already includes your reference inputs:
- `reference/helix_components_html_output.csv`
- `reference/input_site/HTTRACKER Site Folder 1/` // this is the HTML folder so generated from the HTTRACKER. This will act as the input for the conversion script and the output will be in a new folder that you can then import to the Webbuilder using the importer script.

## Project Structure

```text
Copilot_Helix_Backend_Converter/
  src/
    convert_html_to_helix_backend.py
    import_pages_to_helix_backend.py
  reference/
    helix_components_html_output.csv
    input_site/
      www.knowpneumonia.sg/
  requirements.txt
  .env.example
  README.md
```

## Prerequisites

- Python 3.10+ (3.11 recommended)
- A valid GitHub Copilot token or compatible GitHub token
- Network access to your chosen model endpoint
- Playwright Chromium browser (installed via setup step below)
- Webbuilder credentials and instance access for permalink preprocessing

## Full Setup (Step by Step)

1. Open terminal and go to the new project:

```bash
cd "/Users/aniyekdas/Documents/Local Setups/HTML_POC/Copilot_Helix_Backend_Converter"
```

2. Create a virtual environment:

```bash
python3 -m venv venv
```

3. Activate virtual environment:

```bash
source venv/bin/activate
```

4. Upgrade pip (recommended):

```bash
python -m pip install --upgrade pip
```

5. Install project requirements:

```bash
pip install -r requirements.txt
```

6. Install Playwright browser binary (Chromium):

```bash
python -m playwright install chromium
```

7. Create `.env` file from example:

```bash
cp .env.example .env
```

8. Edit `.env` and set token + Webbuilder values:

```env
GITHUB_COPILOT_TOKEN=your_token_here
API_BASE_URL=https://models.inference.ai.azure.com
API_TIMEOUT_SECONDS=90
USERNAME=your_webbuilder_username
PASSWORD=your_webbuilder_password
INSTANCE_ID=your_webbuilder_instance_id
```

Notes:
- By default, the script now updates HTML files in the input folder itself with permalink values before any model scanning/conversion starts.
- Use `--skip-permalink-preprocess` if you want to bypass this pre-step.

## Model Options

Common examples:
- `gpt-4o`
- `gpt-4o-mini`
- `claude-sonnet-4-6`
- `claude-sonnet-4`

If your endpoint uses different model IDs, list available IDs first:

```bash
python src/convert_html_to_helix_backend.py \
  --input-folder reference/input_site/www.knowpneumonia.sg \
  --output-folder output_html \
  --components-csv reference/helix_components_html_output.csv \
  --list-models
```

## Run with Included Reference Input

### Example 1: GPT-4o with creativity 0.4

```bash
python3 src/convert_html_to_helix_backend.py \
  --input-folder reference/input_site/www.knowpneumonia.sg \
  --output-folder converted_output_gpt4o \
  --components-csv reference/helix_components_html_output.csv \
  --model gpt-4o \
  --temperature 0.4 \
  --show-model-output \
  --copy-non-html
```

### Example 2: Claude Sonnet option

```bash
python src/convert_html_to_helix_backend.py \
  --input-folder reference/input_site/www.knowpneumonia.sg \
  --output-folder converted_output_claude \
  --components-csv reference/helix_components_html_output.csv \
  --model claude-sonnet-4-6 \
  --temperature 0.4 \
  --show-model-output \
  --copy-non-html
```

### Example 3: Resume a partial run (recommended for rate limits)

```bash
python3 src/convert_html_to_helix_backend.py \
  --input-folder reference/input_site/www.knowpneumonia.sg \
  --output-folder converted_output_gpt4o_v2 \
  --components-csv reference/helix_components_html_output.csv \
  --model gpt-4o \
  --temperature 0.4 \
  --copy-non-html \
  --skip-existing \
  --skip-model-analysis \
  --analysis-cache-file temp/component_analysis_cache.txt
```

## Run with Any Other Input Folder

The script is folder-agnostic. You can pass any site folder containing `.html` files.

```bash
python src/convert_html_to_helix_backend.py \
  --input-folder "/path/to/your/new/input_html_folder" \
  --output-folder "/path/to/your/new/output_folder" \
  --components-csv "/path/to/helix_components_html_output.csv" \
  --model gpt-4o \
  --temperature 0.4 \
  --show-model-output
```

## Mandatory Run Order (Convert First, Import Second)

You should run the importer only after conversion has finished successfully.

### Step 1: Convert HTML into Helix-style output

```bash
python3 src/convert_html_to_helix_backend.py \
  --input-folder reference/input_site/www.knowpneumonia.sg \
  --output-folder converted_gpt4o_proconnect_pfizerpro_br \
  --components-csv reference/helix_components_html_output.csv \
  --model gpt-4o \
  --temperature 0.4 \
  --copy-non-html
```

### Step 2: Import converted HTML pages into Helix backend

```bash
python3 src/import_pages_to_helix_backend.py \
  --input-folder converted_gpt4o_proconnect_pfizerpro_br
```

Notes:
- The `--input-folder` for the importer must be the converted output folder created in Step 1.
- The importer assumes homepage comes from `index.html` and uses parent-folder names as page titles.
- If Save Page stays disabled after default dropdown selection, the page is logged in `manual_page_intervention.csv`.

## Import Script Details (`import_pages_to_helix_backend.py`)

The importer script does the following:
1. Logs in to Webbuilder with `USERNAME` and `PASSWORD` from `.env`.
2. Opens website editor using `INSTANCE_ID` from `.env` (or `--instance-id`).
3. Imports homepage HTML first (`index.html`).
4. Creates subpages from remaining HTML files and imports each page content.
5. Handles disabled Save Page cases by logging them for manual intervention.

### Import Script Flags

- `--input-folder` (required): folder containing converted HTML files.
- `--manual-intervention-csv`: override CSV path for manual intervention logs.
- `--headless`: run browser in headless mode.
- `--instance-id`: override `INSTANCE_ID` from `.env`.

## What the Script Does Internally

1. Loads environment values.
2. Runs Webbuilder permalink preprocessing against input HTML files (in place):
   - logs in to Webbuilder
   - opens file manager for `INSTANCE_ID`
   - resolves image filenames to permalink URLs
   - updates matching image source values directly in input files
3. Loads token and endpoint for model conversion.
4. Loads component templates from CSV (`Component Name`, `HTML Content`).
5. Calls the model once to analyze component library summary.
6. Scans input folder recursively for `.html` files.
7. For each file:
- Detects likely component keywords from HTML tags.
- Selects relevant CSV component examples.
- Calls selected model to generate Helix-style HTML.
- Prints model response preview (if `--show-model-output`).
- Post-processes output:
  - expands self-closing custom tags
  - injects/fixes unique ids
  - appends missing custom closing tags when needed
8. Writes converted HTML to output folder preserving original relative paths.
9. Optionally copies non-HTML assets to output (`--copy-non-html`).

## Useful Flags

- `--skip-existing`: skips conversion for files already present in output.
- `--skip-model-analysis`: skips initial analysis model call and uses deterministic fallback summary.
- `--analysis-cache-file <path>`: reads/writes component-analysis text to reduce repeated analysis calls.
- `--show-model-output`: prints model response previews during conversion.
- `--skip-permalink-preprocess`: skips Webbuilder permalink preprocessing stage.
- `--permalink-headless`: runs permalink preprocessing browser in headless mode.

## Important Notes

- This script aims to preserve page context and content while migrating structure.
- IDs are kept when present; missing/duplicate IDs are repaired.
- Extra post-processing is included to reduce problems like missing closing tags.
- Model output quality depends on endpoint availability and model behavior.
- Input HTML files are modified in place first by the permalink preprocessing stage unless you pass `--skip-permalink-preprocess`.

## Troubleshooting

- Authentication errors (401/403):
  - Verify token and access permissions.
  - If organization SSO is enforced, authorize token for SSO.

- Endpoint errors (404/connection):
  - Try `API_BASE_URL=https://models.inference.ai.azure.com`.
  - Use `--list-models` to confirm endpoint is reachable.

- Frequent 429 rate limits:
  - Re-run with `--skip-existing` to process only missing files.
  - Use `--skip-model-analysis` + `--analysis-cache-file` to avoid blocking on the initial analysis call.
  - Try again after cooldown if endpoint throttling persists.

- Model ID not found:
  - Run `--list-models` and use an exact returned model ID.

- No output files generated:
  - Confirm input folder contains `.html` files.
  - Check terminal logs for per-file conversion errors.

- Python cannot find importer script:
  - Run from project root using `python3 src/import_pages_to_helix_backend.py ...`
  - If you run from a parent folder, include full relative path to `src/import_pages_to_helix_backend.py`.

- Permalink preprocessing fails:
  - Confirm `USERNAME`, `PASSWORD`, and `INSTANCE_ID` are set in `.env`.
  - Ensure Playwright is installed (`pip install -r requirements.txt`) and browser is installed (`python -m playwright install chromium`).
  - Use `--skip-permalink-preprocess` to run model conversion without permalink updates if needed.
