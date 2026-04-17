#!/usr/bin/env python3
"""
Convert CSV assets report to Step 6 JSON format for WebBuilder
"""

import csv
import json
import os
from pathlib import Path
from collections import defaultdict
import uuid


def csv_to_step6_json(csv_path: Path, output_dir: Path):
    """
    Convert CSV assets report to Step 6 JSON files
    
    Creates:
    - files/{filename}.json for each unique file
    - pages/{pagename}.json for each page
    """
    
    print(f"Reading CSV: {csv_path}")
    
    # Read CSV data
    rows = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    
    print(f"Total rows: {len(rows)}")
    
    # Group by file - to create file configurations
    # Each file needs: pages, category, weight, filepath, header/footer flags
    files_data = defaultdict(lambda: {
        'pages': {},
        'category': '',
        'weight': '0',
        'filepath': '',
        'header_file': False,
        'footer_file': False,
        'async': False,
        'attributes': ''
    })
    
    # Group by page - to create page configurations
    # Generate UUIDs for each page
    pages_data = {}
    page_uuids = {}  # Map page names to UUIDs
    
    for row in rows:
        page_name = row['Page Name']
        file_name = row['CSS/JS File Name']
        attributes = row['CSS/JS File Attributes']
        location = row['Attachment Location']  # Header or Footer
        origin = row['Internal/External']
        asset_type = row['Type']
        
        # Skip external files (they don't need to be in WebBuilder)
        if origin == 'External':
            continue
            
        # Extract actual filename from URL/path
        if '/' in file_name:
            file_name = file_name.split('/')[-1]
        
        # Clean up filename
        file_name = file_name.strip()
        if not file_name:
            continue
            
        # Determine file category
        category = asset_type.lower()
        if category == 'js':
            category = 'JS'
        elif category == 'css':
            category = 'CSS'
        elif category in ['font', 'image']:
            category = 'image'  # WebBuilder groups fonts with images
        else:
            category = 'other'
        
        # Determine filepath based on type
        filepath = ''
        if file_name.endswith('.js'):
            filepath = 'js'
        elif file_name.endswith('.css'):
            filepath = 'css'
        elif any(file_name.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.woff', '.woff2', '.ttf', '.eot']):
            filepath = 'images'
        
        # Determine header/footer placement
        header_file = (location == 'Header')
        footer_file = (location == 'Footer')
        
        # Check for async attribute
        async_loading = 'async' in attributes.lower()
        
        # Add to files_data using UUID as key
        page_uuid = page_uuids.get(page_name, str(uuid.uuid4()))
        files_data[file_name]['pages'][page_uuid] = True
        files_data[file_name]['category'] = category
        files_data[file_name]['filepath'] = filepath
        files_data[file_name]['header_file'] = header_file
        files_data[file_name]['footer_file'] = footer_file
        files_data[file_name]['async'] = async_loading
        
        # Preserve non-empty attributes - if any row has attributes, keep them
        # This handles files that appear in multiple rows with different attribute values
        if attributes and attributes.strip():
            # Only update if current value is empty or this is a more specific value
            current_attrs = files_data[file_name].get('attributes', '')
            if not current_attrs or attributes.lower() in ['async', 'defer']:
                files_data[file_name]['attributes'] = attributes.strip()
        
        # Add to pages_data with UUID
        if page_name not in pages_data:
            page_uuid = str(uuid.uuid4())
            page_uuids[page_name] = page_uuid
            pages_data[page_name] = {'settings': {'title': page_name, 'uuid': page_uuid}}
    
    print(f"Unique files: {len(files_data)}")
    print(f"Unique pages: {len(pages_data)}")
    
    # Create output directories
    files_dir = output_dir / 'files'
    pages_dir = output_dir / 'pages'
    files_dir.mkdir(parents=True, exist_ok=True)
    pages_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate file JSON files
    files_created = 0
    for filename, data in files_data.items():
        # Create filename for JSON (sanitize)
        json_filename = f"{filename}.json"
        json_path = files_dir / json_filename
        
        # Build the JSON structure matching Step 6 format
        file_json = {
            "filename": filename,
            "details": {
                "filename": filename,
                "filepath": data['filepath'],
                "url": f"/{data['filepath']}/{filename}" if data['filepath'] else f"/{filename}",
                "category": data['category'],
                "only_on_deployment": False,
                "deploy_on": "All Environments",
                "weight": data['weight'],
                "pages": data['pages'],
                "private": False,
                "footer_file": data['footer_file'],
                "header_file": data['header_file'],
                "async": data['async'],
                "modular": False,
                "attributes": data['attributes']
            }
        }
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(file_json, f, indent=2, ensure_ascii=False)
        files_created += 1
    
    # Generate page JSON files
    pages_created = 0
    for page_name, data in pages_data.items():
        # Create safe filename
        safe_name = page_name.replace(' ', '_').replace('/', '_')
        json_filename = f"{safe_name}.json"
        json_path = pages_dir / json_filename
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        pages_created += 1
    
    print(f"\n✅ JSON files created:")
    print(f"   Files: {files_created} in {files_dir}")
    print(f"   Pages: {pages_created} in {pages_dir}")
    
    # Show sample
    if files_data:
        sample_file = list(files_data.keys())[0]
        sample_path = files_dir / f"{sample_file}.json"
        print(f"\n📄 Sample file JSON ({sample_file}):")
        with open(sample_path, 'r') as f:
            print(f.read()[:800] + "...")
    
    return files_created, pages_created


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Convert CSV assets report to Step 6 JSON files"
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("pfizer_assets.csv"),
        help="Input CSV file (default: pfizer_assets.csv)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("step6_input"),
        help="Output directory for JSON files (default: step6_input)",
    )
    
    args = parser.parse_args()
    
    # Resolve paths
    csv_path = args.csv.resolve()
    output_dir = args.output.resolve()
    
    print("=" * 60)
    print("CSV to Step 6 JSON Converter")
    print("=" * 60)
    print(f"Input CSV: {csv_path}")
    print(f"Output dir: {output_dir}")
    print("=" * 60)
    
    if not csv_path.exists():
        print(f"❌ Error: CSV file not found: {csv_path}")
        return 1
    
    try:
        files_count, pages_count = csv_to_step6_json(csv_path, output_dir)
        print(f"\n🎉 Success! Generated {files_count} file configs and {pages_count} page configs")
        print(f"\nNext step: Copy these files to:")
        print(f"   {output_dir}/files/*  →  static/block_import/data/files/")
        print(f"   {output_dir}/pages/*  →  static/block_import/data/pages/")
        return 0
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
