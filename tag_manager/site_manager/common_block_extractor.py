# common_block_extractor.py
import os
import hashlib
from bs4 import BeautifulSoup
from collections import defaultdict

MIN_OCCURRENCE_RATIO = 0.6

def get_html_files(root):
    return [
        os.path.join(path, f)
        for path, _, files in os.walk(root)
        for f in files if f.lower().endswith(".html")
    ]

def normalize_block(tag):
    attrs = ",".join(sorted(tag.attrs.keys()))
    children = ",".join(
        child.name for child in tag.find_all(recursive=False) if child.name
    )
    text = " ".join(tag.stripped_strings)[:200]
    signature = f"{tag.name}|{attrs}|{children}|{text}"
    return hashlib.md5(signature.encode("utf-8")).hexdigest()

def extract_blocks(soup):
    blocks = []

    for sel in ["header", "footer", "nav", "aside"]:
        blocks.extend(soup.select(sel))

    for div in soup.find_all("div", recursive=True):
        if len(div.find_all(recursive=False)) >= 3:
            blocks.append(div)

    return blocks

def extract_common_blocks(html_root):
    html_files = get_html_files(html_root)
    total_pages = len(html_files)

    block_pages = defaultdict(set)
    block_examples = {}

    for file in html_files:
        with open(file, encoding="utf-8", errors="ignore") as f:
            soup = BeautifulSoup(f, "lxml")

        seen = set()
        for block in extract_blocks(soup):
            h = normalize_block(block)
            if h not in seen:
                block_pages[h].add(file)
                block_examples.setdefault(h, block)
                seen.add(h)

    common_blocks = [
        block_examples[h]
        for h, pages in block_pages.items()
        if len(pages) / total_pages >= MIN_OCCURRENCE_RATIO
    ]
    return common_blocks
