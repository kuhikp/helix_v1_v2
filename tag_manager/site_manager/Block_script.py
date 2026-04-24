import os
import hashlib
from collections import defaultdict, Counter
from bs4 import BeautifulSoup
from tqdm import tqdm

ROOT_DIR = "/Users/sbws_user/Downloads/HTMLtracker/migration/public/reorg/proconnect.pfizerpro.com.br"      # change this
OUTPUT_DIR = "/Users/sbws_user/Downloads/HTMLtracker/Common_blocks_proconnect.pfizerpro.com.br/"  #location where your html files will be stored
MIN_OCCURRENCE_RATIO = 0.6       # appears in at least 60% of pages

os.makedirs(OUTPUT_DIR, exist_ok=True)

def get_html_files(root):
    html_files = []
    for path, _, files in os.walk(root):
        for f in files:
            if f.lower().endswith(".html"):
                html_files.append(os.path.join(path, f))
    return html_files

def normalize_tag(tag):
    """
    Convert a BeautifulSoup tag into a stable structural signature
    """
    if not tag.name:
        return None

    attrs = sorted(tag.attrs.keys())
    children = [child.name for child in tag.find_all(recursive=False) if child.name]

    signature = f"{tag.name}|{'-'.join(attrs)}|{'-'.join(children)}"
    return signature

def hash_block(tag):
    signature = normalize_tag(tag)
    if not signature:
        return None
    return hashlib.md5(signature.encode()).hexdigest()

def extract_blocks(soup):
    """
    Extract likely reusable blocks
    """
    blocks = []

    # Priority semantic elements
    selectors = ["header", "footer", "nav", "aside"]

    for sel in selectors:
        for tag in soup.select(sel):
            blocks.append(tag)

    # Large structural divs
    for div in soup.find_all("div", recursive=True):
        if len(div.find_all(recursive=False)) >= 3:
            blocks.append(div)

    return blocks

html_files = get_html_files(ROOT_DIR)
total_pages = len(html_files)

block_map = defaultdict(list)

print(f"Scanning {total_pages} HTML files...")

for file in tqdm(html_files):
    with open(file, encoding="utf-8", errors="ignore") as f:
        soup = BeautifulSoup(f, "lxml")

    blocks = extract_blocks(soup)

    for block in blocks:
        block_hash = hash_block(block)
        if block_hash:
            block_map[block_hash].append(block)

print("Analyzing common blocks...")

common_blocks = {
    h: blocks for h, blocks in block_map.items()
    if len(blocks) / total_pages >= MIN_OCCURRENCE_RATIO
}

print(f"Found {len(common_blocks)} common blocks")

def save_block_example(block, index):
    filename = f"block_{index}.html"
    path = os.path.join(OUTPUT_DIR, filename)

    with open(path, "w", encoding="utf-8") as f:
        f.write(str(block))

for idx, blocks in enumerate(common_blocks.values(), start=1):
    save_block_example(blocks[0], idx)

print(f"Saved reusable blocks to '{OUTPUT_DIR}'")
