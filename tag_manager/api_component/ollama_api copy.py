import requests
import json

def create_migration_prompt(original_content, mapping_dict):
    """
    Creates a detailed prompt for the LLM to perform content migration.
    
    Args:
        original_content (str): The text content to be migrated.
        mapping_dict (dict): A dictionary from the CSV where keys are old
                             patterns and values are new patterns.
    
    Returns:
        str: The full prompt for the LLM.
    """

    # instructions = (
    #     "You are an intelligent content migration assistant. "
    #     "Your task is to take a block of content and migrate any occurrences "
    #     "of old HTML structures to new structures based on a set of rules. "
    #     "Ensure that the content inside any attributes is preserved and moved "
    #     "to the correct location in the new structure.\n\n"
    #     "Here are the migration rules based on the old and new templates:\n"
    # )
    
    # for old, new in mapping_dict.items():
    #     instructions += f"- Replace `{old}` with `{new}`.\n"

    instructions = (
        "You are an intelligent content migration assistant. "
        "Your task is to analyze the structure of the 'helix' element in the content "
        "and update it to match the new structure based on the provided rules. "
        "If an attribute from the v1 'helix' element does not exist in the compatible "
        "v2 'helix' element structure, assign it appropriately to ensure no data is lost. "
        "Ensure that all attributes and nested elements are preserved and correctly "
        "reorganized according to the new structure. Additionally, remove any duplicate "
        "'helix' tags or redundant content while ensuring the integrity of the data.\n\n"
        "Here are the migration rules for updating the 'helix' element structure:\n"
    )

    instructions = (
        "You are an intelligent content migration assistant. Your task is to analyze the structure of the 'helix' elements in the content and update them to match the new structure based on the provided rules."
        "Key requirements for migration:" 
        "- Maintain the original nesting and hierarchy of elements. For example, if a `<helix-image>` tag appears inside a `<helix-accordion-panel>`, its migrated `<helix-core-image>` counterpart must appear inside the corresponding `<helix-core-accordion-panel>` in the output."
        "- Migrate all attributes and nested elements according to the provided rules. If an attribute from the v1 element does not exist in the v2 structure, assign it appropriately to ensure no data is lost."
        "- Remove any duplicate or redundant tags while ensuring the integrity of the data."
        "- Do not place migrated elements outside of their original parent containers. Preserve the internal structure of panels, accordions, and other composite elements."
        "- Your response should contain only the migrated content, with no additional commentary or text. If no migration is needed, return the original content unchanged."
        "Migration rules for updating the 'helix' element structure:"
    )

    instructions = (
        "You are an intelligent content migration assistant. Your task is to analyze and migrate all elements with tags starting with `helix-` in the provided content according to the following rules."
        "Key requirements for migration:"
        "- Maintain the original nesting and hierarchy of elements. Migrated tags must remain in their original parent containers and order."
        "- Detect and migrate every tag that starts with `helix-`, including but not limited to `helix-image`, `helix-accordion`, `helix-anchor`, etc."
        "- For each `helix-*` tag, use the appropriate migration rule. If a direct mapping to a `helix-core-*` or other new structure is provided, apply it. If no explicit rule exists, perform a best-effort transformation that preserves all attributes and content, and adapts the tag name to the new convention (e.g., `helix-anchor` → `helix-core-anchor`)."
        "- Migrate all attributes and nested elements according to the rules. If an attribute from the v1 element does not exist in the v2 structure, assign it appropriately to ensure no data is lost."
        "- Remove any duplicate or redundant tags while ensuring the integrity of the data."
        "- Ensure every migrated tag in the output is properly closed, regardless of its type."
        "- Your response should contain only the migrated content, with no additional commentary or text. If no migration is needed for a tag, leave it unchanged."
        "Migration rules for updating the 'helix' element structure:"
    )

    # Append detailed migration rules from the mapping dictionary
    for old, new in mapping_dict.items():
        instructions += f"- Update `{old}` to `{new}`.\n"
    prompt = (
        f"{instructions}\n"
        "Your response should contain only the migrated content, with no additional commentary or text. "
        "If no migration is needed, return the original content unchanged.\n\n"
        "---CONTENT TO MIGRATE---\n"
        f"{original_content}\n"
        "---END OF CONTENT---"
    )
    # print("ORIGINAL CONTENT:")
    # print(original_content)

    # print("\n\n PROMPT IS:\n\n")
    # print(prompt)
    # print("--------------------------------------------------")
    return prompt


def call_ollama(prompt, model="llama3"):
    """Sends a prompt to the Ollama API and returns the generated content."""
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": os.getenv('LLM_MODEL'),
        "prompt": prompt,
        "stream": False,  # Wait for the full response
        "options": {
            "temperature": 0
        }
    }
    
    try:
        print(f"Calling Ollama API with model: {model}")
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
    

