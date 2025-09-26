#!/usr/bin/env python3
"""
Test the actual call_ollama function from the Django application.
"""
import os
import sys

# Add the current directory to Python path to import Django modules
sys.path.append('/Applications/Projects/commit_v1_v2/tag_manager')

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tag_manager.settings')

import django
django.setup()

# Now import the function from your API component
from api_component.ollama_api import call_ollama

def test_call_ollama():
    """Test the call_ollama function directly."""
    
    print("🧪 Testing call_ollama function")
    print("=" * 40)
    
    # Check function signature
    import inspect
    sig = inspect.signature(call_ollama)
    print(f"Function signature: call_ollama{sig}")
    
    # Test with a simple prompt
    test_prompt = "Convert <helix-image> to <helix-core-image>"
    
    print(f"Input prompt: {test_prompt}")
    print("Calling call_ollama...")
    
    try:
        result = call_ollama(test_prompt)
        
        if result:
            print("✅ call_ollama succeeded!")
            print(f"Result preview: {result[:100]}...")
        else:
            print("❌ call_ollama returned empty result")
            
    except Exception as e:
        print(f"❌ call_ollama failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_call_ollama()