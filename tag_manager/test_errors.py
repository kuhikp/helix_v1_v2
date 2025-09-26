#!/usr/bin/env python3
"""
Error Handler Test Script
This script helps test custom error handlers by temporarily setting DEBUG=False
"""

import os
import sys
from pathlib import Path

def toggle_debug_mode(debug_state=False):
    """Toggle DEBUG mode in settings.py"""
    
    # Get the settings file path
    settings_file = Path(__file__).parent / 'tag_manager' / 'settings.py'
    
    if not settings_file.exists():
        print(f"❌ Settings file not found: {settings_file}")
        return False
    
    # Read current settings
    with open(settings_file, 'r') as f:
        content = f.read()
    
    # Update DEBUG setting
    if debug_state:
        new_content = content.replace('DEBUG = False', 'DEBUG = True')
        mode_text = "ENABLED"
    else:
        new_content = content.replace('DEBUG = True', 'DEBUG = False')
        mode_text = "DISABLED"
    
    # Write back the changes
    with open(settings_file, 'w') as f:
        f.write(new_content)
    
    print(f"✅ DEBUG mode {mode_text} in settings.py")
    return True

def show_test_urls():
    """Display available test URLs for error handlers"""
    print("\n🔗 Test URLs available:")
    print("━" * 50)
    print("404 Error: http://localhost:8010/auth/test/404/")
    print("500 Error: http://localhost:8010/auth/test/500/")  
    print("403 Error: http://localhost:8010/auth/test/403/")
    print("Non-existent URL: http://localhost:8010/nonexistent/")
    print("━" * 50)

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python test_errors.py disable  # Disable DEBUG to test error handlers")
        print("  python test_errors.py enable   # Enable DEBUG for development")
        print("  python test_errors.py urls     # Show test URLs")
        return
    
    command = sys.argv[1].lower()
    
    if command == 'disable':
        if toggle_debug_mode(debug_state=False):
            print("\n🚨 ERROR HANDLERS ACTIVE")
            print("   Custom 404 and 500 pages will now be shown")
            print("   Other errors (400, 403, etc.) will show 404 page as configured")
            show_test_urls()
            print("\n💡 Remember to run 'python test_errors.py enable' when done testing!")
    
    elif command == 'enable':
        if toggle_debug_mode(debug_state=True):
            print("\n🛠️  DEVELOPMENT MODE ACTIVE")
            print("   Django debug pages will be shown for all errors")
            print("   Custom error handlers are disabled")
    
    elif command == 'urls':
        show_test_urls()
    
    else:
        print(f"❌ Unknown command: {command}")
        print("Available commands: disable, enable, urls")

if __name__ == '__main__':
    main()
