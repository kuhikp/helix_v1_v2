#!/usr/bin/env python3
"""
Custom Block Counter
=====================
This script reads a sitemap.xml file, fetches pages listed in the sitemap,
counts occurrences of custom-block-element on each page, and exports the data to a CSV file.
"""

import requests
import pandas as pd
from bs4 import BeautifulSoup
from xml.etree import ElementTree as ET
import csv

def fetch_sitemap_urls(sitemap_url):
    """Fetch all URLs from the given sitemap.xml"""
    urls = []
    try:
        response = requests.get(sitemap_url, timeout=15)
        response.raise_for_status()
        root = ET.fromstring(response.content)

        # Remove namespace to simplify parsing
        for elem in root.iter():
            if '}' in elem.tag:
                elem.tag = elem.tag.split('}', 1)[1]

        # Check if this is a sitemap index (contains other sitemaps)
        sitemap_elements = root.findall('.//sitemap')
        if sitemap_elements:
            print("Found sitemap index, parsing sub-sitemaps...")
            for sitemap_elem in sitemap_elements:
                loc_elem = sitemap_elem.find('loc')
                if loc_elem is not None and loc_elem.text:
                    sub_sitemap_url = loc_elem.text.strip()
                    urls.extend(fetch_sitemap_urls(sub_sitemap_url))

        # Parse URL elements
        url_elements = root.findall('.//url')
        for url_elem in url_elements:
            loc_elem = url_elem.find('loc')
            if loc_elem is not None and loc_elem.text:
                urls.append(loc_elem.text.strip())

        return urls
    except Exception as e:
        print(f"Error fetching sitemap {sitemap_url}: {e}")
        return []

def fetch_page(url):
    """Fetch webpage content using requests"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        return soup, None
    except Exception as e:
        return None, str(e)

def count_custom_blocks(soup, class_filter="custom-block-element"):
    """Count occurrences of custom-block-element on the page and check for child elements and helix components"""
    try:
        elements = soup.select(f".{class_filter}")  # Use CSS selector for precise matching
        results = []
        for element in elements:
            child_elements = element.find_all(attrs={"class": lambda classes: classes and class_filter in ' '.join(classes)})
            helix_children = element.find_all(lambda tag: tag.name and tag.name.startswith('helix'))
            results.append({
                'element': element,
                'child_count': len(child_elements),
                'helix_child_count': len(helix_children)
            })
        return results
    except Exception as e:
        print(f"Error counting custom blocks: {e}")
        return []

def process_sitemap(sitemap_url, output_path):
    """Process sitemap.xml and count custom-block-element occurrences with child counts and helix components, avoiding duplicates"""
    try:
        print(f"Fetching URLs from sitemap: {sitemap_url}")
        urls = list(set(fetch_sitemap_urls(sitemap_url)))  # Remove duplicate URLs
        print(f"Found {len(urls)} unique URLs in sitemap.")

        results = []
        for url in urls:
            print(f"Processing URL: {url}")
            soup, error = fetch_page(url)
            if error:
                print(f"Error fetching page {url}: {error}")
                continue

            blocks = count_custom_blocks(soup)
            results.append({
                'URL': url,
                'CustomBlockCount': len(blocks),
                'ChildCustomBlockCount': sum(block['child_count'] for block in blocks),
                'HelixChildCount': sum(block['helix_child_count'] for block in blocks)
            })

        # Export results to CSV
        results_df = pd.DataFrame(results)
        results_df.to_csv(output_path, index=False)
        print(f"Results exported to {output_path}")
    except Exception as e:
        print(f"Error processing sitemap: {e}")

if __name__ == "__main__":
    # Read URLs from websites.csv and append sitemap.xml to each URL
    websites_file = "websites.csv"  # Replace with your websites.csv file path
    sitemap_urls = []

    try:
        with open(websites_file, mode='r') as file:
            reader = csv.reader(file)
            for row in reader:
                if row:  # Ensure the row is not empty
                    sitemap_urls.append(f"{row[0].strip()}/sitemap.xml")
    except Exception as e:
        print(f"Error reading websites file: {e}")
        exit(1)

    # Initialize results list
    results = []

    # Process each sitemap URL and combine results into a single CSV file
    output_csv = "custom_block_counts-dommaster-25july-new.csv"  # Replace with your desired output file
    with open(output_csv, mode='a', newline='', encoding='utf-8') as csvfile:  # Open in append mode
        fieldnames = ['URL', 'CustomBlockCount', 'ChildCustomBlockCount', 'HelixChildCount']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        # Write header only if the file is empty
        if csvfile.tell() == 0:
            writer.writeheader()

        for sitemap_url in sitemap_urls:
            print(f"Processing sitemap: {sitemap_url}")
            try:
                urls = list(set(fetch_sitemap_urls(sitemap_url)))  # Remove duplicate URLs
                print(f"Found {len(urls)} unique URLs in sitemap.")

                for url in urls:
                    print(f"Processing URL: {url}")
                    soup, error = fetch_page(url)
                    if error:
                        print(f"Error fetching page {url}: {error}")
                        continue

                    blocks = count_custom_blocks(soup)
                    record = {
                        'URL': url,
                        'CustomBlockCount': len(blocks),
                        'ChildCustomBlockCount': sum(block['child_count'] for block in blocks),
                        'HelixChildCount': sum(block['helix_child_count'] for block in blocks)
                    }
                    writer.writerow(record)
                    print(f"Processed {url}: {record}")
                    results.append(record)  # Append to results list
                    print(f"Appended record for {url}: {record}")
            except Exception as e:
                print(f"Error processing sitemap {sitemap_url}: {e}")

    # Export combined results to a single CSV file
    try:
        results_df = pd.DataFrame(results)
        results_df.to_csv(output_csv, index=False)
        print(f"Combined results exported to {output_csv}")
    except Exception as e:
        print(f"Error exporting results to CSV: {e}")
    # Ensure results are exported only once
    print("Processing completed. Results are saved in the output CSV file.")
