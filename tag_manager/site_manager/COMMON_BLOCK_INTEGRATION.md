# Common Block Integration – Setup Guide

## Overview

This update introduces utilities to extract reusable HTML blocks (common blocks) and convert them into JSON or static assets for use across the application.

As part of this change:
- Two new Python utility files have been added
- A new static folder structure is required
- Extracted HTML files must be placed into a specific static directory

---

## Added Files

The following files have been added under `site_manager`:

- **`common_block_extractor.py`**  
  Responsible for extracting common HTML blocks from source files and saving them locally.

- **`common_block_to_json.py`**  
  Converts extracted common blocks into a JSON-compatible format for further consumption.

---

## Required Folder Structure

A new folder must be created to store extracted HTML files.

### 📁 Create the following directory path:
tag_manager/
└── site_manager/
└── static/
└── subscription/

If the folder does not already exist, create it manually:

```bash
mkdir -p tag_manager/site_manager/static/subscription

HTML File Placement
✅ Required Action
All HTML files extracted using common_block_extractor.py must be copied into the subscription folder:
tag_manager/site_manager/static/subscription/

📌 Example
If common_block_extractor.py extracts files like:
header.html
footer.html
subscription_card.html

They should be placed as:
tag_manager/site_manager/static/subscription/header.html
tag_manager/site_manager/static/subscription/footer.html
tag_manager/site_manager/static/subscription/subscription_card.html