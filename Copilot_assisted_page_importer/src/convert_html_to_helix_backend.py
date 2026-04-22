#!/usr/bin/env python3
"""
Backend HTML -> Helix converter using GitHub Copilot / GitHub Models.

This script is intentionally written in a straightforward style so it is easy
to read and customize.
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import random
import re
import shutil
import string
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

try:
	from bs4 import BeautifulSoup
except Exception:
	BeautifulSoup = None

try:
	from playwright.sync_api import sync_playwright
except Exception:
	sync_playwright = None


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GITHUB_COPILOT_BASE_URL = "https://api.githubcopilot.com"
GITHUB_MODELS_BASE_URL = "https://models.inference.ai.azure.com"
GITHUB_MODELS_ALT_BASE_URL = "https://models.github.ai/inference"

COPILOT_TOKEN_ENV = "GITHUB_COPILOT_TOKEN"
PAT_TOKEN_ENV = "GITHUB_TOKEN"

DEFAULT_MODEL = "gpt-4o"
DEFAULT_TEMPERATURE = 0.4
DEFAULT_TIMEOUT_SECONDS = 90.0
MAX_INPUT_CHARS_PER_CHUNK = 12000
PROMPT_COMPONENT_ANALYSIS_CHAR_LIMIT = 1200
PROMPT_COMPONENT_SNIPPET_CHAR_LIMIT = 700
HARD_PROMPT_COMPONENT_LIMIT = 8
MAX_RATE_LIMIT_RETRIES_PER_ENDPOINT = 3
RATE_LIMIT_BASE_DELAY_SECONDS = 6.0
RATE_LIMIT_MAX_DELAY_SECONDS = 30.0

WEBBUILDER_DASHBOARD_URL = "https://webbuilder.pfizer/webbuilder/dashboard"
WEBBUILDER_USERNAME_ENV = "USERNAME"
WEBBUILDER_PASSWORD_ENV = "PASSWORD"
WEBBUILDER_INSTANCE_ID_ENV = "INSTANCE_ID"
WEBBUILDER_SEARCH_WAIT_MS = 3000
WEBBUILDER_MENU_WAIT_MS = 2000
WEBBUILDER_LOGIN_WAIT_MS = 5000
WEBBUILDER_FILE_MANAGER_WAIT_MS = 5000

IMAGE_EXTENSIONS = (
	".svg", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp",
	".ico", ".tiff", ".tif", ".avif",
)

# Curated options for this use case (you can still pass any model id).
MODEL_OPTIONS = [
	"gpt-4o",
	"gpt-4o-mini",
	"claude-sonnet-4-6",
	"claude-sonnet-4",
]

COMPONENT_KEYWORDS = {
	"img": ["image", "image link"],
	"button": ["button", "button group"],
	"a": ["external link", "image link", "quicklinks"],
	"h1": ["heading", "section heading"],
	"h2": ["heading", "section heading"],
	"h3": ["heading", "section heading"],
	"h4": ["heading", "section heading"],
	"h5": ["heading", "section heading"],
	"h6": ["heading", "section heading"],
	"table": ["table", "table with overlay"],
	"video": ["brightcove video", "video"],
	"form": ["form wrapper"],
	"input": ["input", "radio"],
	"textarea": ["textarea"],
	"select": ["select"],
	"details": ["accordion"],
}

SYSTEM_PROMPT = """
You are an expert HTML-to-Helix converter running in a backend migration tool.

Your goal:
1) Keep the input page meaning, text, and content order.
2) Convert HTML structure into Helix components using the supplied component CSV examples.
3) Preserve original IDs where present.
4) If an element has no id, create one with this pattern: i + 4 lowercase letters/digits.
5) Never produce self-closing custom component tags (helix-*, extras-*, cdp-*).
6) Ensure valid closing tags and balanced nesting.
7) Output only final HTML. No markdown, no commentary.

Important conversion hints:
- <img> should become a Helix image component where possible.
- <button> and CTA-like controls should become Helix button components.
- Heading tags should map to Helix heading components.
- FAQ/collapsible content should map to accordion components.
- External links can map to external link components.

If a suitable component is not found in the provided library, keep original HTML for that part.
""".strip()

CUSTOM_COMPONENT_TAG_RE = re.compile(
	r"<((?:helix-[\w-]+|extras-[\w-]+|helix-form-[\w-]+|cdp-[\w-]+)\b[^>]*)/\s*>",
	re.IGNORECASE,
)

OPENING_TAG_WITH_OPTIONAL_ID_RE = re.compile(
	r"<(?P<name>(?:helix-[\w-]+|extras-[\w-]+|helix-form-[\w-]+|cdp-[\w-]+|"
	r"p|div|a|section|article|main|ul|ol|li|table|thead|tbody|tr|td|th|"
	r"h1|h2|h3|h4|h5|h6))\b(?P<attrs>[^<>]*?)(?P<selfclose>/?)>",
	re.IGNORECASE,
)

CUSTOM_TAG_TOKEN_RE = re.compile(
	r"<(\/?)((?:helix-[\w-]+|extras-[\w-]+|helix-form-[\w-]+|cdp-[\w-]+)\b[^>]*)>",
	re.IGNORECASE,
)

ID_ATTR_RE = re.compile(r"\bid\s*=\s*([\"'])([^\"']*)\1", re.IGNORECASE)
HELIX_VERSION_TARGET_TAG_RE = re.compile(
	r"<(?P<name>(?:helix-core-[\w-]+|helix-form-[\w-]+))\b(?P<attrs>[^<>]*?)(?P<selfclose>/?)>",
	re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class HelixComponent:
	name: str
	normalized_name: str
	html_template: str


@dataclass
class ApiCallResult:
	response_text: str
	endpoint_used: str


class PayloadTooLargeError(RuntimeError):
	"""Raised when request payload exceeds model endpoint limits."""


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("helix_backend_converter")


# ---------------------------------------------------------------------------
# Client and API helpers (adapted from chatbot-style handling)
# ---------------------------------------------------------------------------

def normalize_base_url(url: str) -> str:
	cleaned = (url or "").strip().rstrip("/")
	if not cleaned:
		return GITHUB_MODELS_BASE_URL
	if not cleaned.startswith(("http://", "https://")):
		cleaned = f"https://{cleaned}"
	return cleaned


def v1_variant(url: str) -> str:
	cleaned = normalize_base_url(url)
	if cleaned.endswith("/v1"):
		return cleaned[:-3]
	return f"{cleaned}/v1"


def get_token() -> tuple[str, bool]:
	copilot_token = os.getenv(COPILOT_TOKEN_ENV)
	if copilot_token:
		return copilot_token, True

	pat_token = os.getenv(PAT_TOKEN_ENV)
	if pat_token:
		return pat_token, False

	raise RuntimeError(
		f"No token found. Set {COPILOT_TOKEN_ENV} (preferred) or {PAT_TOKEN_ENV} in environment/.env"
	)


def build_client(token: str, base_url: str) -> OpenAI:
	timeout_raw = os.getenv("API_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))
	try:
		timeout = float(timeout_raw)
	except ValueError:
		timeout = DEFAULT_TIMEOUT_SECONDS
	return OpenAI(base_url=normalize_base_url(base_url), api_key=token, timeout=timeout)


def parse_api_error(exc: Exception) -> tuple[int | None, str]:
	status_code = getattr(exc, "status_code", None)
	message = str(exc)

	response = getattr(exc, "response", None)
	if response is not None:
		try:
			payload = response.json()
			if isinstance(payload, dict):
				if isinstance(payload.get("error"), dict):
					message = payload["error"].get("message", message)
				else:
					message = payload.get("message", message)
		except Exception:
			pass
	return status_code, message


def is_sso_related_error(status_code: int | None, message: str) -> bool:
	text = message.lower()
	markers = ("sso", "saml", "single sign-on", "resource protected by organization saml enforcement")
	return any(m in text for m in markers)


def is_connection_error(message: str) -> bool:
	text = message.lower()
	markers = (
		"connection error",
		"connect timeout",
		"read timeout",
		"failed to resolve",
		"ssl",
		"network is unreachable",
		"name or service not known",
	)
	return any(m in text for m in markers)


def is_not_found_error(status_code: int | None, message: str) -> bool:
	return status_code == 404 or "404 page not found" in message.lower()


def is_payload_too_large_error(status_code: int | None, message: str) -> bool:
	text = message.lower()
	markers = (
		"payload too large",
		"request body too large",
		"max size",
		"too many tokens",
		"context length",
	)
	return status_code == 413 or any(marker in text for marker in markers)


def is_rate_limit_error(status_code: int | None, message: str) -> bool:
	text = message.lower()
	markers = (
		"too many requests",
		"rate limit",
		"retry later",
	)
	return status_code == 429 or any(marker in text for marker in markers)


def candidate_endpoints(current_base_url: str, include_copilot: bool = True) -> list[str]:
	seed = [
		GITHUB_MODELS_BASE_URL,
		GITHUB_MODELS_ALT_BASE_URL,
	]
	if include_copilot:
		seed.append(GITHUB_COPILOT_BASE_URL)
	candidates: list[str] = []
	seen: set[str] = set()
	for endpoint in seed + [current_base_url]:
		for variant in (normalize_base_url(endpoint), v1_variant(endpoint)):
			normalized = normalize_base_url(variant)
			if normalized not in seen:
				seen.add(normalized)
				candidates.append(normalized)

	current = normalize_base_url(current_base_url)
	return [c for c in candidates if c != current]


def fetch_models(client: OpenAI) -> list[str]:
	try:
		page = client.models.list()
		return sorted(model.id for model in page.data)
	except Exception as exc:
		status_code, message = parse_api_error(exc)
		logger.warning("Could not fetch models (%s): %s", status_code, message)
		return []


def extract_message_content(response: object) -> str:
	try:
		content = response.choices[0].message.content
	except Exception:
		return ""

	if content is None:
		return ""
	if isinstance(content, str):
		return content
	if isinstance(content, list):
		text_parts = []
		for item in content:
			if isinstance(item, str):
				text_parts.append(item)
			elif isinstance(item, dict) and isinstance(item.get("text"), str):
				text_parts.append(item["text"])
		return "\n".join(text_parts)
	return str(content)


def call_model_with_failover(
	token: str,
	model: str,
	messages: list[dict],
	temperature: float,
	start_base_url: str,
	include_copilot_endpoints: bool = True,
) -> ApiCallResult:
	endpoints_to_try = [normalize_base_url(start_base_url)] + candidate_endpoints(
		start_base_url,
		include_copilot=include_copilot_endpoints,
	)
	last_error: str | None = None

	for endpoint in endpoints_to_try:
		rate_limit_retries = 0
		while True:
			logger.info("Calling model '%s' on endpoint: %s", model, endpoint)
			client = build_client(token, endpoint)
			try:
				response = client.chat.completions.create(
					model=model,
					temperature=temperature,
					messages=messages,
				)
				text = extract_message_content(response)
				return ApiCallResult(response_text=text, endpoint_used=endpoint)
			except Exception as exc:
				status_code, message = parse_api_error(exc)
				last_error = f"status={status_code}, message={message}"
				logger.warning("Model call failed on %s: %s", endpoint, last_error)

				if is_payload_too_large_error(status_code, message):
					raise PayloadTooLargeError(
						f"Payload too large on endpoint {endpoint}. Details: {last_error}"
					) from exc

				if status_code in {401, 403} or is_sso_related_error(status_code, message):
					raise RuntimeError(
						"Authentication/authorization failed. Check token permissions and SSO authorization. "
						f"Details: {last_error}"
					) from exc

				if is_rate_limit_error(status_code, message):
					rate_limit_retries += 1
					if rate_limit_retries <= MAX_RATE_LIMIT_RETRIES_PER_ENDPOINT:
						wait_seconds = min(
							RATE_LIMIT_BASE_DELAY_SECONDS * (2 ** (rate_limit_retries - 1)),
							RATE_LIMIT_MAX_DELAY_SECONDS,
						)
						wait_seconds += random.uniform(0.0, 1.5)
						logger.warning(
							"Rate limited on %s. Retrying same endpoint in %.1f seconds (%d/%d).",
							endpoint,
							wait_seconds,
							rate_limit_retries,
							MAX_RATE_LIMIT_RETRIES_PER_ENDPOINT,
						)
						time.sleep(wait_seconds)
						continue

					# Exhausted 429 retries on this endpoint; move to next endpoint.
					break

				if is_not_found_error(status_code, message) or is_connection_error(message):
					break

				# Unknown endpoint error: move to next failover endpoint.
				break

	raise RuntimeError(f"All endpoints failed for model '{model}'. Last error: {last_error}")


# ---------------------------------------------------------------------------
# Component library loader and selection
# ---------------------------------------------------------------------------

def normalize_component_name(name: str) -> str:
	return re.sub(r"\s+", " ", name.strip().lower())


def load_components(csv_path: Path) -> list[HelixComponent]:
	if not csv_path.exists():
		raise FileNotFoundError(f"CSV not found: {csv_path}")

	components: list[HelixComponent] = []
	with csv_path.open("r", encoding="utf-8", newline="") as handle:
		reader = csv.DictReader(handle)
		expected_columns = {"Component Name", "HTML Content"}
		if reader.fieldnames is None or not expected_columns.issubset(set(reader.fieldnames)):
			raise ValueError(
				"CSV must contain columns: 'Component Name' and 'HTML Content'. "
				f"Found: {reader.fieldnames}"
			)

		for row in reader:
			name = (row.get("Component Name") or "").strip()
			html_template = (row.get("HTML Content") or "").strip()
			if not name or not html_template:
				continue
			components.append(
				HelixComponent(
					name=name,
					normalized_name=normalize_component_name(name),
					html_template=html_template,
				)
			)

	if not components:
		raise ValueError(f"No usable rows found in CSV: {csv_path}")

	logger.info("Loaded %d component templates from CSV", len(components))
	return components


def detect_component_keywords_from_html(html: str) -> set[str]:
	html_lower = html.lower()
	detected: set[str] = set()

	if re.search(r"<img\b", html_lower):
		detected.update(COMPONENT_KEYWORDS["img"])
	if re.search(r"<button\b", html_lower) or " class=\"btn" in html_lower or "cta" in html_lower:
		detected.update(COMPONENT_KEYWORDS["button"])
	if re.search(r"<a\b", html_lower):
		detected.update(COMPONENT_KEYWORDS["a"])
	if re.search(r"<h[1-6]\b", html_lower):
		detected.update(COMPONENT_KEYWORDS["h1"])
	if re.search(r"<table\b", html_lower):
		detected.update(COMPONENT_KEYWORDS["table"])
	if re.search(r"<video\b", html_lower) or "brightcove" in html_lower or "video-js" in html_lower:
		detected.update(COMPONENT_KEYWORDS["video"])
	if re.search(r"<form\b", html_lower):
		detected.update(COMPONENT_KEYWORDS["form"])
	if re.search(r"<input\b", html_lower):
		detected.update(COMPONENT_KEYWORDS["input"])
	if re.search(r"<textarea\b", html_lower):
		detected.update(COMPONENT_KEYWORDS["textarea"])
	if re.search(r"<select\b", html_lower):
		detected.update(COMPONENT_KEYWORDS["select"])
	if re.search(r"<details\b", html_lower) or "accordion" in html_lower or "faq" in html_lower:
		detected.update(COMPONENT_KEYWORDS["details"])

	return detected


def select_relevant_components(
	all_components: list[HelixComponent],
	html: str,
	max_components: int,
) -> list[HelixComponent]:
	detected_keywords = detect_component_keywords_from_html(html)
	selected: list[HelixComponent] = []

	for component in all_components:
		if any(keyword in component.normalized_name for keyword in detected_keywords):
			selected.append(component)

	# Always include a small core set for better conversion quality.
	core_keywords = ["image", "button", "heading", "content", "accordion", "external link"]
	for component in all_components:
		if any(keyword in component.normalized_name for keyword in core_keywords):
			if component not in selected:
				selected.append(component)

	# If selection is too small, add more from top of CSV to provide broader context.
	if len(selected) < min(8, max_components):
		for component in all_components:
			if component not in selected:
				selected.append(component)
			if len(selected) >= min(8, max_components):
				break

	return selected[:max_components]


def build_component_context(components: list[HelixComponent], max_snippet_chars: int = 1800) -> str:
	blocks: list[str] = []
	for component in components:
		snippet = component.html_template[:max_snippet_chars]
		block = (
			f"Component: {component.name}\n"
			f"Template:\n{snippet}\n"
		)
		blocks.append(block)
	return "\n\n".join(blocks)


# ---------------------------------------------------------------------------
# Response cleanup and validation
# ---------------------------------------------------------------------------

def strip_markdown_fences(text: str) -> str:
	cleaned = (text or "").strip()
	while cleaned.startswith("```"):
		first_newline = cleaned.find("\n")
		cleaned = cleaned[first_newline + 1 :] if first_newline != -1 else cleaned[3:]
		cleaned = cleaned.strip()
	if cleaned.endswith("```"):
		cleaned = cleaned[:-3].strip()
	return cleaned


def generate_short_id(existing: set[str]) -> str:
	while True:
		candidate = "i" + "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
		if candidate not in existing:
			existing.add(candidate)
			return candidate


def expand_self_closing_custom_tags(html: str) -> str:
	def _expand(match: re.Match) -> str:
		inner = match.group(1).strip()
		tag_name = inner.split()[0] if inner else ""
		attrs = inner[len(tag_name) :] if tag_name else ""
		return f"<{tag_name}{attrs}></{tag_name}>"

	return CUSTOM_COMPONENT_TAG_RE.sub(_expand, html)


def ensure_unique_ids(html: str) -> str:
	used_ids: set[str] = set()

	def _replace(match: re.Match) -> str:
		tag_name = match.group("name")
		attrs = match.group("attrs") or ""
		self_close = match.group("selfclose") or ""

		id_match = ID_ATTR_RE.search(attrs)
		if id_match:
			current_id = id_match.group(2).strip()
			if current_id and current_id not in used_ids:
				used_ids.add(current_id)
			else:
				new_id = generate_short_id(used_ids)
				attrs = ID_ATTR_RE.sub(f'id="{new_id}"', attrs, count=1)
		else:
			new_id = generate_short_id(used_ids)
			attrs = f' id="{new_id}"{attrs}'

		return f"<{tag_name}{attrs}{self_close}>"

	return OPENING_TAG_WITH_OPTIONAL_ID_RE.sub(_replace, html)


def ensure_hwc_version_on_helix_tags(html: str, version: str = "4.0.1198") -> str:
	def _replace(match: re.Match) -> str:
		tag_name = match.group("name")
		attrs = match.group("attrs") or ""
		self_close = match.group("selfclose") or ""

		if "data-hwc-version" in attrs.lower():
			return f"<{tag_name}{attrs}{self_close}>"

		if attrs and not attrs.endswith(" "):
			attrs = f"{attrs} "

		return f'<{tag_name}{attrs}data-hwc-version="{version}"{self_close}>'

	return HELIX_VERSION_TARGET_TAG_RE.sub(_replace, html)


def close_unbalanced_custom_tags(html: str) -> str:
	stack: list[str] = []
	for match in CUSTOM_TAG_TOKEN_RE.finditer(html):
		slash = match.group(1)
		body = match.group(2).strip()
		token = match.group(0)

		tag_name = body.split()[0].lower()
		self_closing = token.endswith("/>")

		if not slash and not self_closing:
			stack.append(tag_name)
			continue

		if slash:
			if stack and stack[-1] == tag_name:
				stack.pop()
			elif tag_name in stack:
				# Recover from mismatched nesting by closing intermediate tags.
				while stack and stack[-1] != tag_name:
					stack.pop()
				if stack and stack[-1] == tag_name:
					stack.pop()

	if not stack:
		return html

	closing_text = "".join(f"</{tag}>" for tag in reversed(stack))
	return html + "\n" + closing_text


def post_process_html(model_html: str) -> str:
	output = strip_markdown_fences(model_html)
	output = expand_self_closing_custom_tags(output)
	output = ensure_unique_ids(output)
	output = ensure_hwc_version_on_helix_tags(output)
	output = close_unbalanced_custom_tags(output)
	return output.strip()


def format_reference_html_for_scanning(html: str) -> str:
	"""Prettify/normalize reference HTML before chunking and model scanning."""
	text = (html or "").strip()
	if not text:
		return text

	if BeautifulSoup is not None:
		soup = BeautifulSoup(text, "html.parser")
		return soup.prettify()

	# Fallback when bs4 is unavailable.
	return re.sub(r">\s+<", ">\n<", text)


def extract_body_inner_html(html: str) -> str:
	"""Return only inner content of <body> ... </body> when present."""
	text = (html or "").strip()
	if not text:
		return text

	if BeautifulSoup is not None:
		soup = BeautifulSoup(text, "html.parser")
		if soup.body is not None:
			return "".join(str(child) for child in soup.body.contents).strip()

	body_open = re.search(r"<body\b[^>]*>", text, flags=re.IGNORECASE | re.DOTALL)
	if not body_open:
		return text

	body_start = body_open.end()
	body_close = re.search(r"</body\s*>", text[body_start:], flags=re.IGNORECASE | re.DOTALL)
	if body_close:
		return text[body_start: body_start + body_close.start()].strip()

	return text[body_start:].strip()


def _extract_first_tag_block(html: str, tag_name: str) -> str:
	open_re = re.compile(rf"<{tag_name}\b[^>]*>", flags=re.IGNORECASE)
	close_re = re.compile(rf"</{tag_name}\s*>", flags=re.IGNORECASE)
	start_match = open_re.search(html)
	if not start_match:
		return ""

	start = start_match.start()
	index = start_match.end()
	depth = 1

	while depth > 0 and index < len(html):
		next_open = open_re.search(html, index)
		next_close = close_re.search(html, index)

		if not next_close:
			return html[start:]

		if next_open and next_open.start() < next_close.start():
			depth += 1
			index = next_open.end()
		else:
			depth -= 1
			index = next_close.end()

	return html[start:index]


def _top_level_signature(node: object) -> str:
	name = getattr(node, "name", None)
	if not name:
		return ""

	parts = [name.lower()]
	for attr in ("src", "href", "role", "type", "data-drupal-selector"):
		value = getattr(node, "get", lambda *_args, **_kwargs: None)(attr)
		if value:
			parts.append(f"{attr}={str(value).strip().lower()}")

	classes = getattr(node, "get", lambda *_args, **_kwargs: None)("class")
	if classes:
		if isinstance(classes, list):
			parts.append("class=" + " ".join(str(c).strip().lower() for c in classes if str(c).strip()))
		else:
			parts.append("class=" + str(classes).strip().lower())

	return "|".join(parts)


def ensure_body_content_coverage(reference_body_html: str, converted_body_html: str) -> str:
	"""
	Ensure important body content is not dropped in conversion.
	At minimum, preserve missing top-level sections such as header/main/footer/scripts.
	"""
	reference_body = (reference_body_html or "").strip()
	converted_body = (converted_body_html or "").strip()

	if not reference_body:
		return converted_body
	if not converted_body:
		return reference_body

	if BeautifulSoup is None:
		# Fallback: ensure major semantic blocks exist.
		for tag in ("header", "main", "footer"):
			if re.search(rf"<{tag}\b", reference_body, flags=re.IGNORECASE) and not re.search(
				rf"<{tag}\b", converted_body, flags=re.IGNORECASE
			):
				block = _extract_first_tag_block(reference_body, tag)
				if block:
					converted_body += "\n\n" + block
		return converted_body.strip()

	ref_soup = BeautifulSoup(f"<body>{reference_body}</body>", "html.parser")
	conv_soup = BeautifulSoup(f"<body>{converted_body}</body>", "html.parser")

	ref_body = ref_soup.body
	conv_body = conv_soup.body
	if ref_body is None or conv_body is None:
		return converted_body

	# Ensure semantic anchors are present.
	for tag in ("header", "main", "footer"):
		if ref_body.find(tag) is not None and conv_body.find(tag) is None:
			missing = ref_body.find(tag)
			if missing is not None:
				fragment = BeautifulSoup(str(missing), "html.parser")
				node = fragment.find(tag)
				if node is not None:
					conv_body.append(node)

	# Ensure top-level nodes from reference body are not lost.
	conv_signatures = {
		_top_level_signature(node)
		for node in conv_body.contents
		if getattr(node, "name", None)
	}

	for ref_node in ref_body.contents:
		if not getattr(ref_node, "name", None):
			continue
		sig = _top_level_signature(ref_node)
		if sig and sig not in conv_signatures:
			fragment = BeautifulSoup(str(ref_node), "html.parser")
			node = fragment.find()
			if node is not None:
				conv_body.append(node)
				conv_signatures.add(sig)

	return "".join(str(child) for child in conv_body.contents).strip()


def remove_anchor_before_first_div(html: str) -> str:
	"""Remove only the top-level <a> tag that appears immediately before the first top-level <div>."""
	text = (html or "").strip()
	if not text:
		return text

	if BeautifulSoup is not None:
		soup = BeautifulSoup(f"<body>{text}</body>", "html.parser")
		body = soup.body
		if body is None:
			return text

		contents = list(body.contents)
		first_div_index: int | None = None
		for idx, node in enumerate(contents):
			if getattr(node, "name", None) == "div":
				first_div_index = idx
				break

		if first_div_index is None:
			return text

		prev_index = first_div_index - 1
		while prev_index >= 0:
			prev_node = contents[prev_index]
			prev_name = getattr(prev_node, "name", None)

			if prev_name is not None:
				if prev_name == "a":
					prev_node.extract()
				break

			if str(prev_node).strip():
				break

			prev_index -= 1

		return "".join(str(child) for child in body.contents).strip()

	# Fallback when bs4 is unavailable.
	return re.sub(
		r"^\s*<a\b[^>]*>.*?</a>\s*(?=<div\b)",
		"",
		text,
		count=1,
		flags=re.IGNORECASE | re.DOTALL,
	).strip()


def keep_only_body_content_starting_from_first_div(html: str) -> str:
	"""
	Keep only content inside <body> and remove html/head/body wrappers.
	Preserve all body content while removing the leading anchor before the first div.
	"""
	text = (html or "").strip()
	if not text:
		return text

	body_inner = extract_body_inner_html(text)
	body_inner = re.sub(r"</body\s*>", "", body_inner, flags=re.IGNORECASE)
	body_inner = re.sub(r"</html\s*>", "", body_inner, flags=re.IGNORECASE)
	body_inner = remove_anchor_before_first_div(body_inner)
	return body_inner.strip()


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def build_component_analysis_prompt(components: list[HelixComponent]) -> str:
	names = "\n".join(f"- {component.name}" for component in components[:120])
	return (
		"You are helping with backend migration planning.\n"
		"Analyze this list of available Helix components and return a compact summary of how to map "
		"standard HTML patterns to these components.\n"
		"Focus on: image, link, button, heading, accordion, table, form controls.\n\n"
		"Return plain text only.\n\n"
		f"Components:\n{names}"
	)


def build_fallback_component_analysis(components: list[HelixComponent], max_items: int = 20) -> str:
	"""Deterministic fallback when analysis model call is unavailable."""
	selected = [component.name for component in components[:max_items]]
	lines = [
		"Fallback component summary:",
		"- Prioritize mapping images, links, buttons, headings, forms, and accordions to Helix components.",
		"- Preserve content order and keep original semantic sections when no direct component mapping is clear.",
		"- Keep existing IDs; add missing IDs with project ID rule.",
		"- Use explicit closing tags for all custom components.",
		"- Available component examples (first items):",
	]
	lines.extend(f"  - {name}" for name in selected)
	return "\n".join(lines)


def collect_html_files(input_folder: Path) -> list[Path]:
	html_suffixes = {".html", ".htm"}
	files = [
		path
		for path in input_folder.rglob("*")
		if path.is_file() and not path.is_symlink() and path.suffix.lower() in html_suffixes
	]
	return sorted(files)


def extract_image_filename(path: str) -> str | None:
	if not path:
		return None

	clean = path.split("?")[0].split("#")[0]
	filename = clean.rsplit("/", 1)[-1].strip()
	if not filename:
		return None

	lower = filename.lower()
	if any(lower.endswith(ext) for ext in IMAGE_EXTENSIONS):
		return filename

	return None


def extract_image_sources_from_html(html_text: str) -> list[dict[str, str]]:
	text = html_text or ""
	results: list[dict[str, str]] = []
	seen_filenames: set[str] = set()

	if BeautifulSoup is not None:
		soup = BeautifulSoup(text, "html.parser")
		image_tags = []
		for tag in soup.find_all(True):
			tag_name = (tag.name or "").lower()
			if "img" in tag_name or "image" in tag_name:
				image_tags.append(tag)

		for tag in image_tags:
			for attr in ("src", "source", "data-src"):
				value = tag.get(attr)
				if value and isinstance(value, str):
					filename = extract_image_filename(value)
					if filename and filename not in seen_filenames:
						seen_filenames.add(filename)
						results.append(
							{
								"tag": str(tag.name),
								"attr": attr,
								"original_value": value,
								"filename": filename,
							}
						)

			srcset = tag.get("srcset")
			if srcset and isinstance(srcset, str):
				for entry in srcset.split(","):
					parts = entry.strip().split()
					if not parts:
						continue

					filename = extract_image_filename(parts[0])
					if filename and filename not in seen_filenames:
						seen_filenames.add(filename)
						results.append(
							{
								"tag": str(tag.name),
								"attr": "srcset",
								"original_value": parts[0],
								"filename": filename,
							}
						)

		return results

	for attr in ("src", "source", "data-src"):
		for match in re.finditer(rf"\b{attr}\s*=\s*([\"'])(.*?)\1", text, flags=re.IGNORECASE | re.DOTALL):
			value = (match.group(2) or "").strip()
			filename = extract_image_filename(value)
			if filename and filename not in seen_filenames:
				seen_filenames.add(filename)
				results.append(
					{
						"tag": "unknown",
						"attr": attr,
						"original_value": value,
						"filename": filename,
					}
				)

	for match in re.finditer(r"\bsrcset\s*=\s*([\"'])(.*?)\1", text, flags=re.IGNORECASE | re.DOTALL):
		srcset_value = match.group(2) or ""
		for entry in srcset_value.split(","):
			parts = entry.strip().split()
			if not parts:
				continue

			filename = extract_image_filename(parts[0])
			if filename and filename not in seen_filenames:
				seen_filenames.add(filename)
				results.append(
					{
						"tag": "unknown",
						"attr": "srcset",
						"original_value": parts[0],
						"filename": filename,
					}
				)

	return results


def search_and_get_webbuilder_permalink(page, filename: str) -> str | None:
	search_box = page.locator('xpath=//*[@id="file-search-text-input"]')
	search_box.click()
	for shortcut in ("Meta+A", "Control+A"):
		try:
			page.keyboard.press(shortcut)
			break
		except Exception:
			continue

	search_box.fill(filename)
	search_box.press("Enter")
	page.wait_for_timeout(WEBBUILDER_SEARCH_WAIT_MS)

	file_visible = page.locator(f"text={filename}")
	file_visible_count = file_visible.count()

	if file_visible_count > 1:
		logger.warning("DUPLICATE: '%s' appears multiple times in file manager - skipping.", filename)
		return None

	if file_visible_count == 0:
		logger.info("NOT FOUND: '%s' is not visible in file manager search results.", filename)
		return None

	rows = page.query_selector_all("table[data-v-c28095ba] tbody tr")
	row_index = -1

	for idx, row in enumerate(rows):
		first_column = row.query_selector("td:nth-child(1)")
		if first_column and first_column.inner_text().strip() == filename:
			row_index = idx + 1
			break

	if row_index == -1:
		logger.info("NOT FOUND: '%s' exact match not found in file manager table rows.", filename)
		return None

	page.locator(
		f'xpath=//*[@id="webbuilder-editor-content-wrapper"]'
		f"/div/div[1]/div/div/div[3]/div[2]/div/div/div[2]"
		f"/table/tbody/tr[{row_index}]/td[7]/div/span[2]/a"
	).click()
	page.wait_for_timeout(WEBBUILDER_MENU_WAIT_MS)

	permalink_ul_xpath = (
		f'//*[@id="webbuilder-editor-content-wrapper"]'
		f"/div/div[1]/div/div/div[3]/div[2]/div/div/div[2]"
		f"/table/tbody/tr[{row_index}]/td[7]/div/span[2]/div/div/ul"
	)
	permalink_li = page.locator(f"xpath={permalink_ul_xpath}").locator("li", has_text="Permalink")
	permalink_li.click()
	page.wait_for_timeout(WEBBUILDER_MENU_WAIT_MS)

	permalink = page.evaluate("navigator.clipboard.readText()")
	if permalink:
		return str(permalink).strip()

	logger.warning("Clipboard was empty after clicking Permalink for '%s'.", filename)
	return None


def login_to_webbuilder(page, username: str, password: str) -> None:
	logger.info("Navigating to Webbuilder dashboard...")
	page.goto(WEBBUILDER_DASHBOARD_URL)
	page.wait_for_timeout(WEBBUILDER_LOGIN_WAIT_MS)

	try:
		page.click('xpath=//*[@id="app"]/div[1]/div[1]/div[1]/div/div[2]/a')
		page.wait_for_timeout(WEBBUILDER_LOGIN_WAIT_MS)
	except Exception:
		logger.info("Login entry link was not clickable; continuing with current session state.")

	page.fill('xpath=//*[@id="username"]', username)
	page.fill('xpath=//*[@id="password"]', password)
	page.press('xpath=//*[@id="password"]', "Enter")
	page.wait_for_timeout(WEBBUILDER_MENU_WAIT_MS)
	logger.info("Webbuilder login flow completed.")


def goto_webbuilder_file_manager(page, instance_id: str) -> None:
	file_manager_url = (
		f"https://webbuilder.pfizer/builder/website/{instance_id}"
		f"?panel=left-sidebar-settings--file-manager"
	)
	logger.info("Navigating to Webbuilder File Manager: %s", file_manager_url)
	page.goto(file_manager_url)
	page.wait_for_timeout(WEBBUILDER_FILE_MANAGER_WAIT_MS)


def apply_permalink_updates_in_place(
	page,
	html_file: Path,
	permalink_cache: dict[str, str | None],
) -> tuple[int, int, bool]:
	html_text = html_file.read_text(encoding="utf-8", errors="ignore")
	image_sources = extract_image_sources_from_html(html_text)
	if not image_sources:
		return 0, 0, False

	replacements: dict[str, str] = {}
	for source_info in image_sources:
		filename = source_info["filename"]
		original_value = source_info["original_value"]

		if filename in permalink_cache:
			permalink = permalink_cache[filename]
			logger.info("PERMALINK CACHE: %s -> %s", filename, "FOUND" if permalink else "NOT FOUND")
		else:
			logger.info("Searching Webbuilder file manager for: %s", filename)
			permalink = search_and_get_webbuilder_permalink(page, filename)
			permalink_cache[filename] = permalink

		if permalink:
			replacements[original_value] = permalink

	if not replacements:
		return len(image_sources), 0, False

	updated_html = html_text
	for original_value, permalink in replacements.items():
		updated_html = updated_html.replace(original_value, permalink)

	if updated_html == html_text:
		return len(image_sources), len(replacements), False

	html_file.write_text(updated_html, encoding="utf-8")
	return len(image_sources), len(replacements), True


def preprocess_reference_html_permalinks(input_folder: Path, headless: bool = False) -> None:
	if sync_playwright is None:
		raise RuntimeError(
			"Playwright is required for permalink preprocessing. Install it with: pip install playwright"
		)

	username = (os.getenv(WEBBUILDER_USERNAME_ENV) or "").strip()
	password = (os.getenv(WEBBUILDER_PASSWORD_ENV) or "").strip()
	instance_id = (os.getenv(WEBBUILDER_INSTANCE_ID_ENV) or "").strip()

	if not username or not password or not instance_id:
		raise RuntimeError(
			f"{WEBBUILDER_USERNAME_ENV}, {WEBBUILDER_PASSWORD_ENV}, and {WEBBUILDER_INSTANCE_ID_ENV} "
			"must be set before permalink preprocessing can run."
		)

	html_files = collect_html_files(input_folder)
	if not html_files:
		logger.info("No HTML files found for permalink preprocessing under: %s", input_folder)
		return

	logger.info(
		"Starting Webbuilder permalink preprocessing for %d reference HTML files.",
		len(html_files),
	)

	total_images = 0
	total_permalinks = 0
	updated_files = 0
	permalink_cache: dict[str, str | None] = {}

	with sync_playwright() as playwright:
		browser = playwright.chromium.launch(headless=headless)
		try:
			context = browser.new_context()
			context.grant_permissions(["clipboard-read", "clipboard-write"])
			page = context.new_page()

			login_to_webbuilder(page, username=username, password=password)
			goto_webbuilder_file_manager(page, instance_id=instance_id)

			for index, html_file in enumerate(html_files, 1):
				rel = html_file.relative_to(input_folder)
				logger.info("Permalink preprocessing [%d/%d]: %s", index, len(html_files), rel)

				images_found, permalinks_found, updated = apply_permalink_updates_in_place(
					page=page,
					html_file=html_file,
					permalink_cache=permalink_cache,
				)
				total_images += images_found
				total_permalinks += permalinks_found
				if updated:
					updated_files += 1
		finally:
			browser.close()

	logger.info(
		"Permalink preprocessing completed. Files updated: %d/%d, image refs found: %d, permalinks mapped: %d",
		updated_files,
		len(html_files),
		total_images,
		total_permalinks,
	)


def split_html_into_chunks(input_html: str, max_chars: int = MAX_INPUT_CHARS_PER_CHUNK) -> list[str]:
	if len(input_html) <= max_chars:
		return [input_html]

	lines = input_html.splitlines(keepends=True)
	chunks: list[str] = []
	current = ""

	for line in lines:
		if current and len(current) + len(line) > max_chars:
			chunks.append(current)
			current = line
		else:
			current += line

	if current:
		chunks.append(current)

	if not chunks:
		return [input_html]

	return chunks


def split_body_html_into_chunks(body_html: str, max_chars: int = MAX_INPUT_CHARS_PER_CHUNK) -> list[str]:
	text = (body_html or "").strip()
	if not text:
		return [""]

	if len(text) <= max_chars:
		return [text]

	if BeautifulSoup is None:
		return split_html_into_chunks(text, max_chars=max_chars)

	soup = BeautifulSoup(f"<body>{text}</body>", "html.parser")
	body = soup.body
	if body is None:
		return split_html_into_chunks(text, max_chars=max_chars)

	nodes = [str(node).strip() for node in body.contents if str(node).strip()]
	if not nodes:
		return split_html_into_chunks(text, max_chars=max_chars)

	chunks: list[str] = []
	current = ""

	for node_html in nodes:
		if len(node_html) > max_chars:
			for piece in split_html_into_chunks(node_html, max_chars=max_chars):
				piece = piece.strip()
				if not piece:
					continue
				if current and len(current) + len(piece) + 2 > max_chars:
					chunks.append(current)
					current = piece
				else:
					current = f"{current}\n\n{piece}".strip() if current else piece
			continue

		if current and len(current) + len(node_html) + 2 > max_chars:
			chunks.append(current)
			current = node_html
		else:
			current = f"{current}\n\n{node_html}".strip() if current else node_html

	if current:
		chunks.append(current)

	return chunks if chunks else [text]


def build_conversion_user_prompt(
	file_relative_path: Path,
	input_html: str,
	selected_components: list[HelixComponent],
	component_analysis: str,
	analysis_char_limit: int = PROMPT_COMPONENT_ANALYSIS_CHAR_LIMIT,
	component_snippet_chars: int = PROMPT_COMPONENT_SNIPPET_CHAR_LIMIT,
) -> str:
	component_context = build_component_context(selected_components, max_snippet_chars=component_snippet_chars)
	return (
		f"File path: {file_relative_path}\n\n"
		"Component library summary (generated by model):\n"
		f"{component_analysis[:analysis_char_limit]}\n\n"
		"Relevant component templates from CSV:\n"
		f"{component_context}\n\n"
		"Now convert this HTML into Helix component based HTML while preserving context and text:\n"
		"- Keep original page meaning and content sequence.\n"
		"- Convert tags using best matching Helix components from the templates.\n"
		"- Keep or add IDs as required.\n"
		"- Ensure all custom components have explicit closing tags.\n"
		"- Return only full converted HTML.\n\n"
		"Input HTML:\n"
		f"{input_html}"
	)


# ---------------------------------------------------------------------------
# Folder conversion orchestration
# ---------------------------------------------------------------------------

def convert_single_file(
	token: str,
	model: str,
	temperature: float,
	base_url: str,
	include_copilot_endpoints: bool,
	file_path: Path,
	input_root: Path,
	output_root: Path,
	all_components: list[HelixComponent],
	component_analysis: str,
	max_components: int,
	show_model_output: bool,
) -> str:
	rel_path = file_path.relative_to(input_root)
	logger.info("Converting file: %s", rel_path)

	raw_input_html = file_path.read_text(encoding="utf-8", errors="ignore")
	if not raw_input_html.strip():
		logger.warning("Skipping empty HTML file: %s", rel_path)
		return base_url

	formatted_reference_html = format_reference_html_for_scanning(raw_input_html)
	reference_body_html = extract_body_inner_html(formatted_reference_html)
	conversion_source_html = reference_body_html if reference_body_html.strip() else formatted_reference_html

	prompt_component_limit = min(max_components, HARD_PROMPT_COMPONENT_LIMIT)
	if max_components > HARD_PROMPT_COMPONENT_LIMIT:
		logger.info(
			"Capping prompt components for %s from %d to %d to stay within model payload limits.",
			rel_path,
			max_components,
			prompt_component_limit,
		)

	selected_components = select_relevant_components(
		all_components,
		conversion_source_html,
		max_components=prompt_component_limit,
	)
	chunks = split_body_html_into_chunks(conversion_source_html, max_chars=MAX_INPUT_CHARS_PER_CHUNK)
	if len(chunks) > 1:
		logger.info(
			"Large HTML file %s (%d chars). Converting in %d chunks of up to %d chars.",
			rel_path,
			len(conversion_source_html),
			len(chunks),
			MAX_INPUT_CHARS_PER_CHUNK,
		)

	endpoint_in_use = base_url
	converted_parts: list[str] = []

	for idx, chunk_html in enumerate(chunks, 1):
		chunk_suffix = f" [chunk {idx}/{len(chunks)}]" if len(chunks) > 1 else ""
		messages = [
			{"role": "system", "content": SYSTEM_PROMPT},
			{
				"role": "user",
				"content": build_conversion_user_prompt(
					file_relative_path=rel_path,
					input_html=chunk_html,
					selected_components=selected_components,
					component_analysis=component_analysis,
					analysis_char_limit=PROMPT_COMPONENT_ANALYSIS_CHAR_LIMIT,
					component_snippet_chars=PROMPT_COMPONENT_SNIPPET_CHAR_LIMIT,
				),
			},
		]

		try:
			api_result = call_model_with_failover(
				token=token,
				model=model,
				messages=messages,
				temperature=temperature,
				start_base_url=endpoint_in_use,
				include_copilot_endpoints=include_copilot_endpoints,
			)
		except PayloadTooLargeError:
			logger.warning(
				"Payload too large for %s%s. Retrying with compact prompt.",
				rel_path,
				chunk_suffix,
			)
			compact_components = selected_components[: min(len(selected_components), 4)]
			compact_messages = [
				{"role": "system", "content": SYSTEM_PROMPT},
				{
					"role": "user",
					"content": build_conversion_user_prompt(
						file_relative_path=rel_path,
						input_html=chunk_html[:8000],
						selected_components=compact_components,
						component_analysis=component_analysis,
						analysis_char_limit=500,
						component_snippet_chars=350,
					),
				},
			]
			api_result = call_model_with_failover(
				token=token,
				model=model,
				messages=compact_messages,
				temperature=temperature,
				start_base_url=endpoint_in_use,
				include_copilot_endpoints=include_copilot_endpoints,
			)

		endpoint_in_use = api_result.endpoint_used

		if show_model_output:
			preview = strip_markdown_fences(api_result.response_text).strip()
			preview = preview[:1200] + ("..." if len(preview) > 1200 else "")
			print("\n" + "=" * 100)
			print(
				f"MODEL RESPONSE PREVIEW | FILE: {rel_path}{chunk_suffix} | MODEL: {model} | ENDPOINT: {api_result.endpoint_used}"
			)
			print("=" * 100)
			print(preview)
			print("=" * 100 + "\n")

		converted_part = post_process_html(api_result.response_text)
		if "<" not in converted_part or ">" not in converted_part:
			logger.warning(
				"Model output did not look like HTML for %s%s. Falling back to original chunk.",
				rel_path,
				chunk_suffix,
			)
			converted_part = chunk_html

		converted_parts.append(converted_part)

	converted_html = "\n\n".join(converted_parts)
	converted_html = ensure_body_content_coverage(reference_body_html, converted_html)
	converted_html = keep_only_body_content_starting_from_first_div(converted_html)

	out_file = output_root / rel_path
	out_file.parent.mkdir(parents=True, exist_ok=True)
	out_file.write_text(converted_html, encoding="utf-8")
	logger.info("Wrote converted file: %s", out_file)
	return endpoint_in_use


def copy_non_html_assets(input_root: Path, output_root: Path) -> None:
	for source_path in input_root.rglob("*"):
		if not source_path.is_file():
			continue
		if source_path.suffix.lower() in {".html", ".htm"}:
			continue
		relative = source_path.relative_to(input_root)
		destination = output_root / relative
		destination.parent.mkdir(parents=True, exist_ok=True)
		shutil.copy2(source_path, destination)


def choose_model(explicit_model: str | None, discovered_models: list[str]) -> str:
	if explicit_model:
		return explicit_model
	if discovered_models:
		for preferred in MODEL_OPTIONS:
			if preferred in discovered_models:
				return preferred
	return DEFAULT_MODEL


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description=(
			"Convert a folder of HTML files to Helix-style HTML using GitHub Copilot/GitHub Models. "
			"Output folder mirrors input folder structure."
		)
	)
	parser.add_argument(
		"--input-folder",
		required=True,
		type=Path,
		help="Folder containing source HTML files (searched recursively).",
	)
	parser.add_argument(
		"--output-folder",
		required=True,
		type=Path,
		help="Folder where converted HTML files will be written.",
	)
	parser.add_argument(
		"--components-csv",
		required=True,
		type=Path,
		help="CSV with columns: Component Name, HTML Content.",
	)
	parser.add_argument(
		"--model",
		default=DEFAULT_MODEL,
		help=(
			"Model id to use (for example: gpt-4o, gpt-4o-mini, claude-sonnet-4-6). "
			"Use --list-models to view endpoint models."
		),
	)
	parser.add_argument(
		"--temperature",
		type=float,
		default=DEFAULT_TEMPERATURE,
		help="Sampling temperature for generation. Default: 0.4",
	)
	parser.add_argument(
		"--max-components-per-file",
		type=int,
		default=24,
		help="Max component templates to include in each file-conversion prompt.",
	)
	parser.add_argument(
		"--list-models",
		action="store_true",
		help="List available models from the active endpoint and exit.",
	)
	parser.add_argument(
		"--copy-non-html",
		action="store_true",
		help="Also copy non-HTML files (images/css/js/etc.) to output folder.",
	)
	parser.add_argument(
		"--show-model-output",
		action="store_true",
		help="Print model response previews while converting files.",
	)
	parser.add_argument(
		"--analysis-cache-file",
		type=Path,
		help="Optional file path to read/write cached component analysis text.",
	)
	parser.add_argument(
		"--skip-model-analysis",
		action="store_true",
		help="Skip the model analysis call and use a deterministic fallback summary.",
	)
	parser.add_argument(
		"--skip-existing",
		action="store_true",
		help="Skip conversion when the destination HTML file already exists.",
	)
	parser.add_argument(
		"--skip-permalink-preprocess",
		action="store_true",
		help="Skip Webbuilder permalink preprocessing on input HTML files before model conversion.",
	)
	parser.add_argument(
		"--permalink-headless",
		action="store_true",
		help="Run the Webbuilder permalink preprocessing browser in headless mode.",
	)
	return parser.parse_args()


def main() -> None:
	load_dotenv()
	args = parse_args()

	input_folder: Path = args.input_folder.resolve()
	output_folder: Path = args.output_folder.resolve()
	components_csv: Path = args.components_csv.resolve()
	temperature: float = float(args.temperature)
	max_components: int = max(1, int(args.max_components_per_file))

	if not input_folder.exists() or not input_folder.is_dir():
		raise FileNotFoundError(f"Input folder does not exist or is not a directory: {input_folder}")

	if args.skip_permalink_preprocess:
		logger.info("Skipping permalink preprocessing by request.")
	else:
		preprocess_reference_html_permalinks(
			input_folder=input_folder,
			headless=bool(args.permalink_headless),
		)

	token, use_copilot_endpoints = get_token()
	active_base_url = normalize_base_url(os.getenv("API_BASE_URL", GITHUB_MODELS_BASE_URL))
	client = build_client(token, active_base_url)
	if not use_copilot_endpoints:
		logger.info("Using %s token; Copilot API endpoints will be skipped during failover.", PAT_TOKEN_ENV)

	discovered_models = fetch_models(client)
	if args.list_models:
		if discovered_models:
			print("Available models:")
			for model_id in discovered_models:
				print(f"- {model_id}")
		else:
			print("Could not fetch models from endpoint. You can still pass --model manually.")
			print("Suggested options:")
			for model_id in MODEL_OPTIONS:
				print(f"- {model_id}")
		return

	selected_model = choose_model(args.model, discovered_models)
	logger.info("Selected model: %s", selected_model)
	logger.info("Selected endpoint: %s", active_base_url)

	all_components = load_components(components_csv)
	analysis_cache_file: Path | None = args.analysis_cache_file.resolve() if args.analysis_cache_file else None

	# Requirement: model also analyzes the CSV component catalog.
	component_analysis: str
	analysis_source: str

	if analysis_cache_file and analysis_cache_file.exists():
		component_analysis = analysis_cache_file.read_text(encoding="utf-8", errors="ignore").strip()
		analysis_source = f"cache:{analysis_cache_file}"
	elif args.skip_model_analysis:
		component_analysis = build_fallback_component_analysis(all_components)
		analysis_source = "fallback"
	else:
		analysis_prompt = build_component_analysis_prompt(all_components)
		analysis_messages = [
			{
				"role": "system",
				"content": "You are an expert web-component migration assistant.",
			},
			{"role": "user", "content": analysis_prompt},
		]
		try:
			analysis_result = call_model_with_failover(
				token=token,
				model=selected_model,
				messages=analysis_messages,
				temperature=temperature,
				start_base_url=active_base_url,
				include_copilot_endpoints=use_copilot_endpoints,
			)
			active_base_url = analysis_result.endpoint_used
			component_analysis = strip_markdown_fences(analysis_result.response_text)
			analysis_source = f"model:{analysis_result.endpoint_used}"
		except Exception as analysis_exc:
			logger.warning(
				"Component analysis call failed (%s). Falling back to deterministic summary.",
				analysis_exc,
			)
			component_analysis = build_fallback_component_analysis(all_components)
			analysis_source = "fallback-after-error"

	if analysis_cache_file and component_analysis:
		analysis_cache_file.parent.mkdir(parents=True, exist_ok=True)
		analysis_cache_file.write_text(component_analysis, encoding="utf-8")

	print("\n" + "#" * 100)
	print(f"COMPONENT ANALYSIS RESPONSE | SOURCE: {analysis_source}")
	print("#" * 100)
	print(component_analysis[:2500] + ("..." if len(component_analysis) > 2500 else ""))
	print("#" * 100 + "\n")

	html_files = collect_html_files(input_folder)
	if not html_files:
		raise RuntimeError(f"No .html/.htm files found under input folder: {input_folder}")

	logger.info("Found %d HTML files to convert", len(html_files))
	output_folder.mkdir(parents=True, exist_ok=True)
	logger.info("Stable endpoint for conversion starts as: %s", active_base_url)

	success_count = 0
	attempted_count = 0
	skipped_count = 0
	failed_files: list[str] = []

	for html_file in html_files:
		rel = html_file.relative_to(input_folder)
		if args.skip_existing:
			out_file = output_folder / rel
			if out_file.exists() and out_file.stat().st_size > 0:
				skipped_count += 1
				logger.info("Skipping existing converted file: %s", rel)
				continue

		attempted_count += 1
		try:
			active_base_url = convert_single_file(
				token=token,
				model=selected_model,
				temperature=temperature,
				base_url=active_base_url,
				include_copilot_endpoints=use_copilot_endpoints,
				file_path=html_file,
				input_root=input_folder,
				output_root=output_folder,
				all_components=all_components,
				component_analysis=component_analysis,
				max_components=max_components,
				show_model_output=args.show_model_output,
			)
			success_count += 1
		except Exception as file_exc:
			rel_str = str(rel)
			failed_files.append(rel_str)
			logger.error("Failed converting file %s: %s", rel_str, file_exc)
			continue

	if args.copy_non_html:
		logger.info("Copying non-HTML assets...")
		copy_non_html_assets(input_folder, output_folder)

	logger.info(
		"Conversion completed. Success: %d / %d attempted (total source: %d, skipped existing: %d), Failed: %d",
		success_count,
		attempted_count,
		len(html_files),
		skipped_count,
		len(failed_files),
	)
	if failed_files:
		preview = ", ".join(failed_files[:10])
		logger.warning("Failed files (first %d): %s", min(len(failed_files), 10), preview)
	logger.info("Final stable endpoint used: %s", active_base_url)
	logger.info("Output folder: %s", output_folder)


if __name__ == "__main__":
	try:
		main()
	except Exception as exc:
		logger.error("Fatal error: %s", exc)
		sys.exit(1)
