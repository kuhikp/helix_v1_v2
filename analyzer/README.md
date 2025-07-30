# Enhanced Web Scraper

## Overview
The Enhanced Web Scraper is a Flask-based web application designed to analyze websites, extract specific elements, and export the results to CSV files. It includes advanced features such as sitemap discovery, real-time progress tracking, and detailed analytics.

## Features

### 1. Sitemap Discovery
- Automatically discovers sitemaps from common locations (e.g., `sitemap.xml`, `robots.txt`).
- Parses sitemap index files and sub-sitemaps.
- Extracts all valid URLs for analysis.

### 2. Real-Time Progress Tracking
- Tracks the number of URLs processed, failed, and total elements found.
- Displays a progress bar and logs for real-time updates.

### 3. Enhanced Analysis
- Extracts custom class elements and Helix components.
- Provides detailed metrics such as word count, image count, link count, and nesting depth.
- Categorizes blocks (e.g., Header, Hero, Content, Footer).

### 4. CSV Export
- Exports analysis results to CSV files.
- Includes metadata such as source URL, page title, and attributes.

## Installation

### Prerequisites
- Python 3.7+
- Flask
- BeautifulSoup
- Requests

### Setup
1. Clone the repository:
   ```bash
   git clone <repository-url>
   ```
2. Navigate to the project directory:
   ```bash
   cd pythonscript
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Start the Flask application:
   ```bash
   python enhanced_web_scraper.py
   ```

## Usage

### Web Interface
1. Open your browser and navigate to `http://localhost:5000`.
2. Enter the website URL and optional filters.
3. Click "Analyze & Export" to start the analysis.
4. Download the generated CSV files.

### API Access
You can also use the API for programmatic access:
```bash
curl -X POST http://localhost:5000/api/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "class_filter": "custom-block-element"
  }'
```

## File Structure
```
pythonscript/
├── enhanced_web_scraper.py       # Main application file
├── templates/                    # HTML templates for the web interface
├── static/                       # Static assets (CSS, JS, images)
├── downloads/                    # Generated CSV files
├── requirements.txt              # Python dependencies
└── README.md                     # Project documentation
```

## Key Classes and Functions

### `SimpleHTMLParser`
- Parses HTML content to extract metadata, headings, links, and scripts.
- Identifies Helix components and their versions.

### `SimpleHomepageAnalyzer`
- Analyzes homepage content for theme and architecture information.
- Extracts analytics and detailed findings.

### `fetch_sitemap_urls`
- Fetches all URLs from sitemaps for a given website.
- Supports robots.txt parsing for sitemap references.

### `scrape_multiple_urls_with_progress`
- Scrapes multiple URLs with real-time progress updates.
- Combines results from all pages into a single dataset.

## Troubleshooting

### Common Issues
1. **Port Already in Use**
   ```bash
   lsof -i :5000
   kill -9 <PID>
   ```
2. **Missing Dependencies**
   ```bash
   pip install -r requirements.txt
   ```
3. **Sitemap Not Found**
   - Ensure the website has a valid sitemap.
   - Check robots.txt for sitemap references.

### Logs
Check the application logs for detailed error messages:
```bash
cat app.log
```

## License
This project is licensed under the MIT License. See the LICENSE file for details.
