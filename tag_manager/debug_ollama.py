#!/usr/bin/env python3
"""
Debug script to test Ollama API connection and identify the 404 error.
"""

import requests
import json
import os
import sys

def test_ollama_connection():
    """Test Ollama API connection step by step."""
    
    print("🔍 Debugging Ollama API Connection")
    print("=" * 50)
    
    # Test 1: Check if Ollama service is running
    print("\n1. Testing Ollama service availability...")
    try:
        response = requests.get("http://localhost:11434/api/version", timeout=5)
        if response.status_code == 200:
            version_data = response.json()
            print(f"✅ Ollama service is running - Version: {version_data.get('version', 'unknown')}")
        else:
            print(f"❌ Ollama version check failed with status: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to Ollama service. Is it running?")
        print("💡 Try running: ollama serve")
        return False
    except Exception as e:
        print(f"❌ Error checking Ollama version: {e}")
        return False
    
    # Test 2: List available models
    print("\n2. Checking available models...")
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            models_data = response.json()
            models = models_data.get('models', [])
            if models:
                print(f"✅ Found {len(models)} models:")
                for model in models[:3]:  # Show first 3 models
                    print(f"   - {model.get('name', 'unknown')}")
            else:
                print("⚠️  No models found")
        else:
            print(f"❌ Models check failed with status: {response.status_code}")
    except Exception as e:
        print(f"❌ Error checking models: {e}")
    
    # Test 3: Test the exact same endpoint and payload as the code
    print("\n3. Testing /api/generate endpoint...")
    
    url = "http://localhost:11434/api/generate"
    
    # Use the same model selection logic as the original code
    llm_model = os.getenv('LLM_MODEL', 'llama3')
    if not llm_model:
        llm_model = "llama3"
    
    print(f"   Using model: {llm_model}")
    
    payload = {
        "model": llm_model,
        "prompt": "Test prompt: Convert <helix-image> to <helix-core-image>",
        "stream": False,
        "system": "You are a precise HTML migration tool. Return ONLY the migrated HTML content.",
        "options": {
            "temperature": 0,
            "top_p": 1,
            "repeat_penalty": 1,
        },
    }
    
    print(f"   Request URL: {url}")
    print(f"   Payload model: {payload['model']}")
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        print(f"   Response status: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ API call successful!")
            data = response.json()
            if 'response' in data:
                response_text = data['response'][:100] + "..." if len(data['response']) > 100 else data['response']
                print(f"   Response preview: {response_text}")
            else:
                print(f"   Unexpected response format: {list(data.keys())}")
        elif response.status_code == 404:
            print("❌ 404 Not Found - API endpoint doesn't exist")
            print(f"   Response text: {response.text}")
            print("💡 This might mean:")
            print("      - Ollama version is too old")
            print("      - API endpoint has changed")
            print("      - Model name is invalid")
        else:
            print(f"❌ Request failed with status {response.status_code}")
            print(f"   Response: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Connection error - service might not be running")
    except requests.exceptions.Timeout:
        print("❌ Request timed out")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    
    # Test 4: Try with a specific model that we know exists
    print("\n4. Testing with llama3:latest specifically...")
    try:
        test_payload = {
            "model": "llama3:latest",
            "prompt": "Hello",
            "stream": False
        }
        
        response = requests.post(url, json=test_payload, timeout=30)
        print(f"   Status with llama3:latest: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ llama3:latest works!")
        else:
            print(f"❌ llama3:latest failed: {response.text}")
            
    except Exception as e:
        print(f"❌ Error testing llama3:latest: {e}")
    
    # Test 5: Environment variables
    print("\n5. Checking environment variables...")
    print(f"   LLM_MODEL: {os.getenv('LLM_MODEL', 'Not set')}")
    print(f"   OLLAMA_BASE_URL: {os.getenv('OLLAMA_BASE_URL', 'Not set')}")
    
    print("\n" + "=" * 50)
    print("🔧 Recommendations:")
    print("1. Make sure Ollama is running: ollama serve")
    print("2. Check available models: ollama list")
    print("3. Try setting LLM_MODEL environment variable to a valid model name")
    print("4. Ensure model name matches exactly (including :latest tag if needed)")

if __name__ == "__main__":
    test_ollama_connection()