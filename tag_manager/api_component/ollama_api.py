import requests
import json
import re
import os
from bs4 import BeautifulSoup

def analyze_transformation_patterns(mapping_dict):
    """
    Dynamically analyze transformation patterns from the mapping dictionary.
    
    Args:
        mapping_dict (dict): Dictionary with V1 -> V2 mappings
        
    Returns:
        dict: Structured transformation rules
    """
    transformation_rules = {}
    
    for old_html, new_html in mapping_dict.items():
        try:
            # Extract tag names
            old_tag_match = re.search(r'<(helix-[^>\s]+)', old_html)
            new_tag_match = re.search(r'<(helix-[^>\s]+)', new_html)
            
            if not old_tag_match or not new_tag_match:
                continue
                
            old_tag = old_tag_match.group(1)
            new_tag = new_tag_match.group(1)
            
            # Extract attributes using regex (more reliable than BeautifulSoup for this case)
            old_attrs = dict(re.findall(r'(\w+(?:-\w+)*)="([^"]*)"', old_html))
            new_attrs = dict(re.findall(r'(\w+(?:-\w+)*)="([^"]*)"', new_html))
            
            # Analyze attribute changes
            added_attrs = {}
            removed_attrs = set()
            modified_attrs = {}
            preserved_attrs = {}
            
            # Find added attributes
            for attr, value in new_attrs.items():
                if attr not in old_attrs:
                    added_attrs[attr] = value
                elif old_attrs[attr] != value:
                    modified_attrs[attr] = {'old': old_attrs[attr], 'new': value}
                else:
                    preserved_attrs[attr] = value
            
            # Find removed attributes
            for attr in old_attrs:
                if attr not in new_attrs:
                    removed_attrs.add(attr)
            
            # Analyze nested content structure changes
            nested_changes = {}
            old_inner = re.search(r'>(.*)</', old_html, re.DOTALL)
            new_inner = re.search(r'>(.*)</', new_html, re.DOTALL)
            
            if old_inner and new_inner:
                old_content = old_inner.group(1).strip()
                new_content = new_inner.group(1).strip()
                
                if old_content != new_content:
                    # Extract nested helix elements
                    old_nested_tags = re.findall(r'<(helix-[^>\s]+)', old_content)
                    new_nested_tags = re.findall(r'<(helix-[^>\s]+)', new_content)
                    
                    # Extract non-helix nested elements
                    old_other_tags = re.findall(r'<([^>helix][^>\s]*)', old_content)
                    new_other_tags = re.findall(r'<([^>helix][^>\s]*)', new_content)
                    
                    if old_nested_tags != new_nested_tags or old_other_tags != new_other_tags:
                        nested_changes = {
                            'old_nested': old_nested_tags,
                            'new_nested': new_nested_tags,
                            'old_other': old_other_tags,
                            'new_other': new_other_tags
                        }
            
            # Store transformation rule
            if old_tag not in transformation_rules:
                transformation_rules[old_tag] = {
                    'new_tag': new_tag,
                    'added_attrs': added_attrs,
                    'removed_attrs': list(removed_attrs),
                    'modified_attrs': modified_attrs,
                    'preserved_attrs': preserved_attrs,
                    'nested_changes': nested_changes,
                    'examples': []
                }
            
            # Add example
            transformation_rules[old_tag]['examples'].append({
                'old': old_html[:100] + '...' if len(old_html) > 100 else old_html,
                'new': new_html[:100] + '...' if len(new_html) > 100 else new_html
            })
            
        except Exception as e:
            print(f"Error analyzing transformation for {old_tag if 'old_tag' in locals() else 'unknown'}: {e}")
            continue
    
    return transformation_rules

def create_migration_prompt(original_content, mapping_dict):
    """
    Creates a dynamic, detailed prompt for the LLM to perform content migration.
    
    Args:
        original_content (str): The text content to be migrated.
        mapping_dict (dict): A dictionary from the CSV where keys are old
                             patterns and values are new patterns.
    
    Returns:
        str: The full prompt for the LLM.
    """
    
    # Dynamically analyze transformation patterns
    transformation_rules = analyze_transformation_patterns(mapping_dict)
    
    instructions = (
        "You are an expert Helix component migration tool. Transform V1 Helix components to V2 format with precise attribute handling.\n"
        "\n"
        "CRITICAL OUTPUT INSTRUCTIONS:\n"
        "- Return ONLY the migrated HTML content\n"
        "- Do NOT include explanatory text, comments, or phrases like 'Here is the updated content'\n"
        "- Output must be valid, well-formed HTML\n"
        "- Preserve exact spacing and formatting where possible\n"
        "\n"
        "DYNAMIC TRANSFORMATION RULES:\n"
    )
    
    # Generate dynamic transformation rules
    for old_tag, rule_data in transformation_rules.items():
        new_tag = rule_data['new_tag']
        instructions += f"\n=== {old_tag} → {new_tag} ===\n"
        instructions += f"- Transform tag name: '{old_tag}' to '{new_tag}'\n"
        
        # Added attributes
        if rule_data['added_attrs']:
            attr_list = [f'{k}="{v}"' for k, v in rule_data['added_attrs'].items()]
            instructions += f"- ADD attributes: {', '.join(attr_list)}\n"
        
        # Removed attributes  
        if rule_data['removed_attrs']:
            instructions += f"- REMOVE attributes: {', '.join(rule_data['removed_attrs'])}\n"
        
        # Modified attributes
        if rule_data['modified_attrs']:
            modifications = [f'{k}: "{v["old"]}" → "{v["new"]}"' for k, v in rule_data['modified_attrs'].items()]
            instructions += f"- MODIFY attributes: {', '.join(modifications)}\n"
        
        # Preserved attributes
        if rule_data['preserved_attrs']:
            preserved_count = len(rule_data['preserved_attrs'])
            instructions += f"- PRESERVE {preserved_count} existing attributes (keep values unchanged)\n"
        
        # Nested content changes
        if rule_data['nested_changes']:
            changes = rule_data['nested_changes']
            if changes.get('old_nested') != changes.get('new_nested'):
                instructions += f"- Transform nested helix elements: {changes.get('old_nested', [])} → {changes.get('new_nested', [])}\n"
            if changes.get('old_other') != changes.get('new_other'):
                instructions += f"- Transform nested elements: {changes.get('old_other', [])} → {changes.get('new_other', [])}\n"
    
    # Append detailed migration rules from the mapping dictionary
    for old, new in mapping_dict.items():
        instructions += f"- Update `{old}` to `{new}`.\n"
    # Universal attribute handling rules
    instructions += (
        "\n"
        "UNIVERSAL ATTRIBUTE RULES:\n"
        #"- data-hwc-version: Update to '4.0.883' for all V2 components\n"
        "- id attributes: Preserve exactly as they are\n"
        "- src, href, alt, title attributes: Preserve values unchanged\n"
        "- Custom data-* attributes: Preserve unless explicitly removed\n"
        "\n"
        "STRUCTURAL PRESERVATION:\n"
        "- Maintain original nesting and hierarchy\n"
        "- Keep all content inside proper parent containers\n"
        "- Preserve order of elements and attributes where possible\n"
        "\n"
        "FALLBACK RULES:\n"
        "- If no specific rule exists for a helix-* component, apply general transformation:\n"
        #"  * helix-component → helix-core-component\n"
        #"  * Update data-hwc-version to '4.0.883'\n"
        "  * Preserve all other attributes\n"
        "\n"
        "CONTENT TO MIGRATE:\n"
    )
    
    prompt = f"{instructions}{original_content}\n\nMIGRATED OUTPUT:"
    
    return prompt



def clean_migration_response(response):
    """Clean up the Ollama response to remove any unwanted commentary."""
    if not response:
        return response
    
    # Remove common unwanted prefixes
    unwanted_prefixes = [
        "Here is the updated content:",
        "Here is the migrated content:",
        "Here's the updated content:",
        "Here's the migrated content:",
        "The migrated content is:",
        "Updated content:",
        "Migrated content:",
        "Here is the result:",
        "The result is:",
        "Output:",
        "Here you go:",
        "Here's what you need:",
    ]
    
    cleaned = response.strip()
    
    for prefix in unwanted_prefixes:
        if cleaned.lower().startswith(prefix.lower()):
            cleaned = cleaned[len(prefix):].strip()
            break
    
    # Remove any leading/trailing whitespace and newlines
    cleaned = cleaned.strip()
    
    # If the response starts with explanatory text followed by HTML, try to extract just the HTML
    if cleaned and not cleaned.startswith('<'):
        lines = cleaned.split('\n')
        html_start_found = False
        html_lines = []
        
        for line in lines:
            line_stripped = line.strip()
            if line_stripped.startswith('<'):
                html_start_found = True
                html_lines.append(line)
            elif html_start_found:
                html_lines.append(line)
        
        if html_lines:
            cleaned = '\n'.join(html_lines)
    
    return cleaned

def call_ollama(prompt, model="llama3:latest"):
    """Sends a prompt to the Ollama API and returns the generated content."""
    url = "http://localhost:11434/api/generate"
    
    # Get model from environment variable or use the provided default
    llm_model = os.getenv('LLM_MODEL', model)
    if not llm_model:
        llm_model = "llama3:latest"  # Ultimate fallback with proper tag
    
    payload = {
        "model": llm_model,
        "prompt": prompt,
        "stream": False,  # Ensure we wait for complete response
        "system": "You are a precise HTML migration tool. Return ONLY the migrated HTML content. Do NOT include any explanatory text, commentary, or phrases like 'Here is the updated content'. Output only the exact migrated HTML.",
        "options": {
            "temperature": 0,  # Make responses deterministic
            "top_p": 1,
            "repeat_penalty": 1,
        },
    }

    # print(f"DEBUG: Using model '{llm_model}' for Ollama API call")
    # print("Payload being sent to Ollama API:", json.dumps(payload, indent=2))
    
    try:
        response = requests.post(url, json=payload, timeout=120)
        response.raise_for_status()
        
        # Handle potential streaming or multiple JSON responses
        response_text = response.text.strip()
        # print("response_text")
        # print(response_text)

        # print(f"Raw Ollama response: {response_text[:200]}...")  # Debug log
        
        # Try to parse as single JSON first
        try:
            data = json.loads(response_text)
            if "response" in data:
                # print(f"Successfully parsed single JSON response")
                migrated_content = data["response"].strip()
                
                # Clean up any unwanted prefixes or commentary
                migrated_content = clean_migration_response(migrated_content)
                return migrated_content
            else:
                print(f"Unexpected response format: {data}")
                return None
                
        except json.JSONDecodeError as e:
            # Handle multiple JSON objects (streaming response)
            # print(f"Single JSON parsing failed: {e}, trying multi-line parsing")
            lines = response_text.strip().split('\n')
            final_response = ""
            
            for line in lines:
                if line.strip():
                    try:
                        line_data = json.loads(line)
                        if "response" in line_data:
                            final_response += line_data["response"]
                        if line_data.get("done", False):
                            break
                    except json.JSONDecodeError as line_e:
                        print(f"Error parsing line: {line}, error: {line_e}")
                        continue
            
            if final_response:
                print(f"Successfully parsed multi-line response, length: {len(final_response)}")
                migrated_content = final_response.strip()
                
                # Clean up any unwanted prefixes or commentary
                migrated_content = clean_migration_response(migrated_content)
                return migrated_content
            else:
                print("Could not extract response from multi-line JSON")
                return None
            
    except requests.exceptions.Timeout:
        print("Ollama API request timed out")
        return None
    except requests.exceptions.ConnectionError:
        print("Could not connect to Ollama API - make sure it's running with 'ollama serve'")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error calling Ollama API: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error in call_ollama: {e}")
        return None

def call_ollama1(prompt, model="llama3"):
    """Sends a prompt to the Ollama API and returns the generated content."""
    url = "http://localhost:11434/api/generate"
    
    # Get model from environment variable or use the provided default
    llm_model = os.getenv('LLM_MODEL', model)
    if not llm_model:
        llm_model = "llama3"  # Ultimate fallback
    
    payload = {
        "model": llm_model,
        "prompt": prompt,
        "stream": False,  # Wait for the full response
        "options": {
            "temperature": 0
        }
    }
    
    try:
        # print(f"Calling Ollama API with model: {model}")
        response = requests.post(url, json=payload, timeout=120)
        response.raise_for_status()
        
        # Handle potential streaming or multiple JSON responses
        response_text = response.text.strip()
        
        # Try to parse as single JSON first
        try:
            data = json.loads(response_text)
            if "response" in data:
                return data["response"]
            else:
                print(f"Unexpected response format: {data}")
                return None
                
        except json.JSONDecodeError:
            # Handle multiple JSON objects (streaming response)
            print("Handling multi-line JSON response")
            lines = response_text.strip().split('\n')
            final_response = ""
            
            for line in lines:
                if line.strip():
                    try:
                        line_data = json.loads(line)
                        if "response" in line_data:
                            final_response += line_data["response"]
                        if line_data.get("done", False):
                            break
                    except json.JSONDecodeError as e:
                        print(f"Error parsing line: {line}, error: {e}")
                        continue
            
            return final_response if final_response else None
            
    except requests.exceptions.Timeout:
        print("Ollama API request timed out")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error calling Ollama API: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error in call_ollama: {e}")
        return None
    

