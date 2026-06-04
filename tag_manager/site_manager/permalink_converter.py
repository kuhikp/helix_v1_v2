"""
Permalink Converter Module

This module handles the conversion of image permalinks from v1 to v2 format.
It processes pages JSON files, extracts image URLs, maps old UUIDs to new ones,
and updates the HTML with new site IDs and UUIDs.
"""

import json
import os
import re
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)


def _normalize_filename(filename: str) -> str:
    """Normalize filenames so v1/v2 comparisons are resilient to path and case differences."""
    return Path(str(filename).strip()).name.lower()


def _is_direct_image_reference(value: str) -> bool:
    """Return True when the value looks like a direct image filename/path instead of a URL."""
    candidate = str(value).strip()
    if not candidate or '://' in candidate or candidate.startswith('data:'):
        return False

    return bool(re.search(r'\.(png|jpe?g|webp|gif|svg)(\?.*)?$', candidate, flags=re.IGNORECASE))


class PermalinkConverter:
    """
    Converts image permalinks from v1 to v2 format in page JSON files.
    
    Workflow:
    1. Read pages JSON files from the data/pages directory
    2. Extract image src attributes from HTML section
    3. Match permalink pattern: https://webbuilder.pfizer/webbuilder/asset-proxy/{siteid}/{uuid}
    4. Find corresponding file in data/files directory
    5. Map old UUID to new UUID from data/files_v2 directory
    6. Update siteid from environment variable V2_SITE_ID
    7. Replace old permalink with new one in HTML
    8. Save updated JSON back to file
    """
    
    # Regex pattern for matching permalinks on both supported hosts.
    PERMALINK_PATTERN = (
        r'https://(?P<host>canvas\.pfizer\.com|webbuilder\.pfizer)'
        r'/webbuilder/asset-proxy/(?P<site_id>\d+)/(?P<asset>[a-f0-9\-]+)'
    )
    IMAGE_ATTRIBUTE_PATTERN = re.compile(
        r'(?P<attribute>src|img-src|img-retina|mobile-img-src|mobile-img-retina)='
        r'(?P<quote>["\'])'
        r'(?P<value>[^"\']+)'
        r'(?P=quote)',
        flags=re.IGNORECASE
    )
    
    def __init__(
        self,
        pages_dir: str,
        files_dir: str,
        files_v2_dir: str,
        v1_site_id: str,
        v2_site_id: str,
        progress_callback=None
    ):
        """
        Initialize the converter.
        
        Args:
            pages_dir: Path to directory containing page JSON files
            files_dir: Path to directory containing v1 files ({uuid}.json)
            files_v2_dir: Path to directory containing v2 files ({uuid}.json)
            v1_site_id: Original site ID (for validation/logging)
            v2_site_id: New site ID to use in converted permalinks
            progress_callback: Optional callback function for progress tracking
        """
        self.pages_dir = Path(pages_dir)
        self.files_dir = Path(files_dir)
        self.files_v2_dir = Path(files_v2_dir)
        self.v1_site_id = v1_site_id
        self.v2_site_id = v2_site_id
        self.progress_callback = progress_callback
        
        # UUID and filename caches (built on demand and persisted to disk)
        self._uuid_mapping_cache: Dict[str, str] = {}
        self._v1_uuid_to_filename_cache: Dict[str, str] = {}
        self._v2_filename_to_uuid_cache: Dict[str, str] = {}
        self.cache_dir = self.files_dir.parent
        self.v1_metadata_file = self.cache_dir / 'file_v1.json'
        self.v2_metadata_file = self.cache_dir / 'file_v2.json'
        
        # Progress tracking
        self.total_pages = 0
        self.processed_pages = 0
        
    def _emit_progress(self, message: str, processed: int = None, total: int = None):
        """
        Emit progress update via callback if provided.
        
        Args:
            message: Progress message
            processed: Number of processed pages
            total: Total number of pages
        """
        if self.progress_callback:
            progress_data = {
                'message': message,
                'processed': processed or self.processed_pages,
                'total': total or self.total_pages,
                'percentage': int((self.processed_pages / max(self.total_pages, 1)) * 100)
            }
            try:
                self.progress_callback(progress_data)
            except Exception as e:
                logger.warning(f"Error in progress callback: {str(e)}")
    
    def _validate_directories(self) -> Tuple[bool, str]:
        """
        Validate that required directories exist.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not self.pages_dir.exists():
            return False, f"Pages directory does not exist: {self.pages_dir}"
        
        if not self.files_dir.exists():
            return False, f"Files directory does not exist: {self.files_dir}"
        
        if not self.files_v2_dir.exists():
            return False, f"Files v2 directory does not exist: {self.files_v2_dir}"
        
        return True, ""

    def _load_metadata_index(self, metadata_file: Path) -> Dict[str, Dict[str, object]]:
        """Load a UUID-keyed metadata index if it exists and is valid."""
        if not metadata_file.exists():
            return {}

        try:
            with open(metadata_file, 'r', encoding='utf-8') as file_handle:
                cached_data = json.load(file_handle)
        except Exception as exc:
            logger.warning(f"Could not load metadata index {metadata_file}: {exc}")
            return {}

        if not isinstance(cached_data, dict):
            return {}

        return {
            str(key): value
            for key, value in cached_data.items()
            if key and isinstance(value, dict)
        }

    def _save_metadata_index(self, metadata_file: Path, metadata_index: Dict[str, Dict[str, object]]) -> None:
        """Persist a UUID-keyed metadata index to disk for reuse in later runs."""
        try:
            with open(metadata_file, 'w', encoding='utf-8') as file_handle:
                json.dump(metadata_index, file_handle, ensure_ascii=True, indent=2, sort_keys=True)
        except Exception as exc:
            logger.warning(f"Could not save metadata index {metadata_file}: {exc}")

    def _read_file_metadata(self, file_path: Path) -> Tuple[Optional[str], Optional[Dict[str, object]]]:
        """Read essential metadata from a file metadata JSON document."""
        try:
            with open(file_path, 'r', encoding='utf-8') as file_handle:
                file_data = json.load(file_handle)
        except Exception as exc:
            logger.warning(f"Could not read file metadata {file_path.name}: {exc}")
            return None, None

        details = file_data.get('details', {}) if isinstance(file_data, dict) else {}
        uuid_value = details.get('uuid') or file_path.stem.replace('processed_', '')
        filename_value = details.get('filename')

        if not uuid_value or not filename_value:
            return None, None

        metadata = {
            'uuid': str(uuid_value),
            'filename': str(filename_value),
            'normalized_filename': _normalize_filename(str(filename_value)),
            'filetype': details.get('filetype'),
            'filepath': details.get('filepath'),
            'filesize': details.get('filesize'),
            'hash': details.get('hash') or file_data.get('hash'),
            'created_at': details.get('created_at'),
            'updated_at': details.get('updated_at'),
            'deleted_at': details.get('deleted_at'),
            'url': details.get('url'),
            'source_json': file_path.name,
        }

        return str(uuid_value), metadata

    def _build_metadata_index(self, source_dir: Path, metadata_file: Path, label: str) -> Dict[str, Dict[str, object]]:
        """Build and persist a UUID-keyed metadata index from a source directory."""
        cached_index = self._load_metadata_index(metadata_file)
        if cached_index:
            return cached_index

        metadata_index: Dict[str, Dict[str, object]] = {}

        for file_path in source_dir.glob('*.json'):
            uuid_value, metadata = self._read_file_metadata(file_path)
            if uuid_value and metadata:
                metadata_index[uuid_value] = metadata

        self._save_metadata_index(metadata_file, metadata_index)
        logger.info(f"Built {label} metadata index with {len(metadata_index)} entries")
        return metadata_index

    def _get_v1_metadata_index(self) -> Dict[str, Dict[str, object]]:
        """Return the v1 UUID-keyed metadata index from file_v1.json."""
        return self._build_metadata_index(self.files_dir, self.v1_metadata_file, 'v1')

    def _get_v2_metadata_index(self) -> Dict[str, Dict[str, object]]:
        """Return the v2 UUID-keyed metadata index from file_v2.json."""
        return self._build_metadata_index(self.files_v2_dir, self.v2_metadata_file, 'v2')

    def _build_v1_uuid_to_filename_mapping(self) -> Dict[str, str]:
        """Build and cache a mapping from v1 UUID to normalized asset filename."""
        if self._v1_uuid_to_filename_cache:
            return self._v1_uuid_to_filename_cache

        mapping: Dict[str, str] = {}

        for uuid_value, metadata in self._get_v1_metadata_index().items():
            normalized_filename = metadata.get('normalized_filename')
            if normalized_filename:
                mapping[uuid_value] = str(normalized_filename)

        self._v1_uuid_to_filename_cache = mapping
        logger.info(f"Built v1 UUID to filename mapping with {len(mapping)} entries")
        return mapping

    def _build_v2_filename_to_uuid_mapping(self) -> Dict[str, str]:
        """Build and cache a mapping from normalized asset filename to v2 UUID."""
        if self._v2_filename_to_uuid_cache:
            return self._v2_filename_to_uuid_cache

        mapping: Dict[str, str] = {}

        for uuid_value, metadata in self._get_v2_metadata_index().items():
            filename_value = metadata.get('normalized_filename')
            if not filename_value:
                continue

            existing_uuid = mapping.get(filename_value)
            if existing_uuid and existing_uuid != str(uuid_value):
                logger.warning(
                    f"Duplicate filename '{filename_value}' in files_v2: "
                    f"keeping {existing_uuid}, skipping {uuid_value}"
                )
                continue

            mapping[str(filename_value)] = str(uuid_value)

        self._v2_filename_to_uuid_cache = mapping
        logger.info(f"Built v2 filename to UUID mapping with {len(mapping)} entries")
        return mapping

    def _default_asset_host(self, html: str) -> str:
        """Use the first asset-proxy host found in the page, else fall back to webbuilder.pfizer."""
        match = re.search(self.PERMALINK_PATTERN, html)
        if match:
            return match.group('host')
        return 'webbuilder.pfizer'
    
    def _build_uuid_mapping(self) -> Dict[str, str]:
        """
        Build a mapping from v1 UUID to v2 UUID by comparing JSON metadata filenames.

        Workflow:
        - Read page UUID from permalink
        - Find that UUID in files/ JSON metadata
        - Read the asset filename from the matching file JSON
        - Find the same filename in files_v2/ JSON metadata
        - Use that record's UUID as the replacement UUID
        
        Returns:
            Dictionary mapping v1 UUID to v2 UUID
        """
        if self._uuid_mapping_cache:
            return self._uuid_mapping_cache
        
        mapping: Dict[str, str] = {}
        
        try:
            v1_uuid_to_filename = self._build_v1_uuid_to_filename_mapping()
            v2_filename_to_uuid = self._build_v2_filename_to_uuid_mapping()

            for v1_uuid, filename_value in v1_uuid_to_filename.items():
                v2_uuid = v2_filename_to_uuid.get(filename_value)
                if v2_uuid:
                    mapping[v1_uuid] = v2_uuid
            
            logger.info(f"Built UUID mapping with {len(mapping)} entries")
            self._uuid_mapping_cache = mapping
            
        except Exception as e:
            logger.error(f"Error building UUID mapping: {str(e)}")
        
        return mapping
    
    def _extract_references_from_html(self, html: str) -> List[Dict[str, str]]:
        """
        Extract convertible image references from HTML content.
        
        Args:
            html: HTML string to search
        
        Returns:
            List of dictionaries describing either asset-proxy URLs or direct image filenames.
        """
        references: List[Dict[str, str]] = []
        default_host = self._default_asset_host(html)

        for match in re.finditer(self.PERMALINK_PATTERN, html):
            references.append({
                'kind': 'asset_proxy',
                'original': match.group(0),
                'host': match.group('host'),
                'site_id': match.group('site_id'),
                'lookup_key': match.group('asset'),
            })

        for match in self.IMAGE_ATTRIBUTE_PATTERN.finditer(html):
            attribute_value = match.group('value')
            if not _is_direct_image_reference(attribute_value):
                continue

            references.append({
                'kind': 'direct_filename',
                'original': attribute_value,
                'host': default_host,
                'site_id': self.v2_site_id,
                'lookup_key': _normalize_filename(attribute_value),
            })

        return references
    
    def _convert_reference(
        self,
        reference: Dict[str, str],
        uuid_mapping: Dict[str, str],
        filename_to_uuid_mapping: Dict[str, str]
    ) -> Optional[str]:
        """
        Convert a single asset reference to v2 format.
        
        Args:
            reference: Extracted reference metadata
            uuid_mapping: Mapping of v1 UUID to v2 UUID
            filename_to_uuid_mapping: Mapping of normalized filename to v2 UUID
        
        Returns:
            New URL with v2 site ID and UUID, or None if mapping not found
        """
        lookup_key = reference['lookup_key']

        if reference['kind'] == 'asset_proxy':
            new_uuid = uuid_mapping.get(lookup_key)
            if not new_uuid:
                logger.warning(f"No v2 UUID mapping found for v1 UUID: {lookup_key}")
                return None
        else:
            new_uuid = filename_to_uuid_mapping.get(lookup_key)
            if not new_uuid:
                logger.warning(f"No v2 UUID mapping found for filename: {lookup_key}")
                return None

        host = reference.get('host') or 'webbuilder.pfizer'
        new_url = f"https://{host}/webbuilder/asset-proxy/{self.v2_site_id}/{new_uuid}"

        logger.debug(f"Converted {reference['original']} -> {new_url}")
        return new_url
    
    def _update_html_with_new_permalinks(
        self,
        html: str,
        permalink_updates: Dict[str, str]
    ) -> str:
        """
        Replace old permalinks with new ones in HTML.
        
        Args:
            html: Original HTML string
            permalink_updates: Dictionary mapping old URL to new URL
        
        Returns:
            Updated HTML string
        """
        updated_html = html
        
        for old_url, new_url in permalink_updates.items():
            if new_url:
                updated_html = updated_html.replace(old_url, new_url)
                logger.debug(f"Replaced permalink in HTML: {old_url} -> {new_url}")
        
        return updated_html
    
    def convert_page(self, page_file_path: Path, uuid_mapping: Dict[str, str]) -> Tuple[bool, str]:
        """
        Convert permalinks in a single page JSON file.
        
        Args:
            page_file_path: Path to the page JSON file
            uuid_mapping: Mapping of v1 UUID to v2 UUID
        
        Returns:
            Tuple of (success, message)
        """
        try:
            # Read the page JSON
            with open(page_file_path, 'r', encoding='utf-8') as f:
                page_data = json.load(f)
            
            # Extract HTML from the page data structure
            # Expected structure: page_data['storage']['data']['html']
            if 'storage' not in page_data or 'data' not in page_data.get('storage', {}):
                return True, f"Skipped {page_file_path.name}: No storage.data found"
            
            html = page_data['storage']['data'].get('html', '')
            
            if not html:
                return True, f"Skipped {page_file_path.name}: No HTML content"
            
            # Extract all convertible references.
            references = self._extract_references_from_html(html)
            
            if not references:
                return True, f"Skipped {page_file_path.name}: No image references found"
            
            # Build conversion map for this page
            permalink_updates = {}
            converted_count = 0
            filename_to_uuid_mapping = self._build_v2_filename_to_uuid_mapping()
            
            for reference in references:
                new_url = self._convert_reference(reference, uuid_mapping, filename_to_uuid_mapping)
                if new_url:
                    permalink_updates[reference['original']] = new_url
                    converted_count += 1
            
            if not permalink_updates:
                return True, f"Skipped {page_file_path.name}: No matching UUIDs or filenames found in mapping"
            
            # Update HTML with new permalinks
            updated_html = self._update_html_with_new_permalinks(html, permalink_updates)
            
            # Update page data
            page_data['storage']['data']['html'] = updated_html
            
            # Write back to file
            with open(page_file_path, 'w', encoding='utf-8') as f:
                json.dump(page_data, f, ensure_ascii=False, indent=2)
            
            return True, f"Updated {page_file_path.name}: {converted_count} permalinks converted"
        
        except json.JSONDecodeError as e:
            return False, f"Error parsing JSON {page_file_path.name}: {str(e)}"
        except IOError as e:
            return False, f"Error reading/writing {page_file_path.name}: {str(e)}"
        except Exception as e:
            return False, f"Unexpected error processing {page_file_path.name}: {str(e)}"
    
    def convert_all_pages(self) -> Tuple[int, int, List[str]]:
        """
        Convert permalinks in all page JSON files.
        
        Returns:
            Tuple of (successful_count, failed_count, messages)
        """
        # Validate directories
        is_valid, error_msg = self._validate_directories()
        if not is_valid:
            logger.error(error_msg)
            self._emit_progress(f"Error: {error_msg}")
            return 0, 0, [error_msg]
        
        # Build UUID mapping
        self._emit_progress("Building UUID mapping...")
        uuid_mapping = self._build_uuid_mapping()
        
        if not uuid_mapping:
            msg = (
                "Error: No UUID mapping found. "
                "Check that files and files_v2 contain matching details.filename values."
            )
            logger.error(msg)
            self._emit_progress(msg)
            return 0, 0, [msg]
        
        self._emit_progress(f"UUID mapping complete. Found {len(uuid_mapping)} mappings.")
        
        # Process all page files
        successful = 0
        failed = 0
        messages = []
        
        page_files = list(self.pages_dir.glob("*.json"))
        self.total_pages = len(page_files)
        self.processed_pages = 0
        
        logger.info(f"Found {len(page_files)} page files to process")
        self._emit_progress(f"Starting conversion of {self.total_pages} pages...", 0, self.total_pages)
        
        for page_file_path in page_files:
            success, message = self.convert_page(page_file_path, uuid_mapping)
            messages.append(message)
            
            if success:
                successful += 1
            else:
                failed += 1
                logger.warning(message)
            
            self.processed_pages += 1
            self._emit_progress(
                f"Processing page: {page_file_path.name}",
                self.processed_pages,
                self.total_pages
            )
        
        self._emit_progress(
            f"Conversion complete: {successful} successful, {failed} failed",
            self.total_pages,
            self.total_pages
        )
        
        logger.info(
            f"Conversion complete: {successful} successful, {failed} failed "
            f"out of {len(page_files)} total"
        )
        
        return successful, failed, messages


def convert_permalinks(
    site_id: int,
    pages_dir: str = None,
    files_dir: str = None,
    files_v2_dir: str = None,
    v1_site_id: str = None,
    v2_site_id: str = None,
    progress_callback=None,
    base_data_path: str = None
) -> Dict:
    """
    Main function to convert permalinks for a site.
    
    Args:
        site_id: Site ID (for compatibility)
        pages_dir: Custom pages directory. If None, uses default.
        files_dir: Custom files directory. If None, uses default.
        files_v2_dir: Custom files_v2 directory. If None, uses default.
        v1_site_id: Original site ID. If None, extracted from URLs.
        v2_site_id: New site ID. If None, uses V2_SITE_ID from env.
        progress_callback: Callback function for progress updates
        base_data_path: Base path to data directories. If None, uses default from settings.
    
    Returns:
        Dictionary with conversion results
    """
    from django.conf import settings
    from dotenv import load_dotenv
    
    # Load environment variables
    load_dotenv()
    
    # Get V2_SITE_ID from environment if not provided
    if not v2_site_id:
        v2_site_id = os.getenv('V2_SITE_ID')
    
    if not v2_site_id:
        return {
            'success': False,
            'message': 'V2_SITE_ID environment variable not set and not provided',
            'successful_count': 0,
            'failed_count': 0,
            'details': []
        }
    
    # Set up directory paths (use provided values or defaults)
    if not pages_dir:
        if base_data_path is None:
            base_data_path = os.path.join(
                settings.BASE_DIR,
                'site_manager',
                'static',
                'block_import',
                'data'
            )
        pages_dir = os.path.join(base_data_path, 'pages')
    
    if not files_dir:
        if base_data_path is None:
            base_data_path = os.path.join(
                settings.BASE_DIR,
                'site_manager',
                'static',
                'block_import',
                'data'
            )
        files_dir = os.path.join(base_data_path, 'files')
    
    if not files_v2_dir:
        if base_data_path is None:
            base_data_path = os.path.join(
                settings.BASE_DIR,
                'site_manager',
                'static',
                'block_import',
                'data'
            )
        files_v2_dir = os.path.join(base_data_path, 'files_v2')
    
    # Create converter and run
    converter = PermalinkConverter(
        pages_dir,
        files_dir,
        files_v2_dir,
        v1_site_id or "unknown",
        v2_site_id,
        progress_callback=progress_callback
    )
    successful, failed, messages = converter.convert_all_pages()
    
    return {
        'success': failed == 0,
        'message': f'Conversion complete: {successful} successful, {failed} failed',
        'successful_count': successful,
        'failed_count': failed,
        'details': messages,
        'v1_site_id': v1_site_id,
        'v2_site_id': v2_site_id
    }


def ensure_metadata_files(
    files_dir: str,
    files_v2_dir: str,
    v1_site_id: str = None,
    v2_site_id: str = None
) -> Dict[str, object]:
    """Create file_v1.json and file_v2.json if they are missing and return basic status."""
    converter = PermalinkConverter(
        pages_dir=files_dir,
        files_dir=files_dir,
        files_v2_dir=files_v2_dir,
        v1_site_id=v1_site_id or 'unknown',
        v2_site_id=v2_site_id or 'unknown'
    )

    v1_exists_before = converter.v1_metadata_file.exists()
    v2_exists_before = converter.v2_metadata_file.exists()

    v1_metadata = converter._get_v1_metadata_index()
    v2_metadata = converter._get_v2_metadata_index()

    return {
        'file_v1_path': str(converter.v1_metadata_file),
        'file_v2_path': str(converter.v2_metadata_file),
        'file_v1_created': not v1_exists_before and converter.v1_metadata_file.exists(),
        'file_v2_created': not v2_exists_before and converter.v2_metadata_file.exists(),
        'file_v1_count': len(v1_metadata),
        'file_v2_count': len(v2_metadata),
    }
