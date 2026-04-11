"""
================================================================================
LEAD SNIPER — AGENT 1: INGESTOR
================================================================================
Responsibility:
    Read raw CSV lead data, sanitize all inputs, validate critical fields, and
    return a clean, structured list of lead dictionaries ready for downstream
    processing by AGENT 2 (Scout).

Architecture Reference:
    .antigravity_env/agents.md   — Multi-Agent system contract
    .antigravity_env/custom_rules.md — Core directives (Zero-Cost, Self-Healing)

Design Principles (per custom_rules.md):
    - ZERO-COST: Uses only Python standard library (csv, json, logging, os).
    - SELF-HEALING: All I/O wrapped in try/except with detailed error logging.
    - SURGICAL: This file handles ONLY ingestion. No scraping, no scoring.
    - SELLABLE QUALITY: Enterprise-grade comments, modular class design,
      importable by the main orchestrator without modification.

Author:     Lead Architect via Antigravity Engine
Version:    1.0.0
================================================================================
"""

import csv
import json
import logging
import os
from typing import Optional

# ──────────────────────────────────────────────────────────────────────────────
# LOGGING CONFIGURATION
# Outputs to both the console and a persistent log file for full auditability.
# Log format includes timestamp, level, and module name for traceability.
# ──────────────────────────────────────────────────────────────────────────────
LOG_FILE = "agent1_ingestor.log"

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger("AGENT_1_INGESTOR")


# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# Expected CSV schema. Any column not in this list will be ignored gracefully.
# ──────────────────────────────────────────────────────────────────────────────
EXPECTED_HEADERS = [
    "Name",
    "Email",
    "Role",
    "Company",
    "Industry",
    "Location",
    "LinkedIn",
    "Website",
]

# The Website field must begin with one of these schemes to be considered valid.
VALID_URL_PREFIXES = ("http://", "https://")


# ──────────────────────────────────────────────────────────────────────────────
# CLASS: LeadIngestor
# ──────────────────────────────────────────────────────────────────────────────
class LeadIngestor:
    """
    AGENT 1 — Ingestor

    Reads a CSV file of raw leads, validates each row against the expected
    schema, and returns a clean list of lead dictionaries. Invalid or
    incomplete rows are skipped and logged — never silently dropped.

    Usage:
        ingestor = LeadIngestor()
        leads = ingestor.ingest_csv("leads.csv")

    Returns:
        A list of dicts, each representing one validated lead.
        Example:
        [
            {
                "Name": "Jane Doe",
                "Email": "jane@example.com",
                "Role": "CEO",
                "Company": "Acme Corp",
                "Industry": "SaaS",
                "Location": "New York, NY",
                "LinkedIn": "https://linkedin.com/in/janedoe",
                "Website": "https://acme.com"
            },
            ...
        ]
    """

    def __init__(self):
        logger.info("LeadIngestor initialized. Ready to process CSV input.")

    # ──────────────────────────────────────────────────────────────────────────
    # PRIVATE HELPER: _sanitize_row
    # Strip leading/trailing whitespace from all string values in a row dict.
    # ──────────────────────────────────────────────────────────────────────────
    def _sanitize_row(self, row: dict) -> dict:
        """
        Strip whitespace from all field values. Returns a new clean dict.
        This prevents ghost failures caused by spaces in URLs or emails.
        """
        return {key: (value.strip() if isinstance(value, str) else value)
                for key, value in row.items()}

    # ──────────────────────────────────────────────────────────────────────────
    # PRIVATE HELPER: _is_valid_website
    # A lightweight URL validator using no external libraries.
    # ──────────────────────────────────────────────────────────────────────────
    def _is_valid_website(self, url: Optional[str]) -> bool:
        """
        Returns True only if the URL is a non-empty string that starts with
        'http://' or 'https://'. Does NOT perform a live reachability check —
        that is AGENT 2's (Scout's) responsibility.
        """
        if not url:
            return False
        return url.startswith(VALID_URL_PREFIXES)

    # ──────────────────────────────────────────────────────────────────────────
    # PRIVATE HELPER: _validate_headers
    # Warn if any expected headers are missing from the CSV.
    # ──────────────────────────────────────────────────────────────────────────
    def _validate_headers(self, fieldnames: list) -> None:
        """
        Compares the CSV's actual headers against the expected schema.
        Logs a warning for each missing column so the operator knows exactly
        what data quality issues exist — without halting execution.
        """
        if fieldnames is None:
            logger.warning("CSV has no detectable headers.")
            return

        normalized_fields = [f.strip() for f in fieldnames]
        missing = [h for h in EXPECTED_HEADERS if h not in normalized_fields]

        if missing:
            logger.warning(
                "CSV is missing expected column(s): %s. "
                "Affected rows will have None values for these fields.",
                missing,
            )
        else:
            logger.info("All expected headers are present. Schema check passed.")

    # ──────────────────────────────────────────────────────────────────────────
    # PUBLIC METHOD: ingest_csv
    # Core ingestion pipeline. Self-healing by design.
    # ──────────────────────────────────────────────────────────────────────────
    def ingest_csv(self, file_path: str) -> list[dict]:
        """
        Main ingestion method. Reads the CSV at `file_path`, validates each
        row, and returns a clean list of lead dicts.

        Self-Healing Behaviour (per custom_rules.md — Directive 4):
            - Missing file       → logs CRITICAL, returns empty list (no crash).
            - Permission denied  → logs CRITICAL, returns empty list.
            - Malformed row      → logs WARNING, skips row, continues.
            - Missing Website    → logs WARNING with lead name, skips row.
            - Empty CSV          → logs WARNING, returns empty list.
            - Unexpected error   → logs CRITICAL with full traceback, returns [].

        Args:
            file_path (str): Absolute or relative path to the CSV file.

        Returns:
            list[dict]: A list of validated lead dictionaries. May be empty.
        """
        validated_leads = []
        skipped_count = 0
        processed_count = 0

        logger.info("=" * 60)
        logger.info("AGENT 1 — Starting ingestion for: %s", file_path)
        logger.info("=" * 60)

        # ── SELF-HEALING GUARD: File existence check ──────────────────────────
        if not os.path.exists(file_path):
            logger.critical(
                "CRITICAL — File not found: '%s'. "
                "Verify the path and retry. Returning empty list.",
                file_path,
            )
            return []

        # ── SELF-HEALING GUARD: File readability check ────────────────────────
        if not os.access(file_path, os.R_OK):
            logger.critical(
                "CRITICAL — Permission denied reading: '%s'. "
                "Check file permissions. Returning empty list.",
                file_path,
            )
            return []

        # ── MAIN INGESTION BLOCK ──────────────────────────────────────────────
        try:
            with open(file_path, mode="r", encoding="utf-8-sig", newline="") as csv_file:
                # utf-8-sig handles BOM characters from Excel-exported CSVs.
                reader = csv.DictReader(csv_file)

                # Validate the schema before processing any rows.
                self._validate_headers(reader.fieldnames)

                for line_number, raw_row in enumerate(reader, start=2):
                    # Line numbers start at 2 (row 1 is the header).
                    try:
                        # Step 1: Sanitize whitespace from all fields.
                        row = self._sanitize_row(raw_row)
                        lead_name = row.get("Name") or f"Row {line_number}"

                        # Step 2: Validate the Website field — the core
                        # requirement for AGENT 2 (Scout) to do its job.
                        website = row.get("Website")
                        if not self._is_valid_website(website):
                            logger.warning(
                                "Skipped Lead: %s - No valid website. "
                                "(Value found: '%s') [Line %d]",
                                lead_name,
                                website or "EMPTY",
                                line_number,
                            )
                            skipped_count += 1
                            continue

                        # Step 3: Build a clean, structured lead dictionary
                        # using only the expected headers to prevent noise
                        # from extra CSV columns polluting downstream agents.
                        clean_lead = {
                            header: row.get(header, "").strip()
                            for header in EXPECTED_HEADERS
                        }

                        validated_leads.append(clean_lead)
                        processed_count += 1
                        logger.debug(
                            "Accepted Lead: %s | Website: %s [Line %d]",
                            lead_name,
                            website,
                            line_number,
                        )

                    except Exception as row_error:
                        # Row-level error: log and continue. Never crash the
                        # entire pipeline because of one bad row.
                        logger.warning(
                            "Skipped malformed row at line %d. Error: %s",
                            line_number,
                            str(row_error),
                        )
                        skipped_count += 1
                        continue

        except UnicodeDecodeError:
            logger.critical(
                "CRITICAL — Could not decode '%s' as UTF-8. "
                "Try re-saving the CSV with UTF-8 encoding. Returning empty list.",
                file_path,
            )
            return []

        except Exception as fatal_error:
            # Catch-all for any unexpected I/O or parsing failure.
            logger.critical(
                "CRITICAL — Unexpected error while reading '%s'. "
                "Error: %s. Returning empty list.",
                file_path,
                str(fatal_error),
                exc_info=True,  # Includes full traceback in the log file.
            )
            return []

        # ── SUMMARY REPORT ────────────────────────────────────────────────────
        logger.info("-" * 60)
        logger.info(
            "AGENT 1 — Ingestion complete. "
            "Accepted: %d | Skipped: %d | Total Rows Read: %d",
            processed_count,
            skipped_count,
            processed_count + skipped_count,
        )
        logger.info("=" * 60)

        return validated_leads

    # ──────────────────────────────────────────────────────────────────────────
    # PUBLIC METHOD: export_to_json
    # Optional utility to dump validated leads for debugging or handoff.
    # ──────────────────────────────────────────────────────────────────────────
    def export_to_json(self, leads: list[dict], output_path: str = "validated_leads.json") -> None:
        """
        Serializes the validated lead list to a JSON file for inspection or
        for passing to AGENT 2 (Scout) via file-based IPC.

        Args:
            leads (list[dict]): The validated leads list from ingest_csv().
            output_path (str): Destination path for the JSON file.
        """
        try:
            with open(output_path, mode="w", encoding="utf-8") as json_file:
                json.dump(leads, json_file, indent=4, ensure_ascii=False)
            logger.info(
                "Exported %d validated leads to '%s'.", len(leads), output_path
            )
        except Exception as export_error:
            logger.error(
                "Failed to export leads to JSON: %s", str(export_error)
            )


# ──────────────────────────────────────────────────────────────────────────────
# STANDALONE ENTRY POINT
# Allows direct testing: `python agent1_ingestor.py`
# In production, the orchestrator imports LeadIngestor and calls ingest_csv().
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    # Accept an optional file path as a CLI argument for quick local testing.
    test_file = sys.argv[1] if len(sys.argv) > 1 else "leads.csv"

    ingestor = LeadIngestor()
    leads = ingestor.ingest_csv(test_file)

    if leads:
        # Pretty-print the first lead as a sanity check.
        print("\n── Sample Validated Lead ──")
        print(json.dumps(leads[0], indent=4))
        print(f"\n✓ Total validated leads ready for AGENT 2: {len(leads)}")

        # Optionally export the full clean list to JSON.
        ingestor.export_to_json(leads)
    else:
        print("\n✗ No valid leads were ingested. Check agent1_ingestor.log for details.")
