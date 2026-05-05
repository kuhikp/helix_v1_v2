import os
import json
import hashlib
from collections import defaultdict
from bs4 import BeautifulSoup
from tqdm import tqdm

# ==================================================
# CONFIGURATION
# ==================================================

ROOT_DIR = "/Users/sbws_user/Downloads/HTMLtracker/migration/public/www.pactonco.fr" #HTTracked site folder in your local
OUTPUT_DIR = "/Users/sbws_user/Downloads/HTMLtracker/Common_blocks_www.pactonco.fr/" #location where common blocks will be saved in your local
UNCOMMON_OUTPUT_DIR = "/Users/sbws_user/Downloads/HTMLtracker/Uncommon_blocks_www.pactonco.fr/" #location where uncommon blocks will be saved in your local
MIN_OCCURRENCE_RATIO = 0.6  # 60%

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(UNCOMMON_OUTPUT_DIR, exist_ok=True)

# ==================================================
# FILE DISCOVERY
# ==================================================

def get_html_files(root):
    html_files = []
    for path, _, files in os.walk(root):
        for f in files:
            if f.lower().endswith(".html"):
                html_files.append(os.path.join(path, f))
    return html_files

# ==================================================
# BLOCK NORMALIZATION & HASHING
# ==================================================

def normalize_tag(tag):
    if not tag.name:
        return None

    attrs = sorted(tag.attrs.keys())
    children = [c.name for c in tag.find_all(recursive=False) if c.name]

    depth = len(list(tag.parents))
    text_len = len(tag.get_text(strip=True))
    text_bucket = text_len // 100

    return (
        f"{tag.name}|"
        f"{'-'.join(attrs)}|"
        f"{'-'.join(children)}|"
        f"d={depth}|"
        f"t={text_bucket}"
    )

def hash_block(tag):
    sig = normalize_tag(tag)
    if not sig:
        return None
    return hashlib.md5(sig.encode()).hexdigest()

def block_unique_name(block_hash, tag):
    return f"{tag.name}_block_{block_hash[:8]}"

def parent_fingerprint(tag):
    if not tag.parent or not tag.parent.name:
        return None
    return hashlib.md5(tag.parent.name.encode()).hexdigest()

# ==================================================
# BLOCK EXTRACTION
# ==================================================

def extract_blocks(soup):
    blocks = []
    selected = set()

    semantic_tags = ["header", "footer", "nav", "aside", "main"]

    for tag in semantic_tags:
        for el in soup.select(tag):
            blocks.append(el)
            selected.add(el)

    for div in soup.find_all("div", recursive=True):
        if len(div.find_all(recursive=False)) >= 3:
            if any(parent in selected for parent in div.parents):
                continue
            blocks.append(div)
            selected.add(div)

    return blocks

# ==================================================
# MAIN SCAN
# ==================================================

html_files = get_html_files(ROOT_DIR)
total_pages = len(html_files)

print(f"Scanning {total_pages} HTML files...")

block_map = defaultdict(lambda: {
    "blocks": [],
    "files": set(),
    "name": None
})

file_block_reference = defaultdict(list)

for file in tqdm(html_files):
    with open(file, encoding="utf-8", errors="ignore") as f:
        soup = BeautifulSoup(f, "lxml")

    blocks = extract_blocks(soup)

    seen_in_file = set()
    seen_child_per_parent = set()

    for block in blocks:
        block_hash = hash_block(block)
        if not block_hash:
            continue

        parent_fp = parent_fingerprint(block)
        child_key = (block_hash, parent_fp)

        # ✅ Do not repeat child blocks in same parent
        if child_key in seen_child_per_parent:
            continue

        seen_child_per_parent.add(child_key)

        if block_hash in seen_in_file:
            continue

        seen_in_file.add(block_hash)

        entry = block_map[block_hash]
        entry["blocks"].append(block)
        entry["files"].add(file)
        entry["name"] = block_unique_name(block_hash, block)

        file_block_reference[file].append(entry["name"])

# ==================================================
# COMMON / UNCOMMON CLASSIFICATION
# ==================================================

common_blocks = {}
uncommon_blocks = {}
unique_blocks = {}

for h, data in block_map.items():
    ratio = len(data["files"]) / total_pages

    if ratio >= MIN_OCCURRENCE_RATIO:
        common_blocks[h] = data
    elif ratio > 1 / total_pages:
        uncommon_blocks[h] = data
    else:
        unique_blocks[h] = data

# ==================================================
# NESTED BLOCK PRUNING
# ==================================================

def prune_nested(block_dict):
    pruned = {}

    items = list(block_dict.items())
    for h, data in items:
        candidate = str(data["blocks"][0])
        nested = False

        for oh, other in items:
            if h == oh:
                continue
            if candidate in str(other["blocks"][0]):
                nested = True
                break

        if not nested:
            pruned[h] = data

    return pruned

common_blocks = prune_nested(common_blocks)
uncommon_blocks = prune_nested(uncommon_blocks)

print(f"✅ Common blocks found: {len(common_blocks)}")

# ==================================================
# SAVE OUTPUTS
# ==================================================

def save_blocks(blocks, out_dir):
    registry = {}

    for h, data in blocks.items():
        name = data["name"]
        block = data["blocks"][0]

        with open(os.path.join(out_dir, f"{name}.html"), "w", encoding="utf-8") as f:
            f.write(str(block))

        registry[name] = {
            "hash": h,
            "used_in": list(data["files"])
        }

    return registry

common_registry = save_blocks(common_blocks, OUTPUT_DIR)
uncommon_registry = save_blocks(uncommon_blocks, UNCOMMON_OUTPUT_DIR)

with open(os.path.join(OUTPUT_DIR, "block_registry.json"), "w") as f:
    json.dump(common_registry, f, indent=2)

with open(os.path.join(OUTPUT_DIR, "file_block_map.json"), "w") as f:
    json.dump(file_block_reference, f, indent=2)

print("✅ Reusable blocks saved")
print("✅ Block registry created")
print("✅ File → block reference map generated")