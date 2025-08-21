#!/usr/bin/env python3
"""
Helix V1 to V2 Analyzer with CSV Export
====================================

This enhanced version focuses on Custom Class Elements and Helix Elements
with CSV export functionality.
"""

# Import necessary libraries and modules
from flask import Flask, render_template, request, jsonify, send_file, flash, redirect, url_for, Response
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import json
import time
import os
from urllib.parse import urlparse
import tempfile
import zipfile
from werkzeug.utils import secure_filename
import logging
from xml.etree import ElementTree as ET
from urllib.robotparser import RobotFileParser
import threading
import queue
from html.parser import HTMLParser
from datetime import datetime

# Configure logging for the application
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask application
app = Flask(__name__)
app.secret_key = '#123462345223424'

# Configuration for file uploads
UPLOAD_FOLDER = 'downloads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Global storage for progress tracking
progress_sessions = {}

# Define a custom HTML parser class
class SimpleHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.current_tag = None
        self.attrs_dict = {}
        self.helix_components = {}
        self.page_title = ""
        self.meta_description = ""
        self.headings = []
        self.links = []
        self.scripts = []
        self.in_title = False
        self.in_script = False
        self.script_content = ""
        
    def handle_starttag(self, tag, attrs):
        """Handle the start of an HTML tag"""
        self.current_tag = tag
        self.attrs_dict = dict(attrs)
        
        # Check for Helix components
        if tag.startswith('helix-') or 'data-hwc-version' in self.attrs_dict:
            version = self.attrs_dict.get('data-hwc-version', 'unknown')
            if tag not in self.helix_components:
                self.helix_components[tag] = {'versions': set(), 'count': 0}
            self.helix_components[tag]['versions'].add(version)
            self.helix_components[tag]['count'] += 1
        
        # Extract meta information
        if tag == 'title':
            self.in_title = True
        elif tag == 'meta' and self.attrs_dict.get('name') == 'description':
            self.meta_description = self.attrs_dict.get('content', '')
        elif tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            self.headings.append({'tag': tag, 'attrs': self.attrs_dict})
        elif tag == 'a' and 'href' in self.attrs_dict:
            self.links.append({'href': self.attrs_dict['href'], 'attrs': self.attrs_dict})
        elif tag == 'script':
            self.in_script = True
            if 'src' in self.attrs_dict:
                self.scripts.append(self.attrs_dict['src'])
    
    def handle_endtag(self, tag):
        """Handle the end of an HTML tag"""
        if tag == 'title':
            self.in_title = False
        elif tag == 'script':
            self.in_script = False
            self.script_content = ""
    
    def handle_data(self, data):
        """Handle the data within an HTML tag"""
        if self.in_title:
            self.page_title += data.strip()
        elif self.in_script:
            self.script_content += data

# Define a class for analyzing homepage content
class SimpleHomepageAnalyzer:
    def __init__(self, url):
        self.url = url
        self.html_content = ""
        self.parser = SimpleHTMLParser()
        self.findings = {}
    
    def set_content(self, html_content):
        """Set HTML content directly for analysis"""
        self.html_content = html_content
    
    def parse_content(self):
        """Parse the provided HTML content"""
        if self.html_content:
            self.parser.feed(self.html_content)
            return True
        return False
    
    def extract_analytics(self):
        """Extract page analytics from script content"""
        analytics = {}
        
        # Search for pageAnalytics in the HTML content
        pattern = r'var pageAnalytics = \{([^}]+)\}'
        match = re.search(pattern, self.html_content, re.DOTALL)
        
        if match:
            analytics_content = match.group(1)
            
            # Extract key-value pairs
            lines = analytics_content.split('\n')
            for line in lines:
                line = line.strip()
                if ':' in line and not line.startswith('//'):
                    try:
                        key, value = line.split(':', 1)
                        key = key.strip().strip('"').strip("'")
                        value = value.strip().rstrip(',').strip('"').strip("'")
                        if value != 'null' and value:
                            analytics[key] = value
                    except:
                        continue
        
        return analytics
    
    def extract_theme_info(self):
        """Extract theme and architecture information from the HTML content"""
        theme_info = {}
        
        # Look for theme links in the HTML
        if 'hcp-galaxy-theme.digitalpfizer.com' in self.html_content:
            theme_info['theme_system'] = 'hcp-galaxy-theme'
            # Extract version
            version_match = re.search(r'hcp-galaxy-theme\.digitalpfizer\.com/(\d+\.\d+\.\d+)/', self.html_content)
            if version_match:
                theme_info['theme_version'] = version_match.group(1)
        elif 'pkg-cdn.digitalpfizer.com' in self.html_content:
            theme_info['theme_system'] = 'cdn-theme'
            # Extract version
            version_match = re.search(r'pkg-cdn\.digitalpfizer\.com/(\d+\.\d+\.\d+)/', self.html_content)
            if version_match:
                theme_info['theme_version'] = version_match.group(1)
        if 'helix-web-components' in self.html_content:
            theme_info['theme_system'] = 'helix-web-components'
        elif 'helix-core-content' in self.html_content:
            theme_info['theme_system'] = 'helix-core-content'
        # Determine component architecture
        if 'helix-core-' in self.html_content:
            theme_info['component_architecture'] = 'helix-core (modern)'
        elif 'helix-' in self.html_content:
            theme_info['component_architecture'] = 'helix-web-components (legacy)'
        
        # Ensure theme_system key exists
        if 'theme_system' not in theme_info:
            theme_info['theme_system'] = ''
        return theme_info
    
    def analyze_all(self):
        """Perform a complete analysis of the HTML content"""
        if not self.parse_content():
            return None
        
        # Convert sets to lists for JSON serialization
        helix_components = {}
        for comp, data in self.parser.helix_components.items():
            helix_components[comp] = {
                'versions': list(data['versions']),
                'count': data['count']
            }
        
        self.findings = {
            'url': self.url,
            'analysis_date': datetime.now().isoformat(),
            'page_title': self.parser.page_title,
            'meta_description': self.parser.meta_description,
            'helix_components': helix_components,
            'page_analytics': self.extract_analytics(),
            'theme_info': self.extract_theme_info(),
            'total_headings': len(self.parser.headings),
            'total_links': len(self.parser.links),
            'total_scripts': len(self.parser.scripts)
        }
        
        return self.findings
    
    def print_findings(self):
        """Print the findings in a formatted column layout"""
        if not self.findings:
            print("No findings available")
            return
        
        print("\nKEY FINDINGS - COLUMN FORMAT")
        print("=" * 80)
        
        # Basic information
        print(f"{'URL:':<25} {self.findings['url']}")
        print(f"{'Page Title:':<25} {self.findings['page_title'][:50]}...")
        print(f"{'Meta Description:':<25} {self.findings['meta_description'][:50]}...")
        print(f"{'Analysis Date:':<25} {self.findings['analysis_date']}")
        
        print(f"\n{'THEME & ARCHITECTURE':<25}")
        print("-" * 50)
        theme_info = self.findings['theme_info']
        for key, value in theme_info.items():
            print(f"{'  ' + key + ':':<25} {value}")
        
        print(f"\n{'PAGE ANALYTICS':<25}")
        print("-" * 50)
        analytics = self.findings['page_analytics']
        for key, value in list(analytics.items())[:10]:
            print(f"{'  ' + key + ':':<25} {value}")
        
        print(f"\n{'HELIX COMPONENTS':<25}")
        print("-" * 50)
        helix_components = self.findings['helix_components']
        for comp, data in helix_components.items():
            versions_str = ', '.join(data['versions'])
            print(f"{'  ' + comp + ':':<25} Count: {data['count']}, Versions: {versions_str}")
        
        print(f"\n{'SUMMARY STATISTICS':<25}")
        print("-" * 50)
        print(f"{'  Total Components:':<25} {len(helix_components)}")
        total_instances = sum(comp['count'] for comp in helix_components.values())
        print(f"{'  Total Instances:':<25} {total_instances}")
        print(f"{'  Total Headings:':<25} {self.findings['total_headings']}")
        print(f"{'  Total Links:':<25} {self.findings['total_links']}")
        print(f"{'  Total Scripts:':<25} {self.findings['total_scripts']}")
        
        # Version analysis
        all_versions = set()
        for comp_data in helix_components.values():
            all_versions.update(comp_data['versions'])
        
        if all_versions:
            print(f"{'  Component Versions:':<25} {', '.join(sorted(all_versions))}")
            
            if any(v.startswith('4.') for v in all_versions):
                print(f"{'  Architecture Type:':<25} Modern (4.x series)")
            elif any(v.startswith('3.') for v in all_versions):
                print(f"{'  Architecture Type:':<25} Legacy (3.x series)")

def cleanup_old_sessions():
    """Clean up old progress sessions to prevent memory leaks"""
    current_time = time.time()
    sessions_to_remove = []
    
    for session_id, session_data in progress_sessions.items():
        # Remove sessions older than 1 hour
        if 'timestamp' in session_data:
            if current_time - session_data['timestamp'] > 3600:
                sessions_to_remove.append(session_id)
        # Remove completed/error sessions older than 10 minutes
        elif session_data.get('status') in ['completed', 'error']:
            if 'last_updated' in session_data:
                if current_time - session_data['last_updated'] > 600:
                    sessions_to_remove.append(session_id)
    
    for session_id in sessions_to_remove:
        try:
            del progress_sessions[session_id]
            logger.info(f"Cleaned up old session: {session_id}")
        except KeyError:
            pass


def fetch_sitemap_urls(base_url):
    """
    Fetch all URLs from sitemap(s) for the given website
    Returns a list of URLs found in sitemaps
    """
    urls_found = []

    try:
        # Common sitemap locations
        sitemap_urls = [
            f"{base_url}/sitemap.xml",
            f"{base_url}/sitemap_index.xml", 
            f"{base_url}/sitemaps.xml",
            f"{base_url}/sitemap/sitemap.xml",
            f"{base_url}/sitemap1.xml"
        ]

        # Check robots.txt for sitemap references
        try:
            robots_url = f"{base_url}/robots.txt"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            robots_response = requests.get(robots_url, headers=headers, timeout=10)
            if robots_response.status_code == 200:
                robots_content = robots_response.text
                # Look for sitemap directives
                for line in robots_content.split('\n'):
                    if line.lower().startswith('sitemap:'):
                        sitemap_url = line.split(':', 1)[1].strip()
                        if sitemap_url not in sitemap_urls:
                            sitemap_urls.append(sitemap_url)
        except Exception as e:
            logger.warning(f"Could not fetch robots.txt: {e}")

        # Try each sitemap URL
        for sitemap_url in sitemap_urls:
            try:
                logger.info(f"Trying sitemap: {sitemap_url}")
                response = requests.get(sitemap_url, headers=headers, timeout=15)

                if response.status_code == 200:
                    logger.debug(f"Sitemap content: {response.text[:500]}...")  # Log first 500 characters
                    urls_from_sitemap = parse_sitemap(response.content, base_url)
                    urls_found.extend(urls_from_sitemap)
                    logger.info(f"Found {len(urls_from_sitemap)} URLs in {sitemap_url}")
                else:
                    logger.warning(f"Sitemap {sitemap_url} returned status code {response.status_code}")

            except Exception as e:
                logger.warning(f"Error fetching sitemap {sitemap_url}: {e}")
                continue

        # Remove duplicates and filter valid URLs
        unique_urls = list(set(urls_found))
        valid_urls = []

        for url in unique_urls:
            print(f"Validating URL: {base_url}")
            if url.startswith(('http://', 'https://')) and url != base_url:
                valid_urls.append(url)

        logger.info(f"Total unique valid URLs found: {len(valid_urls)}")
        return valid_urls

    except Exception as e:
        logger.error(f"Error fetching sitemap URLs: {e}")
        return []


def parse_sitemap(sitemap_content, base_url):
    """
    Parse sitemap XML content and extract URLs
    Handles both regular sitemaps and sitemap index files
    """
    urls = []
    
    try:
        root = ET.fromstring(sitemap_content)
        
        # Remove namespace to simplify parsing
        for elem in root.iter():
            if '}' in str(elem.tag):
                elem.tag = elem.tag.split('}', 1)[1]
        
        # Check if this is a sitemap index (contains other sitemaps)
        sitemap_elements = root.findall('.//sitemap')
        if sitemap_elements:
            logger.info("Found sitemap index, parsing sub-sitemaps...")
            for sitemap_elem in sitemap_elements:
                loc_elem = sitemap_elem.find('loc')
                if loc_elem is not None and loc_elem.text:
                    try:
                        # Fetch the sub-sitemap
                        headers = {
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                        }
                        sub_response = requests.get(loc_elem.text, headers=headers, timeout=15)
                        if sub_response.status_code == 200:
                            sub_urls = parse_sitemap(sub_response.content, base_url)
                            urls.extend(sub_urls)
                    except Exception as e:
                        logger.warning(f"Error fetching sub-sitemap {loc_elem.text}: {e}")
        
        # Parse URL elements
        url_elements = root.findall('.//url')
        for url_elem in url_elements:
            loc_elem = url_elem.find('loc')
            if loc_elem is not None and loc_elem.text:
                urls.append(loc_elem.text.strip())
        
        return urls
        
    except ET.ParseError as e:
        logger.warning(f"Error parsing sitemap XML: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error parsing sitemap: {e}")
        return []


def scrape_multiple_urls_with_progress(urls, class_filter="custom-block-element", max_pages=None, progress_callback=None, session_id=None):
    """
    Scrape multiple URLs and combine the results with real-time progress updates
    Returns combined data from all pages
    """
    all_custom_elements = []
    all_helix_elements = []
    
    processed_urls = []
    failed_urls = []
    
    # Limit pages if specified
    if max_pages:
        urls = urls[:max_pages]
    
    total_urls = len(urls)
    
    for i, url in enumerate(urls, 1):
        try:
            logger.info(f"Processing URL {i}/{total_urls}: {url}")
            
            # Fetch the page
            soup, page_source, error = fetch_page(url)
            if error:
                logger.warning(f"Failed to fetch {url}: {error}")
                failed_urls.append({'url': url, 'error': error})
                
                # Update failed count in progress
                if session_id and session_id in progress_sessions:
                    progress_sessions[session_id]['urls_failed'] = len(failed_urls)
                    progress_sessions[session_id]['processing_log'].append(f'Failed to fetch {url}: {error}')
                
                continue
            
            # Run enhanced analyses
            custom_elements = find_enhanced_custom_class_elements(soup, class_filter)
            helix_elements = find_enhanced_helix_elements(soup, page_source)
            
            # Add source URL to each element
            for element in custom_elements:
                element['source_url'] = url
                element['page_title'] = soup.title.string if soup.title else 'No Title'
            
            for element in helix_elements:
                element['source_url'] = url
                element['page_title'] = soup.title.string if soup.title else 'No Title'
            
            # Add to combined results
            all_custom_elements.extend(custom_elements)
            all_helix_elements.extend(helix_elements)
            
            processed_urls.append(url)
            
            # Call progress callback with element counts
            if progress_callback:
                progress_callback(
                    i, 
                    total_urls, 
                    url, 
                    len(all_custom_elements), 
                    len(all_helix_elements)
                )
            
            # Small delay to be respectful to the server
            time.sleep(0.5)
            
        except Exception as e:
            logger.error(f"Error processing {url}: {e}")
            failed_urls.append({'url': url, 'error': str(e)})
            
            # Update failed count in progress
            if session_id and session_id in progress_sessions:
                progress_sessions[session_id]['urls_failed'] = len(failed_urls)
                progress_sessions[session_id]['processing_log'].append(f'Error processing {url}: {str(e)}')
            
            continue
    
    results = {
        'custom_elements': all_custom_elements,
        'helix_elements': all_helix_elements,
        'processed_urls': processed_urls,
        'failed_urls': failed_urls,
        'summary': {
            'total_urls_processed': len(processed_urls),
            'total_urls_failed': len(failed_urls),
            'custom_class_elements_count': len(all_custom_elements),
            'helix_elements_count': len(all_helix_elements),
            'total_elements': len(all_custom_elements) + len(all_helix_elements)
        }
    }
    
    return results


def scrape_multiple_urls(urls, class_filter="custom-block-element", max_pages=None, progress_callback=None):
    """
    Scrape multiple URLs and combine the results
    Returns combined data from all pages
    """
    all_custom_elements = []
    all_helix_elements = []
    
    processed_urls = []
    failed_urls = []
    
    # Limit pages if specified
    if max_pages:
        urls = urls[:max_pages]
    
    total_urls = len(urls)
    
    for i, url in enumerate(urls, 1):
        try:
            logger.info(f"Processing URL {i}/{total_urls}: {url}")
            
            if progress_callback:
                progress_callback(i, total_urls, url)
            
            # Fetch the page
            soup, page_source, error = fetch_page(url)
            if error:
                logger.warning(f"Failed to fetch {url}: {error}")
                failed_urls.append({'url': url, 'error': error})
                continue
            
            # Run enhanced analyses
            custom_elements = find_enhanced_custom_class_elements(soup, class_filter)
            helix_elements = find_enhanced_helix_elements(soup, page_source)
            
            # Add source URL to each element
            for element in custom_elements:
                element['source_url'] = url
                element['page_title'] = soup.title.string if soup.title else 'No Title'
            
            for element in helix_elements:
                element['source_url'] = url
                element['page_title'] = soup.title.string if soup.title else 'No Title'
            
            # Add to combined results
            all_custom_elements.extend(custom_elements)
            all_helix_elements.extend(helix_elements)
            
            processed_urls.append(url)
            
            # Small delay to be respectful to the server
            time.sleep(0.5)
            
        except Exception as e:
            logger.error(f"Error processing {url}: {e}")
            failed_urls.append({'url': url, 'error': str(e)})
            continue
    
    results = {
        'custom_elements': all_custom_elements,
        'helix_elements': all_helix_elements,
        'processed_urls': processed_urls,
        'failed_urls': failed_urls,
        'summary': {
            'total_urls_processed': len(processed_urls),
            'total_urls_failed': len(failed_urls),
            'custom_class_elements_count': len(all_custom_elements),
            'helix_elements_count': len(all_helix_elements),
            'total_elements': len(all_custom_elements) + len(all_helix_elements)
        }
    }
    
    return results


def fetch_page(url):
    """Fetch webpage content using requests"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        return soup, response.text, None
        
    except Exception as e:
        logger.error(f"Error fetching page: {e}")
        return None, None, str(e)


def find_enhanced_custom_class_elements(soup, class_filter="custom-block-element"):
    """
    Enhanced Custom Class Elements finder with detailed analysis
    Focus on PRIMARY elements only, excluding child helix elements
    """
    custom_elements = []
    
    # Find all elements with the target class
    all_elements = soup.find_all(attrs={"class": True})
    
    for element in all_elements:
        classes = element.get('class', [])
        class_string = ' '.join(classes)
        
        if class_filter.lower() in class_string.lower():
            
            # Check for helix children
            helix_children = element.find_all(lambda tag: tag.name and tag.name.startswith('helix'))
            
            # Determine block category
            block_category = determine_block_category(element, classes)
            
            # Generate enhanced label
            enhanced_label = generate_enhanced_label(element, classes, helix_children)
            
            # Calculate content metrics
            content_metrics = calculate_content_metrics(element)
            
            custom_elements.append({
                'element_id': element.get('id', f'element_{len(custom_elements)}'),
                'tag': element.name,
                'classes': class_string,
                'enhanced_label': enhanced_label,
                'block_category': block_category,
                'has_helix_children': len(helix_children) > 0,
                'helix_children_count': len(helix_children),
                'helix_child_types': ', '.join(list(set([child.name for child in helix_children]))),
                'text_content': element.get_text(strip=True),
                'text_length': len(element.get_text(strip=True)),
                'word_count': content_metrics['word_count'],
                'image_count': content_metrics['image_count'],
                'link_count': content_metrics['link_count'],
                'form_elements': content_metrics['form_element_count'],
                'nesting_depth': content_metrics['nesting_depth'],
                'total_child_elements': len(element.find_all()),
                'semantic_elements': len(element.find_all(['header', 'nav', 'main', 'section', 'article', 'aside', 'footer'])),
                'interactive_elements': len(element.find_all(['button', 'input', 'select', 'textarea', 'a'])),
                'attributes_json': json.dumps(dict(element.attrs), indent=2)
            })
    
    return custom_elements


def find_enhanced_helix_elements(soup, page_source):
    """Enhanced Helix Elements finder with detailed analysis"""
    helix_elements = []
    
    # Method 1: Parse HTML for helix tags
    helix_tags = soup.find_all(lambda tag: tag.name and tag.name.startswith('helix'))
    
    for i, tag in enumerate(helix_tags):
        # Check if this is a child of a custom-block-element
        parent_custom_block = tag.find_parent(attrs={"class": lambda x: x and 'custom-block-element' in ' '.join(x)})
        
        helix_elements.append({
            'element_id': tag.get('id', f'helix_parsed_{i}'),
            'detection_type': 'parsed_tag',
            'tag_name': tag.name,
            'is_child_of_custom_block': parent_custom_block is not None,
            'parent_block_id': parent_custom_block.get('id', 'unknown') if parent_custom_block else 'none',
            'classes': ' '.join(tag.get('class', [])),
            'text_content': tag.get_text(strip=True),
            'text_length': len(tag.get_text(strip=True)),
            'word_count': len(tag.get_text(strip=True).split()) if tag.get_text(strip=True) else 0,
            'attributes_count': len(tag.attrs),
            'child_elements_count': len(tag.find_all()),
            'has_slot_attribute': 'slot' in tag.attrs,
            'slot_value': tag.get('slot', 'none'),
            'variant': tag.get('variant', 'none'),
            'data_attributes': json.dumps({k: v for k, v in tag.attrs.items() if k.startswith('data-')}, indent=2),
            'attributes_json': json.dumps(dict(tag.attrs), indent=2),
            'html_content': str(tag)[:500] + '...' if len(str(tag)) > 500 else str(tag)
        })
    
    # Method 2: Raw text search for helix patterns
    helix_pattern = r'<helix[^>]*(?:>.*?</helix[^>]*>|/>)'
    matches = re.finditer(helix_pattern, page_source, re.IGNORECASE | re.DOTALL)
    
    for i, match in enumerate(matches):
        helix_elements.append({
            'element_id': f'helix_regex_{i}',
            'detection_type': 'regex_match',
            'tag_name': extract_tag_name_from_match(match.group()),
            'is_child_of_custom_block': 'unknown',
            'parent_block_id': 'unknown',
            'classes': 'extracted_from_regex',
            'text_content': extract_text_from_helix_match(match.group()),
            'text_length': len(extract_text_from_helix_match(match.group())),
            'word_count': len(extract_text_from_helix_match(match.group()).split()),
            'position_in_source': match.start(),
            'context': page_source[max(0, match.start()-100):match.end()+100],
            'matched_html': match.group()[:500] + '...' if len(match.group()) > 500 else match.group(),
            'attributes_json': '{}',
            'html_content': match.group()[:500] + '...' if len(match.group()) > 500 else match.group()
        })
    
    return helix_elements


def determine_block_category(element, classes):
    """Determine the category of the custom block"""
    class_string = ' '.join(classes).lower()
    
    if 'header' in class_string or 'navigation' in class_string or 'menu' in class_string:
        return 'Navigation/Header'
    elif 'hero' in class_string or 'banner' in class_string:
        return 'Hero/Banner'
    elif 'footer' in class_string:
        return 'Footer'
    elif 'content' in class_string or 'article' in class_string:
        return 'Content Block'
    elif 'sidebar' in class_string or 'aside' in class_string:
        return 'Sidebar'
    elif 'form' in class_string or 'input' in class_string:
        return 'Form Element'
    elif 'media' in class_string or 'image' in class_string or 'video' in class_string:
        return 'Media Block'
    elif 'card' in class_string or 'tile' in class_string:
        return 'Card/Tile'
    elif 'list' in class_string or 'grid' in class_string:
        return 'Layout/Grid'
    else:
        return 'Generic Block'


def generate_enhanced_label(element, classes, helix_children):
    """Generate an enhanced, descriptive label for the block"""
    tag = element.name.upper()
    element_id = element.get('id', 'no-id')
    
    # Get meaningful text content (first 50 chars)
    text_content = element.get_text(strip=True)[:50]
    text_preview = f" - '{text_content}...'" if len(text_content) > 47 else f" - '{text_content}'" if text_content else " - (no text)"
    
    # Include helix information if present
    helix_info = ""
    if helix_children:
        helix_types = list(set([child.name for child in helix_children]))
        helix_info = f" [Contains: {', '.join(helix_types)}]"
    
    return f"{tag}#{element_id}{text_preview}{helix_info}"


def calculate_content_metrics(element):
    """Calculate detailed content metrics"""
    text_content = element.get_text(strip=True)
    
    return {
        'total_text_length': len(text_content),
        'word_count': len(text_content.split()) if text_content else 0,
        'has_images': len(element.find_all('img')) > 0,
        'image_count': len(element.find_all('img')),
        'has_links': len(element.find_all('a')) > 0,
        'link_count': len(element.find_all('a')),
        'has_forms': len(element.find_all(['form', 'input', 'textarea', 'select'])) > 0,
        'form_element_count': len(element.find_all(['form', 'input', 'textarea', 'select'])),
        'nesting_depth': calculate_nesting_depth(element)
    }


def calculate_nesting_depth(element):
    """Calculate the maximum nesting depth"""
    def get_depth(elem, current_depth=0):
        if not elem.children:
            return current_depth
        max_child_depth = current_depth
        for child in elem.children:
            if hasattr(child, 'children'):
                child_depth = get_depth(child, current_depth + 1)
                max_child_depth = max(max_child_depth, child_depth)
        return max_child_depth
    
    return get_depth(element)


def extract_tag_name_from_match(html_match):
    """Extract tag name from regex match"""
    match = re.match(r'<(helix-[^>\s]+)', html_match, re.IGNORECASE)
    return match.group(1) if match else 'helix-unknown'


def extract_text_from_helix_match(html_match):
    """Extract text content from helix HTML match"""
    try:
        soup = BeautifulSoup(html_match, 'html.parser')
        return soup.get_text(strip=True)
    except:
        return ''


def create_csv_export(base_url, scrape_results, class_filter):
    """Create CSV files for the three main data types from sitemap scraping results"""
    
    # Create temporary directory for CSV files
    temp_dir = tempfile.mkdtemp()
    csv_files = []
    
    try:
        domain = urlparse(base_url).netloc.replace('.', '_')
        timestamp = int(time.time())
        
        custom_elements = scrape_results.get('custom_elements', [])
        helix_elements = scrape_results.get('helix_elements', [])
        summary = scrape_results.get('summary', {})
        
        # 1. Custom Class Elements CSV
        if custom_elements:
            custom_df = pd.DataFrame(custom_elements)
            custom_csv_path = os.path.join(temp_dir, f'custom_class_elements_{domain}_{timestamp}.csv')
            custom_df.to_csv(custom_csv_path, index=False, encoding='utf-8')
            csv_files.append(custom_csv_path)
        
        # 2. Helix Elements CSV
        if helix_elements:
            helix_df = pd.DataFrame(helix_elements)
            helix_csv_path = os.path.join(temp_dir, f'helix_elements_{domain}_{timestamp}.csv')
            helix_df.to_csv(helix_csv_path, index=False, encoding='utf-8')
            csv_files.append(helix_csv_path)
        
        # Create a comprehensive summary CSV
        summary_data = {
            'Website_URL': [base_url],
            'Analysis_Date': [time.strftime('%Y-%m-%d %H:%M:%S')],
            'Class_Filter': [class_filter],
            'Total_URLs_Processed': [summary.get('total_urls_processed', 0)],
            'Total_URLs_Failed': [summary.get('total_urls_failed', 0)],
            'Custom_Class_Elements_Count': [summary.get('custom_class_elements_count', 0)],
            'Helix_Elements_Count': [summary.get('helix_elements_count', 0)],
            'Total_Elements_Analyzed': [summary.get('total_elements', 0)]
        }
        summary_df = pd.DataFrame(summary_data)
        summary_csv_path = os.path.join(temp_dir, f'analysis_summary_{domain}_{timestamp}.csv')
        summary_df.to_csv(summary_csv_path, index=False, encoding='utf-8')
        csv_files.append(summary_csv_path)
        
        # Create a URL processing report CSV
        processed_urls = scrape_results.get('processed_urls', [])
        failed_urls = scrape_results.get('failed_urls', [])
        
        url_report_data = []
        for url in processed_urls:
            url_report_data.append({
                'URL': url,
                'Status': 'Success',
                'Error': '',
                'Custom_Elements': len([e for e in custom_elements if e.get('source_url') == url]),
                'Helix_Elements': len([e for e in helix_elements if e.get('source_url') == url])
            })
        
        for failed in failed_urls:
            url_report_data.append({
                'URL': failed.get('url', ''),
                'Status': 'Failed',
                'Error': failed.get('error', ''),
                'Custom_Elements': 0,
                'Helix_Elements': 0
            })
        
        if url_report_data:
            url_report_df = pd.DataFrame(url_report_data)
            url_report_csv_path = os.path.join(temp_dir, f'url_processing_report_{domain}_{timestamp}.csv')
            url_report_df.to_csv(url_report_csv_path, index=False, encoding='utf-8')
            csv_files.append(url_report_csv_path)
        
        # Create ZIP file containing all CSVs
        zip_path = tempfile.NamedTemporaryFile(delete=False, suffix='.zip').name
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for csv_file in csv_files:
                zipf.write(csv_file, os.path.basename(csv_file))
        
        return zip_path
        
    except Exception as e:
        logger.error(f"Error creating CSV export: {e}")
        return None


@app.route('/')
def index():
    """Main page with URL input form"""
    return render_template('enhanced_index.html')


@app.route('/analyze_page', methods=['POST'])
def analyze_page():
    print("Received request to analyze page")   
    """Analyze a single page and return summary"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        # Fetch the page
        soup, page_source, error = fetch_page(url)
        if error:
            return jsonify({'error': f'Error fetching URL: {error}'}), 400
        
        # Use simple analyzer
        analyzer = SimpleHomepageAnalyzer(url)

        print("Setting content for analysis")
        analyzer.set_content(page_source)
        # Add JS files to findings for later use
        findings = analyzer.analyze_all()
        print("Analyzing all content")
        print(analyzer.parser.scripts)
        findings['scripts'] = [script for script in analyzer.parser.scripts]
       
        
        if not findings:
            return jsonify({'error': 'Analysis failed'}), 500
        
        # Create summary for display
        summary = {
            'url': findings['url'],
            'page_title': findings['page_title'],
            'meta_description': findings['meta_description'][:100] + '...' if len(findings['meta_description']) > 100 else findings['meta_description'],
            'theme_info': findings['theme_info'],
            'helix_components': findings['helix_components'],
            'page_analytics': findings['page_analytics'],
            'statistics': {
                'total_components': len(findings['helix_components']),
                'total_instances': sum(comp['count'] for comp in findings['helix_components'].values()),
                'total_headings': findings['total_headings'],
                'total_links': findings['total_links'],
                'total_scripts': findings['total_scripts']
            }
        }
        
        
        # Determine architecture type
        all_versions = set()
        for comp_data in findings['helix_components'].values():
            all_versions.update(comp_data['versions'])


        if all_versions or summary['theme_info']['theme_system']:
            print(f"Found Helix component versions: {all_versions}")
                
            summary['component_versions'] = sorted(all_versions)
            if any(v.startswith('4.') for v in all_versions) or summary['theme_info']['theme_system'] == "helix-core-content":
                summary['architecture_type'] = 'Modern (4.x series)'
            elif any(v.startswith('3.') for v in all_versions) or summary['theme_info']['theme_system'] == "helix-web-components":
                summary['architecture_type'] = 'Legacy (3.x series)'
            else:
                # Enhanced: Check JS files for helix-core-image or helix-image
                js_files = findings.get('scripts', [])
                js_helix_version = None
                for js_url in js_files:
                    try:
                        # Only check external JS files (skip inline)
                        if js_url.startswith(('http://', 'https://')):
                            resp = requests.get(js_url, timeout=10)
                            if resp.status_code == 200:
                                js_content = resp.text
                                print(js_content)
                                if "helix-core-image" in js_content:
                                    js_helix_version = 'Modern (4.x series)'
                                    break
                                elif "helix-image" in js_content:
                                    js_helix_version = 'Legacy (3.x series)'
                                    # Don't break, prefer V2 if both found
                    except Exception as e:
                        logger.warning(f"Could not fetch JS file {js_url}: {e}")
                        continue
                if js_helix_version:
                    summary['architecture_type'] = f"{js_helix_version}"
                else:
                    summary['architecture_type'] = 'Unknown'
        else:
            summary['component_versions'] = []
            summary['architecture_type'] = 'No Helix components found'
        
        return jsonify({'success': True, 'summary': summary})
        
    except Exception as e:
        logger.error(f"Error in analyze_page: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/analyze_detailed', methods=['POST'])
def analyze_detailed():
    """Analyze a single page and return detailed findings"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        # Fetch the page
        soup, page_source, error = fetch_page(url)
        if error:
            return jsonify({'error': f'Error fetching URL: {error}'}), 400
        
        # Use simple analyzer
        analyzer = SimpleHomepageAnalyzer(url)
        analyzer.set_content(page_source)
        findings = analyzer.analyze_all()
        
        if not findings:
            return jsonify({'error': 'Analysis failed'}), 500
        
        # Capture print_findings output
        import io
        import sys
        
        old_stdout = sys.stdout
        sys.stdout = buffer = io.StringIO()
        
        try:
            analyzer.print_findings()
            detailed_output = buffer.getvalue()
        finally:
            sys.stdout = old_stdout
        
        return jsonify({
            'success': True, 
            'findings': findings,
            'detailed_output': detailed_output
        })
        
    except Exception as e:
        logger.error(f"Error in analyze_detailed: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/progress/<session_id>')
def progress_stream(session_id):
    """Server-Sent Events endpoint for real-time progress updates"""
    def generate():
        try:
            # Initial connection message
            yield "data: {\"status\": \"connected\", \"message\": \"Connected to progress stream\"}\n\n"
            
            # Check if session exists
            if session_id not in progress_sessions:
                yield f"data: {{\"status\": \"error\", \"message\": \"Session {session_id} not found\"}}\n\n"
                return
            
            while session_id in progress_sessions:
                session_data = progress_sessions[session_id]
                
                # Send current progress as JSON
                yield f"data: {json.dumps(session_data)}\n\n"
                
                # Check if processing is complete
                if session_data.get('status') in ['completed', 'error']:
                    # Keep session for a bit longer for download
                    yield f"data: {{\"status\": \"stream_complete\", \"message\": \"Progress stream ending\"}}\n\n"
                    break
                    
                time.sleep(1)  # Update every second
                
        except Exception as e:
            logger.error(f"Error in progress stream for session {session_id}: {e}")
            yield f"data: {{\"status\": \"error\", \"message\": \"Stream error: {str(e)}\"}}\n\n"
    
    response = Response(generate(), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['Connection'] = 'keep-alive'
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Cache-Control'
    return response


@app.route('/start_processing', methods=['POST'])
def start_processing():
    """Start processing and return session ID for progress tracking"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        class_filter = data.get('class_filter', 'custom-block-element').strip()
        max_pages = data.get('max_pages', '')
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        # Parse max_pages parameter
        max_pages_int = None
        if max_pages and str(max_pages).isdigit():
            max_pages_int = int(max_pages)
            if max_pages_int <= 0:
                max_pages_int = None
        
        # Create session ID for progress tracking
        session_id = f"session_{int(time.time())}_{hash(url) % 10000}"
        
        # Initialize progress session
        progress_sessions[session_id] = {
            'status': 'starting',
            'current_url': url,
            'urls_found': 0,
            'urls_processed': 0,
            'urls_failed': 0,
            'custom_elements': 0,
            'helix_elements': 0,
            'total_elements': 0,
            'progress_percentage': 0,
            'message': 'Starting analysis...',
            'processing_log': ['Analysis started'],
            'timestamp': time.time(),
            'last_updated': time.time()
        }
        
        # Start processing in a separate thread
        def background_processing():
            try:
                # Clean up old sessions before starting
                cleanup_old_sessions()
                
                process_sitemap_scraping(session_id, url, class_filter, max_pages_int)
            except Exception as e:
                logger.error(f"Background processing error for session {session_id}: {e}")
                if session_id in progress_sessions:
                    progress_sessions[session_id].update({
                        'status': 'error',
                        'message': f'Error: {str(e)}',
                        'last_updated': time.time()
                    })
                    progress_sessions[session_id]['processing_log'].append(f'Error: {str(e)}')
        
        # Start background thread
        threading.Thread(target=background_processing, daemon=True).start()
        
        return jsonify({'session_id': session_id, 'status': 'started'})
        
    except Exception as e:
        logger.error(f"Error starting processing: {e}")
        return jsonify({'error': str(e)}), 500


def process_sitemap_scraping(session_id, url, class_filter, max_pages_int):
    """Background function to process sitemap scraping"""
    try:
        if session_id not in progress_sessions:
            logger.error(f"Session {session_id} not found")
            return
            
        # Extract base URL for sitemap discovery
        parsed_url = urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        
        # Step 1: Try to find sitemap URLs
        logger.info(f"Discovering sitemap URLs for: {base_url}")
        progress_sessions[session_id].update({
            'status': 'discovering',
            'message': f'Discovering sitemap URLs for {base_url}...',
            'progress_percentage': 5,
            'last_updated': time.time()
        })
        progress_sessions[session_id]['processing_log'].append(f'Starting sitemap discovery for {base_url}')
        
        sitemap_urls = fetch_sitemap_urls(base_url)
        
        if not sitemap_urls:
            # Fallback: If no sitemap found, scrape the provided URL only
            logger.info("No sitemap found, scraping single URL")
            progress_sessions[session_id].update({
                'message': 'No sitemap found, analyzing single page...',
                'urls_found': 1,
                'progress_percentage': 10,
                'last_updated': time.time()
            })
            progress_sessions[session_id]['processing_log'].append('No sitemap found, falling back to single page analysis')
            
            soup, page_source, error = fetch_page(url)
            if error:
                progress_sessions[session_id].update({
                    'status': 'error',
                    'message': f'Error fetching URL: {error}',
                    'last_updated': time.time()
                })
                progress_sessions[session_id]['processing_log'].append(f'Error: {error}')
                return
            
            # Run enhanced analyses
            custom_elements = find_enhanced_custom_class_elements(soup, class_filter)
            helix_elements = find_enhanced_helix_elements(soup, page_source)
            
            # Add source URL to elements
            for element in custom_elements:
                element['source_url'] = url
                element['page_title'] = soup.title.string if soup.title else 'No Title'
            
            for element in helix_elements:
                element['source_url'] = url
                element['page_title'] = soup.title.string if soup.title else 'No Title'
            
            # Update progress
            progress_sessions[session_id].update({
                'urls_processed': 1,
                'custom_elements': len(custom_elements),
                'helix_elements': len(helix_elements),
                'total_elements': len(custom_elements) + len(helix_elements),
                'progress_percentage': 90,
                'message': 'Single page analysis complete'
            })
            
            scrape_results = {
                'custom_elements': custom_elements,
                'helix_elements': helix_elements,
                'processed_urls': [url],
                'failed_urls': [],
                'summary': {
                    'total_urls_processed': 1,
                    'total_urls_failed': 0,
                    'custom_class_elements_count': len(custom_elements),
                    'helix_elements_count': len(helix_elements),
                    'total_elements': len(custom_elements) + len(helix_elements)
                }
            }
        else:
            # Step 2: Scrape all sitemap URLs
            total_urls = len(sitemap_urls)
            if max_pages_int:
                total_urls = min(total_urls, max_pages_int)
            
            logger.info(f"Found {len(sitemap_urls)} URLs in sitemap, processing {total_urls} pages")
            progress_sessions[session_id].update({
                'urls_found': total_urls,
                'message': f'Found {len(sitemap_urls)} URLs in sitemap, processing {total_urls} pages...',
                'progress_percentage': 10
            })
            progress_sessions[session_id]['processing_log'].append(f'Found {len(sitemap_urls)} URLs in sitemap')
            
            # Define progress callback for real-time updates
            def progress_callback(current, total, current_url, custom_count, helix_count):
                progress_percentage = 10 + int((current / total) * 80)  # 10-90%
                total_elements = custom_count + helix_count
                
                progress_sessions[session_id].update({
                    'current_url': current_url,
                    'urls_processed': current,
                    'custom_elements': custom_count,
                    'helix_elements': helix_count,
                    'total_elements': total_elements,
                    'progress_percentage': progress_percentage,
                    'message': f'Processing page {current} of {total}...'
                })
                
                if current % 5 == 0:  # Log every 5th URL
                    progress_sessions[session_id]['processing_log'].append(f'Processed {current}/{total} pages, found {total_elements} elements')
            
            # Scrape all URLs from sitemap
            scrape_results = scrape_multiple_urls_with_progress(
                sitemap_urls, 
                class_filter, 
                max_pages_int, 
                progress_callback,
                session_id
            )
        
        # Step 3: Create CSV export
        progress_sessions[session_id].update({
            'progress_percentage': 95,
            'message': 'Creating CSV export...',
            'last_updated': time.time()
        })
        progress_sessions[session_id]['processing_log'].append('Creating CSV export package...')
        
        zip_file = create_csv_export(base_url, scrape_results, class_filter)
        
        if not zip_file:
            progress_sessions[session_id].update({
                'status': 'error',
                'message': 'Error creating CSV export',
                'last_updated': time.time()
            })
            progress_sessions[session_id]['processing_log'].append('Error: Failed to create CSV export')
            return
        
        # Store the zip file path in the session for download
        progress_sessions[session_id]['zip_file'] = zip_file
        progress_sessions[session_id]['download_filename'] = f"sitemap_scraper_csv_export_{urlparse(base_url).netloc.replace('.', '_')}_{int(time.time())}.zip"
        
        # Complete processing
        progress_sessions[session_id].update({
            'status': 'completed',
            'progress_percentage': 100,
            'message': 'Analysis complete! Click to download results.',
            'last_updated': time.time()
        })
        progress_sessions[session_id]['processing_log'].append(f'Analysis completed successfully! Found {scrape_results["summary"]["total_elements"]} total elements.')
        
    except Exception as e:
        logger.error(f"Error in background processing: {e}")
        if session_id in progress_sessions:
            progress_sessions[session_id].update({
                'status': 'error',
                'message': f'Error: {str(e)}',
                'last_updated': time.time()
            })
            if 'processing_log' not in progress_sessions[session_id]:
                progress_sessions[session_id]['processing_log'] = []
            progress_sessions[session_id]['processing_log'].append(f'Error: {str(e)}')


@app.route('/download/<session_id>')
def download_results(session_id):
    """Download the results for a completed session"""
    if session_id not in progress_sessions:
        return "Session not found", 404
    
    session_data = progress_sessions[session_id]
    if session_data.get('status') != 'completed':
        return "Session not completed", 400
    
    zip_file = session_data.get('zip_file')
    download_filename = session_data.get('download_filename', 'results.zip')
    
    if not zip_file or not os.path.exists(zip_file):
        return "Results file not found", 404
    
    # Clean up session after download
    def cleanup():
        time.sleep(60)  # Wait a minute before cleanup
        if session_id in progress_sessions:
            zip_file_path = progress_sessions[session_id].get('zip_file')
            if zip_file_path and os.path.exists(zip_file_path):
                try:
                    os.unlink(zip_file_path)
                except:
                    pass
            del progress_sessions[session_id]
    
    threading.Thread(target=cleanup, daemon=True).start()
    
    return send_file(
        zip_file,
        as_attachment=True,
        download_name=download_filename,
        mimetype='application/zip'
    )


@app.route('/scrape', methods=['POST'])
def scrape():
    """Handle URL scraping request with sitemap processing and return CSV export"""
    try:
        url = request.form.get('url', '').strip()
        class_filter = request.form.get('class_filter', 'custom-block-element').strip()
        max_pages = request.form.get('max_pages', '').strip()
        
        if not url:
            flash('Please enter a URL', 'error')
            return redirect(url_for('index'))
        
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        # Parse max_pages parameter
        max_pages_int = None
        if max_pages and max_pages.isdigit():
            max_pages_int = int(max_pages)
            if max_pages_int <= 0:
                max_pages_int = None
        
        # Create session ID for progress tracking
        session_id = f"session_{int(time.time())}_{hash(url) % 10000}"
        
        # Initialize progress session
        progress_sessions[session_id] = {
            'status': 'discovering',
            'current_url': url,
            'urls_found': 0,
            'urls_processed': 0,
            'urls_failed': 0,
            'custom_elements': 0,
            'helix_elements': 0,
            'total_elements': 0,
            'progress_percentage': 0,
            'message': 'Discovering sitemap URLs...',
            'processing_log': []
        }
        
        # Extract base URL for sitemap discovery
        parsed_url = urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        
        # Step 1: Try to find sitemap URLs
        logger.info(f"Discovering sitemap URLs for: {base_url}")
        progress_sessions[session_id]['message'] = f'Discovering sitemap URLs for {base_url}...'
        progress_sessions[session_id]['processing_log'].append(f'Starting sitemap discovery for {base_url}')
        
        sitemap_urls = fetch_sitemap_urls(base_url)
        
        if not sitemap_urls:
            # Fallback: If no sitemap found, scrape the provided URL only
            logger.info("No sitemap found, scraping single URL")
            progress_sessions[session_id]['message'] = 'No sitemap found, analyzing single page...'
            progress_sessions[session_id]['processing_log'].append('No sitemap found, falling back to single page analysis')
            progress_sessions[session_id]['urls_found'] = 1
            
            soup, page_source, error = fetch_page(url)
            if error:
                progress_sessions[session_id]['status'] = 'error'
                progress_sessions[session_id]['message'] = f'Error fetching URL: {error}'
                flash(f'Error fetching URL: {error}', 'error')
                return redirect(url_for('index'))
            
            # Run enhanced analyses
            custom_elements = find_enhanced_custom_class_elements(soup, class_filter)
            helix_elements = find_enhanced_helix_elements(soup, page_source)
            
            # Add source URL to elements
            for element in custom_elements:
                element['source_url'] = url
                element['page_title'] = soup.title.string if soup.title else 'No Title'
            
            for element in helix_elements:
                element['source_url'] = url
                element['page_title'] = soup.title.string if soup.title else 'No Title'
            
            # Update progress
            progress_sessions[session_id].update({
                'urls_processed': 1,
                'custom_elements': len(custom_elements),
                'helix_elements': len(helix_elements),
                'total_elements': len(custom_elements) + len(helix_elements),
                'progress_percentage': 90,
                'message': 'Analysis complete, generating CSV...'
            })
            
            # Create results structure
            scrape_results = {
                'custom_elements': custom_elements,
                'helix_elements': helix_elements,
                'processed_urls': [url],
                'failed_urls': [],
                'summary': {
                    'total_urls_processed': 1,
                    'total_urls_failed': 0,
                    'custom_class_elements_count': len(custom_elements),
                    'helix_elements_count': len(helix_elements),
                    'total_elements': len(custom_elements) + len(helix_elements)
                }
            }
        else:
            # Step 2: Scrape all sitemap URLs
            total_urls = len(sitemap_urls)
            if max_pages_int:
                total_urls = min(total_urls, max_pages_int)
            
            logger.info(f"Found {len(sitemap_urls)} URLs in sitemap, processing {total_urls} pages")
            progress_sessions[session_id].update({
                'urls_found': total_urls,
                'message': f'Found {len(sitemap_urls)} URLs in sitemap, processing {total_urls} pages...',
                'progress_percentage': 10
            })
            progress_sessions[session_id]['processing_log'].append(f'Found {len(sitemap_urls)} URLs in sitemap')
            
            # Define progress callback for real-time updates
            def progress_callback(current, total, current_url, custom_count, helix_count):
                progress_percentage = 10 + int((current / total) * 80)  # 10-90%
                total_elements = custom_count + helix_count
                
                progress_sessions[session_id].update({
                    'current_url': current_url,
                    'urls_processed': current,
                    'custom_elements': custom_count,
                    'helix_elements': helix_count,
                    'total_elements': total_elements,
                    'progress_percentage': progress_percentage,
                    'message': f'Processing page {current} of {total}...'
                })
                
                if current % 5 == 0:  # Log every 5th URL
                    progress_sessions[session_id]['processing_log'].append(f'Processed {current}/{total} pages, found {total_elements} elements')
            
            # Scrape all URLs from sitemap
            scrape_results = scrape_multiple_urls_with_progress(
                sitemap_urls, 
                class_filter, 
                max_pages_int, 
                progress_callback,
                session_id
            )
        
        # Step 3: Create CSV export
        progress_sessions[session_id].update({
            'progress_percentage': 95,
            'message': 'Creating CSV export...'
        })
        
        zip_file = create_csv_export(base_url, scrape_results, class_filter)
        
        if not zip_file:
            progress_sessions[session_id]['status'] = 'error'
            progress_sessions[session_id]['message'] = 'Error creating CSV export'
            flash('Error creating CSV export', 'error')
            return redirect(url_for('index'))
        
        # Complete processing
        progress_sessions[session_id].update({
            'status': 'completed',
            'progress_percentage': 100,
            'message': 'Analysis complete! Download ready.'
        })
        
        # Generate filename for download
        domain = urlparse(base_url).netloc.replace('.', '_')
        download_filename = f"sitemap_scraper_csv_export_{domain}_{int(time.time())}.zip"
        
        # Add success message with summary
        summary = scrape_results['summary']
        flash(f'Analysis complete! Processed {summary["total_urls_processed"]} URLs, '
              f'found {summary["total_elements"]} total elements', 'success')
        
        return send_file(
            zip_file,
            as_attachment=True,
            download_name=download_filename,
            mimetype='application/zip'
        )
        
    except Exception as e:
        logger.error(f"Error in scrape route: {e}")
        if 'session_id' in locals():
            progress_sessions[session_id]['status'] = 'error'
            progress_sessions[session_id]['message'] = f'Error: {str(e)}'
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('index'))


@app.route('/api/scrape', methods=['POST'])
def api_scrape():
    """API endpoint for programmatic access with sitemap support"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        class_filter = data.get('class_filter', 'custom-block-element').strip()
        max_pages = data.get('max_pages', None)
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        # Parse max_pages parameter
        max_pages_int = None
        if max_pages and isinstance(max_pages, int) and max_pages > 0:
            max_pages_int = max_pages
        
        # Extract base URL for sitemap discovery
        parsed_url = urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        
        # Step 1: Try to find sitemap URLs
        logger.info(f"API: Discovering sitemap URLs for: {base_url}")
        sitemap_urls = fetch_sitemap_urls(base_url)
        
        if not sitemap_urls:
            # Fallback: If no sitemap found, scrape the provided URL only
            logger.info("API: No sitemap found, scraping single URL")
            
            soup, page_source, error = fetch_page(url)
            if error:
                return jsonify({'error': f'Error fetching URL: {error}'}), 400
            
            # Run enhanced analyses
            custom_elements = find_enhanced_custom_class_elements(soup, class_filter)
            helix_elements = find_enhanced_helix_elements(soup, page_source)
            
            # Add source URL to elements
            for element in custom_elements:
                element['source_url'] = url
                element['page_title'] = soup.title.string if soup.title else 'No Title'
            
            for element in helix_elements:
                element['source_url'] = url
                element['page_title'] = soup.title.string if soup.title else 'No Title'
            
            # Create results structure
            scrape_results = {
                'custom_elements': custom_elements,
                'helix_elements': helix_elements,
                'processed_urls': [url],
                'failed_urls': [],
                'summary': {
                    'total_urls_processed': 1,
                    'total_urls_failed': 0,
                    'custom_class_elements_count': len(custom_elements),
                    'helix_elements_count': len(helix_elements),
                    'total_elements': len(custom_elements) + len(helix_elements)
                }
            }
        else:
            # Step 2: Scrape all sitemap URLs
            total_urls = len(sitemap_urls)
            if max_pages_int:
                total_urls = min(total_urls, max_pages_int)
            
            logger.info(f"API: Found {len(sitemap_urls)} URLs in sitemap, processing {total_urls} pages")
            
            # Scrape all URLs from sitemap
            scrape_results = scrape_multiple_urls(
                sitemap_urls, 
                class_filter, 
                max_pages_int
            )
        
        # Enhanced response with sitemap data
        response_data = {
            'base_url': base_url,
            'original_url': url,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'class_filter': class_filter,
            'sitemap_info': {
                'sitemap_urls_found': len(sitemap_urls),
                'urls_processed': scrape_results['summary']['total_urls_processed'],
                'urls_failed': scrape_results['summary']['total_urls_failed']
            },
            'summary': scrape_results['summary'],
            'data': {
                'custom_class_elements': scrape_results['custom_elements'],
                'helix_elements': scrape_results['helix_elements']
            },
            'processing_report': {
                'processed_urls': scrape_results['processed_urls'],
                'failed_urls': scrape_results['failed_urls']
            }
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Error in API scrape: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/upload_csv', methods=['POST'])
def upload_csv():
    """Upload a CSV file and process the sitemap URLs"""
    if 'file' not in request.files:
        flash('No file part')
        return redirect(request.url)

    file = request.files['file']
    if file.filename == '':
        flash('No selected file')
        return redirect(request.url)

    if file and file.filename.endswith('.csv'):
        filename = secure_filename(file.filename)
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)

        # Read the CSV file
        try:
            df = pd.read_csv(file_path)
            urls = df['URL'].tolist()

            # Process the URLs
            scrape_results = scrape_multiple_urls(urls)

            # Export the results to CSV
            zip_path = create_csv_export(request.url_root, scrape_results, 'custom-block-element')

            return send_file(zip_path, as_attachment=True)
        except Exception as e:
            logger.error(f"Error processing CSV file: {e}")
            flash('Error processing the file')
            return redirect(request.url)

    flash('Invalid file format. Please upload a CSV file.')
    return redirect(request.url)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5004)
