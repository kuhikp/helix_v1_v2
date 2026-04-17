#!/usr/bin/env python3
"""Extract CSS/JS references from HTML pages and export them to CSV.

Columns:
1. Page Name
2. CSS/JS File Name
3. CSS/JS File Attributes
4. Attachment Location
5. Internal/External
"""

from __future__ import annotations

import argparse
import csv
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import unquote, urlparse


CSV_HEADERS = [
    "Page Name",
    "CSS/JS File Name",
    "CSS/JS File Attributes",
    "Attachment Location",
    "Internal/External",
    "Type",
]


class AssetExtractor(HTMLParser):
    """Parse HTML and collect CSS/JS asset references with metadata."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.records: List[Tuple[str, str, str, str, str]] = []
        self.stack: List[Tuple[str, Dict[str, str]]] = []
        self.current_section: str = "Header"  # Track if we're in Header or Footer

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, str | None]]) -> None:
        tag_lower = tag.lower()
        if tag_lower == "body":
            self.current_section = "Footer"
        attrs_dict = self._attrs_to_dict(attrs)
        self._capture_asset(tag_lower, attrs_dict)
        self.stack.append((tag_lower, attrs_dict))

    def handle_startendtag(self, tag: str, attrs: List[Tuple[str, str | None]]) -> None:
        attrs_dict = self._attrs_to_dict(attrs)
        self._capture_asset(tag.lower(), attrs_dict)

    def handle_endtag(self, tag: str) -> None:
        target = tag.lower()
        if target == "body":
            self.current_section = "Header"
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == target:
                del self.stack[i]
                break

    def _capture_asset(self, tag: str, attrs: Dict[str, str]) -> None:
        url = ""
        if tag == "script" and attrs.get("src"):
            url = attrs["src"].strip()
        elif tag == "link" and attrs.get("href") and self._is_css_link(attrs):
            url = attrs["href"].strip()

        if not url:
            return

        is_external = self._is_external(url)
        file_name = url if is_external else self._extract_file_name(url)
        attr_text = self._format_attributes(attrs)
        location = self._attachment_location()
        origin = "External" if is_external else "Internal"
        asset_type = self._determine_asset_type(url, tag)

        self.records.append((file_name, attr_text, location, origin, asset_type))

    def _attachment_location(self) -> str:
        return self.current_section

    @staticmethod
    def _determine_asset_type(url: str, tag: str) -> str:
        """Determine asset type based on URL and tag."""
        url_lower = url.lower()
        if tag == "script" or url_lower.endswith(".js"):
            return "JS"
        elif ".css" in url_lower:
            return "CSS"
        elif any(ext in url_lower for ext in [".woff", ".woff2", ".ttf", ".otf", ".eot"]):
            return "Font"
        elif any(ext in url_lower for ext in [".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"]):
            return "Image"
        else:
            return "Other"

    @staticmethod
    def _is_css_link(attrs: Dict[str, str]) -> bool:
        href = attrs.get("href", "").lower()
        rel = attrs.get("rel", "").lower()
        return "stylesheet" in rel or ".css" in href

    @staticmethod
    def _is_external(url: str) -> bool:
        parsed = urlparse(url)
        return bool(parsed.scheme or parsed.netloc) or url.startswith("//")

    @staticmethod
    def _extract_file_name(url: str) -> str:
        path = urlparse(url).path
        if not path:
            return url
        name = Path(path).name
        return unquote(name) if name else url

    @staticmethod
    def _format_attributes(attrs: Dict[str, str]) -> str:
        allowed_attrs = {"default", "async", "defer", "hybrid", "preload"}
        result = []
        for attr in allowed_attrs:
            if attr in attrs:
                value = attrs[attr]
                if value:
                    result.append(f'{attr}="{value}"')
                else:
                    result.append(attr)
        return "; ".join(result) if result else ""

    @staticmethod
    def _attrs_to_dict(attrs: List[Tuple[str, str | None]]) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for key, value in attrs:
            out[key.lower()] = value if value is not None else ""
        return out


def page_name_for(html_path: Path, root_dir: Path) -> str:
    rel_path = html_path.relative_to(root_dir)
    if html_path.name.lower() == "index.html":
        if rel_path == Path("index.html"):
            return "Homepage"
        return unquote(html_path.parent.name)
    return unquote(html_path.stem)


def iter_html_files(root_dir: Path) -> List[Path]:
    return sorted(
        [p for p in root_dir.rglob("*.html") if p.is_file()],
        key=lambda p: str(p.relative_to(root_dir)).lower(),
    )


def extract_rows(root_dir: Path) -> List[List[str]]:
    rows: List[List[str]] = []
    for html_file in iter_html_files(root_dir):
        parser = AssetExtractor()
        try:
            html_text = html_file.read_text(encoding="utf-8", errors="ignore")
            parser.feed(html_text)
            parser.close()
        except Exception:
            # Skip malformed or unreadable files and continue scanning.
            continue

        name = page_name_for(html_file, root_dir)
        for file_name, attr_text, location, origin, asset_type in parser.records:
            rows.append([name, file_name, attr_text, location, origin, asset_type])
    return rows


def write_csv(csv_path: Path, rows: List[List[str]]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADERS)
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract CSS/JS file references from all HTML files into a CSV report."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Root folder to scan recursively for HTML files (default: current folder).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("assets_report.csv"),
        help="Output CSV file path (default: assets_report.csv).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root_dir = args.root.resolve()
    output_path = args.output.resolve()

    rows = extract_rows(root_dir)
    write_csv(output_path, rows)

    print(f"Scanned HTML files under: {root_dir}")
    print(f"Rows written: {len(rows)}")
    print(f"CSV created: {output_path}")


if __name__ == "__main__":
    main()
