"""
================================================================================
LEAD SNIPER — TEMPLATE LOADER (Phase 4 / Roadmap #5)
================================================================================
Responsibility:
    Parse .antigravity_env/prompt_templates.md, cache the result as JSON, and
    expose a load_templates() function for the agents to consume. Implements
    a mtime-based stale-check so edits to the markdown invalidate the cache
    automatically without restart.

Architecture Reference:
    .antigravity_env/agents.md         — Multi-Agent system contract
    .antigravity_env/custom_rules.md   — Core directives (Zero-Cost, Self-Healing)
    .antigravity_env/decisions.md      — ADR-011 (Loader Contract — pending)
    .antigravity_env/prompt_templates.md — The single source of truth (markdown)

Design Principles (per custom_rules.md):
    - ZERO-COST: Standard library only (re, json, os, pathlib, time, logging).
    - SELF-HEALING: Cache corruption triggers automatic regeneration from
      markdown. Missing markdown raises TemplateNotFoundError (caller handles).
    - SURGICAL: This module is a leaf — no imports from other project files.
      It can be tested independently of agents/UI/orchestrator.
    - SELLABLE QUALITY: Full structured logging, schema validation, atomic
      cache writes (write-temp-then-rename) to prevent partial-write corruption.

Usage:
    from template_loader import load_templates, get_template, TemplateNotFoundError

    # Get all active templates (parses or reads cache):
    templates = load_templates()
    # → {"hvac_contractor": {...}, "career_coach": {...}}

    # Get a specific template:
    hvac = get_template("hvac_contractor")
    system_prompt_p1 = hvac["system_prompt_phase1"]

    # Force re-read (e.g., after editing the markdown mid-session):
    templates = load_templates(force_reload=True)

Author:     Lead Architect via Antigravity Engine
Version:    1.0.0  (Phase 4 / Roadmap #5 / BUG-004 fix in progress)
================================================================================
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

# ──────────────────────────────────────────────────────────────────────────────
# LOGGING CONFIGURATION
# Mirrors the per-agent logging pattern. Each module owns its own logger name.
# ──────────────────────────────────────────────────────────────────────────────
LOG_FILE = "template_loader.log"

# Use module-level logger but DO NOT call logging.basicConfig() — that is
# owned by the orchestrator (main.py) and the UI (app_ui.py). Calling it
# here would override their handlers. Just attach a file handler if no
# root config exists yet.
logger = logging.getLogger("TEMPLATE_LOADER")
if not logger.handlers:
    _file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    _file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(_file_handler)
    logger.setLevel(logging.INFO)


# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────

# Default paths — overridable via load_templates() parameters for testing.
DEFAULT_MARKDOWN_PATH = ".antigravity_env/prompt_templates.md"
DEFAULT_CACHE_PATH    = ".antigravity_env/prompt_templates.cache.json"

# Required fields per template (matches the schema in prompt_templates.md).
# A template missing any of these is considered malformed and is rejected.
REQUIRED_FIELDS = (
    "id",
    "display_name",
    "status",
    "target_industry_phrase",
    "keywords",
    "system_prompt_phase1",
    "user_prompt_phase1",
    "required_evidence",
    "system_prompt_phase2",
    "user_prompt_phase2",
    "pitch_rules",
)

# Module-level cache — populated on first load_templates() call within a process.
# Reset to None to force a re-load. Keyed by markdown path so multi-path tests work.
_in_process_cache: dict = {}


# ──────────────────────────────────────────────────────────────────────────────
# EXCEPTION CLASSES
# ──────────────────────────────────────────────────────────────────────────────

class TemplateLoaderError(Exception):
    """Base exception for all loader failures."""
    pass


class TemplateNotFoundError(TemplateLoaderError):
    """Raised when a requested template id does not exist in the registry."""
    pass


class TemplateMalformedError(TemplateLoaderError):
    """Raised when a template is missing required fields or has invalid structure."""
    pass


class MarkdownSourceMissingError(TemplateLoaderError):
    """Raised when prompt_templates.md cannot be found or read."""
    pass


# ──────────────────────────────────────────────────────────────────────────────
# MARKDOWN PARSING
# Parses the prompt_templates.md format defined in Prompt 12 of Phase 2.
# Each Active template is a markdown section starting with '### TEMPLATE — Name'
# followed by '- **id:** value' lines, with code blocks for prompts.
# ──────────────────────────────────────────────────────────────────────────────

def _extract_active_section(md_text: str) -> str:
    """
    Pull out only the 'Active Templates' section from the full markdown file.
    We deliberately ignore the 'Reserved Slots' and 'Deprecated Templates'
    sections — those describe planned/retired templates, not loadable ones.

    Returns the substring between '## Active Templates' and the next '## ' header.
    Returns empty string if the section is not found.
    """
    match = re.search(
        r"^## Active Templates\s*$(.*?)^## ",
        md_text,
        flags=re.DOTALL | re.MULTILINE,
    )
    if match:
        return match.group(1)
    # Fallback: section runs to end of file (no following ## header).
    match = re.search(
        r"^## Active Templates\s*$(.*)",
        md_text,
        flags=re.DOTALL | re.MULTILINE,
    )
    return match.group(1) if match else ""


def _split_into_template_blocks(active_section: str) -> list[str]:
    """
    Split the Active Templates section into individual template blocks.
    Each block starts with '### TEMPLATE — ' and runs until the next '### TEMPLATE — '
    or end of section. Returns a list of block strings (each begins with '### TEMPLATE').
    """
    parts = re.split(r"^(### TEMPLATE — )", active_section, flags=re.MULTILINE)
    blocks = []
    # re.split with a captured group returns: [pre, sep1, content1, sep2, content2, ...]
    # Pair sep+content back together.
    for i in range(1, len(parts), 2):
        if i + 1 < len(parts):
            blocks.append(parts[i] + parts[i + 1])
    return blocks


def _extract_field(block: str, field_name: str) -> Optional[str]:
    """
    Extract a simple inline field like '- **id:** `value`' or '- **status:** Active'.
    Returns the trimmed value, or None if the field is missing.
    Strips backticks and surrounding whitespace.
    """
    pattern = rf"^- \*\*{re.escape(field_name)}:\*\*\s*(.+?)$"
    match = re.search(pattern, block, flags=re.MULTILINE)
    if not match:
        return None
    value = match.group(1).strip()
    # Strip backticks if the entire value is wrapped in them.
    if value.startswith("`") and value.endswith("`"):
        value = value[1:-1]
    return value


def _extract_code_block(block: str, label: str) -> Optional[str]:
    """
    Extract the contents of the first ```...``` code block that appears AFTER
    a line containing the bold label like '**system_prompt_phase1:**'.
    Returns the code block contents (without the fences), or None if not found.

    The markdown format from Prompt 12 looks like:
        **system_prompt_phase1:**
        ```
        You are an expert ...
        ```
    """
    label_escaped = re.escape(label)
    pattern = rf"\*\*{label_escaped}:\*\*\s*\n```\s*\n(.*?)\n```"
    match = re.search(pattern, block, flags=re.DOTALL)
    return match.group(1) if match else None


def _extract_required_evidence(block: str) -> Optional[str]:
    """
    Extract the 'required_evidence' field, which is a free-form sentence
    rather than a code block. Format: '**required_evidence:** Page content...'.
    """
    pattern = r"\*\*required_evidence:\*\*\s*(.+?)(?=\n\n|\n####|\n---|\Z)"
    match = re.search(pattern, block, flags=re.DOTALL)
    return match.group(1).strip() if match else None


def _extract_pitch_rules(block: str) -> Optional[list]:
    """
    Extract the 'pitch_rules' bullet list. Format:
        **pitch_rules:**
        - Rule one.
        - Rule two.
    Returns a list of rule strings (without the leading '- '), or None if not found.
    """
    pattern = r"\*\*pitch_rules:\*\*\s*\n((?:- .+\n?)+)"
    match = re.search(pattern, block)
    if not match:
        return None
    raw = match.group(1)
    rules = [
        line.lstrip("- ").strip()
        for line in raw.splitlines()
        if line.strip().startswith("- ")
    ]
    return rules if rules else None


def parse_markdown_templates(md_path: str = DEFAULT_MARKDOWN_PATH) -> dict:
    """
    Parse the markdown registry file and return a dict keyed by template id.

    Only Active templates are included. Reserved slots and Deprecated templates
    are ignored at parse time (they're documentation, not loadable runtime data).

    Args:
        md_path: Path to prompt_templates.md. Defaults to .antigravity_env/prompt_templates.md.

    Returns:
        dict[str, dict]: Mapping from template id (str) to template dict.
        Each template dict has all REQUIRED_FIELDS populated.

    Raises:
        MarkdownSourceMissingError: If the file does not exist or cannot be read.
        TemplateMalformedError: If a parsed template is missing required fields.
    """
    if not os.path.exists(md_path):
        msg = f"Markdown source not found at: {md_path}"
        logger.critical(msg)
        raise MarkdownSourceMissingError(msg)

    try:
        with open(md_path, mode="r", encoding="utf-8") as f:
            md_text = f.read()
    except OSError as e:
        msg = f"Could not read markdown source {md_path}: {e}"
        logger.critical(msg)
        raise MarkdownSourceMissingError(msg) from e

    active_section = _extract_active_section(md_text)
    if not active_section.strip():
        logger.warning(
            "Markdown file %s has no 'Active Templates' section or it is empty. "
            "Returning empty registry.",
            md_path,
        )
        return {}

    blocks = _split_into_template_blocks(active_section)
    logger.info("Found %d template block(s) in Active Templates section.", len(blocks))

    registry: dict = {}
    for block in blocks:
        try:
            template = {
                "id":                     _extract_field(block, "id"),
                "display_name":           _extract_field(block, "display_name"),
                "status":                 _extract_field(block, "status"),
                "target_industry_phrase": _extract_field(block, "target_industry_phrase"),
                "keywords":               _extract_field(block, "keywords"),
                "system_prompt_phase1":   _extract_code_block(block, "system_prompt_phase1"),
                "user_prompt_phase1":     _extract_code_block(block, "user_prompt_phase1"),
                "required_evidence":      _extract_required_evidence(block),
                "system_prompt_phase2":   _extract_code_block(block, "system_prompt_phase2"),
                "user_prompt_phase2":     _extract_code_block(block, "user_prompt_phase2"),
                "pitch_rules":            _extract_pitch_rules(block),
            }

            validate_template(template)

            # Skip non-Active templates defensively (in case someone moves a
            # block here without updating the status field).
            if template["status"] != "Active":
                logger.info(
                    "Skipping template '%s' — status is '%s' (only 'Active' is loaded).",
                    template["id"], template["status"],
                )
                continue

            registry[template["id"]] = template
            logger.info(
                "Loaded template: id=%s display_name=%s",
                template["id"], template["display_name"],
            )

        except TemplateMalformedError as e:
            logger.error(
                "Skipping malformed template block. Error: %s. Block snippet: %s",
                e, block[:200],
            )
            continue
        except Exception as e:
            logger.error(
                "Unexpected error parsing template block: %s. Block snippet: %s",
                e, block[:200],
            )
            continue

    logger.info("Markdown parse complete. %d Active template(s) loaded.", len(registry))
    return registry


# ──────────────────────────────────────────────────────────────────────────────
# SCHEMA VALIDATION
# ──────────────────────────────────────────────────────────────────────────────

def validate_template(template: dict) -> None:
    """
    Verify a parsed template has every required field with a non-empty value.

    Raises:
        TemplateMalformedError: If any required field is missing or empty.
    """
    missing = [
        field for field in REQUIRED_FIELDS
        if not template.get(field)
    ]
    if missing:
        raise TemplateMalformedError(
            f"Template (id={template.get('id', 'UNKNOWN')}) is missing required fields: {missing}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# CACHE MANAGEMENT (Path C — hybrid markdown + JSON cache)
# ──────────────────────────────────────────────────────────────────────────────

def is_cache_stale(
    md_path: str = DEFAULT_MARKDOWN_PATH,
    cache_path: str = DEFAULT_CACHE_PATH,
) -> bool:
    """
    Return True if the cache is missing or older than the markdown source.

    Stale-check uses os.path.getmtime() on both files. If either file is
    missing, we treat it as stale (forcing regeneration / surfacing the
    markdown error to the caller).
    """
    if not os.path.exists(cache_path):
        return True
    if not os.path.exists(md_path):
        # Markdown gone — cache is technically intact, but we should not
        # silently use a stale cache when source is missing. Let the caller
        # surface the MarkdownSourceMissingError.
        return True
    try:
        md_mtime    = os.path.getmtime(md_path)
        cache_mtime = os.path.getmtime(cache_path)
        return md_mtime > cache_mtime
    except OSError as e:
        logger.warning("mtime check failed: %s. Treating cache as stale.", e)
        return True


def regenerate_cache(
    md_path: str = DEFAULT_MARKDOWN_PATH,
    cache_path: str = DEFAULT_CACHE_PATH,
) -> dict:
    """
    Re-parse the markdown and write the result to the JSON cache.

    Uses an atomic write pattern: write to <cache_path>.tmp, then os.replace()
    to the final path. This prevents partial-write corruption if the process
    is killed mid-write.

    Args:
        md_path:    Path to prompt_templates.md (source of truth).
        cache_path: Path to prompt_templates.cache.json (auto-generated).

    Returns:
        dict: The parsed registry that was just written.

    Raises:
        MarkdownSourceMissingError: If the markdown source is unreadable.
        OSError: If the cache cannot be written (disk full, permission denied, etc.).
    """
    registry = parse_markdown_templates(md_path)

    cache_dir = os.path.dirname(cache_path)
    if cache_dir:
        Path(cache_dir).mkdir(parents=True, exist_ok=True)

    tmp_path = cache_path + ".tmp"
    try:
        with open(tmp_path, mode="w", encoding="utf-8") as f:
            json.dump(
                {
                    "_meta": {
                        "source_path":         md_path,
                        "source_mtime":        os.path.getmtime(md_path),
                        "cache_format_version": 1,
                    },
                    "templates": registry,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )
            f.flush()
            os.fsync(f.fileno())  # Force write to disk before rename
        os.replace(tmp_path, cache_path)
        logger.info(
            "Cache regenerated: %s (%d template(s)).",
            cache_path, len(registry),
        )
    except OSError as e:
        logger.error("Failed to write cache to %s: %s", cache_path, e)
        # Clean up the tmp file if it's still hanging around.
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        raise

    return registry


def _read_cache(cache_path: str = DEFAULT_CACHE_PATH) -> Optional[dict]:
    """
    Read the JSON cache and return the templates dict.

    Self-healing: on cache corruption (invalid JSON, missing top-level keys,
    schema mismatch), returns None so the caller can regenerate. Never raises.
    """
    if not os.path.exists(cache_path):
        return None

    try:
        with open(cache_path, mode="r", encoding="utf-8") as f:
            cache_data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Cache at %s is corrupt or unreadable: %s", cache_path, e)
        return None

    if not isinstance(cache_data, dict):
        logger.warning("Cache at %s has unexpected top-level type.", cache_path)
        return None

    templates = cache_data.get("templates")
    if not isinstance(templates, dict):
        logger.warning("Cache at %s missing 'templates' dict.", cache_path)
        return None

    # Defensively re-validate every entry so a manually-edited cache (which
    # users should never do, but might) doesn't poison the agents.
    for tid, template in list(templates.items()):
        try:
            validate_template(template)
        except TemplateMalformedError as e:
            logger.warning(
                "Cache entry %s is malformed: %s. Discarding cache, regenerating.",
                tid, e,
            )
            return None

    return templates


# ──────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ──────────────────────────────────────────────────────────────────────────────

def load_templates(
    md_path: str = DEFAULT_MARKDOWN_PATH,
    cache_path: str = DEFAULT_CACHE_PATH,
    force_reload: bool = False,
) -> dict:
    """
    Load the template registry. Stale-checks the cache against the markdown
    source and regenerates if needed.

    Args:
        md_path:      Path to prompt_templates.md.
        cache_path:   Path to prompt_templates.cache.json.
        force_reload: If True, bypass all caches (in-process and on-disk) and
                      re-parse the markdown. Useful for hot-reloading during dev.

    Returns:
        dict[str, dict]: Mapping from template id to template dict.

    Raises:
        MarkdownSourceMissingError: If the markdown is missing AND the cache
                                    is also missing or unusable.
    """
    global _in_process_cache
    cache_key = (md_path, cache_path)

    # Layer 1: in-process cache (fastest path).
    if not force_reload and cache_key in _in_process_cache:
        return _in_process_cache[cache_key]

    # Layer 2: on-disk JSON cache (fast path, survives process restart).
    if not force_reload and not is_cache_stale(md_path, cache_path):
        cached = _read_cache(cache_path)
        if cached is not None:
            _in_process_cache[cache_key] = cached
            logger.info(
                "Templates loaded from on-disk cache: %s (%d template(s)).",
                cache_path, len(cached),
            )
            return cached
        else:
            logger.info("On-disk cache unusable. Falling through to regeneration.")

    # Layer 3: regenerate from markdown (slow path, source of truth).
    try:
        registry = regenerate_cache(md_path, cache_path)
        _in_process_cache[cache_key] = registry
        return registry
    except OSError:
        # Cache write failed — but we still have the parsed registry from
        # the failed regenerate_cache() call's parse step. Try parsing
        # directly so the caller still gets templates even if cache is unwritable.
        logger.warning("Cache write failed; serving from in-memory parse only.")
        registry = parse_markdown_templates(md_path)
        _in_process_cache[cache_key] = registry
        return registry


def get_template(
    template_id: str,
    md_path: str = DEFAULT_MARKDOWN_PATH,
    cache_path: str = DEFAULT_CACHE_PATH,
) -> dict:
    """
    Get a single template by its id.

    Args:
        template_id: The template id (e.g., 'hvac_contractor', 'career_coach').
        md_path:     Path to prompt_templates.md.
        cache_path:  Path to prompt_templates.cache.json.

    Returns:
        dict: The full template dict.

    Raises:
        TemplateNotFoundError: If template_id is not in the registry.
        MarkdownSourceMissingError: If the markdown source is unreadable
                                    AND the cache cannot serve the request.
    """
    registry = load_templates(md_path=md_path, cache_path=cache_path)
    if template_id not in registry:
        available = sorted(registry.keys())
        raise TemplateNotFoundError(
            f"Template id '{template_id}' not found in registry. "
            f"Available templates: {available}"
        )
    return registry[template_id]


def list_templates(
    md_path: str = DEFAULT_MARKDOWN_PATH,
    cache_path: str = DEFAULT_CACHE_PATH,
) -> list[tuple]:
    """
    Return a list of (id, display_name) tuples for all Active templates.
    Useful for populating UI dropdowns without exposing internal template structure.
    """
    registry = load_templates(md_path=md_path, cache_path=cache_path)
    return [(tid, t["display_name"]) for tid, t in registry.items()]


# ──────────────────────────────────────────────────────────────────────────────
# STANDALONE ENTRY POINT — Direct test runner.
# Usage: python template_loader.py
# Prints the parsed registry as JSON for inspection.
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    print("── Template Loader Smoke Test ──")
    try:
        templates = load_templates(force_reload=True)
        print(f"\n✓ Loaded {len(templates)} Active template(s):")
        for tid, t in templates.items():
            print(f"  • {tid:30s} → {t['display_name']}")
        print("\n── First template (full dict) ──")
        if templates:
            first_id = next(iter(templates))
            print(json.dumps(templates[first_id], indent=2, ensure_ascii=False)[:1500] + "...")
    except TemplateLoaderError as e:
        print(f"\n✗ Loader error: {e}")
        sys.exit(1)
