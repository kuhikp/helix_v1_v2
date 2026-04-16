import json
import uuid

def write_blocks_as_json(blocks, output_dir):
    os.makedirs(output_dir, exist_ok=True)

    for i, block in enumerate(blocks, start=1):
        block_id = str(uuid.uuid4())

        block_json = {
            "storage": {
                "data": {
                    "html": str(block),
                    "css": ""
                }
            },
            "settings": {
                "title": f"Auto Common Block {i}",
                "category": "Auto-Extracted",
                "protected": False,
                "settings": {
                    "description": "Generated from HTTracked site",
                    "auto_attach": False
                }
            }
        }

        file_path = os.path.join(output_dir, f"common_block_{i}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(block_json, f, indent=2)