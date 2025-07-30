#!/usr/bin/env python3
"""
CSV Export Test Script
======================

Test the CSV export functionality with sample data.
"""

import sys
import os
import pandas as pd
sys.path.append('/Applications/Projects/poc/pythonscript')

from enhanced_web_scraper import *


def test_csv_export():
    """Test CSV export functionality"""
    
    print("🧪 Testing CSV Export Functionality")
    print("=" * 40)
    
    # Test URL
    test_url = "https://16375504.livepreview.pfizer/"
    
    print(f"🌐 Testing URL: {test_url}")
    
    # Fetch the page
    soup, page_source, error = fetch_page(test_url)
    if error:
        print(f"❌ Error fetching page: {error}")
        return
    
    print("✅ Page fetched successfully")
    
    # Run analyses
    print("\n📊 Running Enhanced Analyses...")
    
    custom_elements = find_enhanced_custom_class_elements(soup, "custom-block-element")
    print(f"✓ Custom Class Elements: {len(custom_elements)}")
    
    shadow_elements = find_enhanced_shadow_root_elements(soup, page_source)
    print(f"✓ Shadow Root Elements: {len(shadow_elements)}")
    
    helix_elements = find_enhanced_helix_elements(soup, page_source)
    print(f"✓ Helix Elements: {len(helix_elements)}")
    
    # Test CSV creation
    print("\n📝 Creating CSV Export...")
    
    zip_file = create_csv_export(test_url, custom_elements, shadow_elements, helix_elements, "custom-block-element")
    
    if zip_file:
        print(f"✅ CSV Export created: {zip_file}")
        
        # Check file size
        file_size = os.path.getsize(zip_file)
        print(f"📦 ZIP file size: {file_size:,} bytes")
        
        # Extract and preview first few rows of each CSV
        print("\n📋 CSV Content Preview:")
        
        import zipfile
        with zipfile.ZipFile(zip_file, 'r') as zf:
            for filename in zf.namelist():
                print(f"\n📄 {filename}:")
                with zf.open(filename) as f:
                    try:
                        df = pd.read_csv(f)
                        print(f"   Rows: {len(df)}, Columns: {len(df.columns)}")
                        print(f"   Columns: {', '.join(df.columns[:5])}{'...' if len(df.columns) > 5 else ''}")
                        if len(df) > 0:
                            print(f"   Sample data: {str(df.iloc[0, 0])[:50]}{'...' if len(str(df.iloc[0, 0])) > 50 else ''}")
                    except Exception as e:
                        print(f"   Error reading CSV: {e}")
        
        # Clean up
        os.unlink(zip_file)
        print(f"\n🧹 Test file cleaned up")
        
    else:
        print("❌ Failed to create CSV export")
    
    # Display sample data structure
    if custom_elements:
        print(f"\n📊 Sample Custom Class Element Data:")
        sample = custom_elements[0]
        for key, value in list(sample.items())[:8]:
            print(f"   {key}: {str(value)[:80]}{'...' if len(str(value)) > 80 else ''}")
    
    if shadow_elements:
        print(f"\n🌑 Sample Shadow Root Element Data:")
        sample = shadow_elements[0]
        for key, value in list(sample.items())[:6]:
            print(f"   {key}: {str(value)[:80]}{'...' if len(str(value)) > 80 else ''}")
    
    if helix_elements:
        print(f"\n🧬 Sample Helix Element Data:")
        sample = helix_elements[0]
        for key, value in list(sample.items())[:8]:
            print(f"   {key}: {str(value)[:80]}{'...' if len(str(value)) > 80 else ''}")
    
    print(f"\n✅ CSV Export Test Complete!")
    print("=" * 40)


if __name__ == "__main__":
    test_csv_export()
