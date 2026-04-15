"""
================================================================================
LEAD SNIPER — MASTER ORCHESTRATOR
================================================================================
Responsibility:
    Wire AGENT 1 (Ingestor) → AGENT 2 (Scout) → AGENT 3 (Brain) into a single
    autonomous pipeline. Reads raw lead CSV, scrapes each website, scores the
    lead via AI, generates a personalized pitch, and writes the final enriched
    output to a results CSV — all in one command.

Architecture Reference:
    .antigravity_env/agents.md   — Multi-Agent system contract
    .antigravity_env/custom_rules.md — Core directives (Zero-Cost, Self-Healing)

Design Principles (per custom_rules.md):
    - ZERO-COST: No paid services invoked. Gemini free tier used for AI.
    - SELF-HEALING: Each lead is wrapped in try/except — one failure never
      crashes the entire pipeline. Failed leads are written with error markers.
    - SURGICAL: This file only orchestrates. No business logic lives here.
    - SELLABLE QUALITY: Progress logging, graceful exit, partial output
      preservation (CSV is written per-row, not batched), resumable design.

Usage:
    # Recommended: Set your API key as an environment variable (never hardcode).
    $env:GEMINI_API_KEY = "YOUR_KEY_HERE"   # PowerShell
    set GEMINI_API_KEY=YOUR_KEY_HERE         # CMD

    python main.py

    # Or pass the key at runtime (for quick testing only):
    python main.py YOUR_KEY_HERE

Get a free Gemini API key: https://aistudio.google.com/app/apikey

Author:     Lead Architect via Antigravity Engine
Version:    1.0.0
================================================================================
"""

import csv
import logging
import os
import sys
import time
from datetime import datetime

# ── Agent Imports ─────────────────────────────────────────────────────────────
# Each agent is imported as a module — no business logic lives in this file.
from agent1_ingestor import LeadIngestor
from agent2_scout    import WebScout
from agent3_brain    import LeadBrain

# ──────────────────────────────────────────────────────────────────────────────
# LOGGING CONFIGURATION
# Orchestrator has its own log file (main.log) AND mirrors to console.
# This creates a full end-to-end audit trail across all four log files:
#   main.log, agent1_ingestor.log, agent2_scout.log, agent3_brain.log
# ──────────────────────────────────────────────────────────────────────────────
LOG_FILE = "main.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger("ORCHESTRATOR")

# ──────────────────────────────────────────────────────────────────────────────
# PIPELINE CONFIGURATION
# All file paths and runtime settings are defined here in one place.
# Change these values to repurpose the pipeline for any industry/CSV.
# ──────────────────────────────────────────────────────────────────────────────

# Input: Raw leads CSV exported from your CRM or spreadsheet.
INPUT_CSV = "Hvac Contractors - Sheet1.csv"

# Output: Enriched leads with AI scores and personalized pitches.
OUTPUT_CSV = "scored_hvac_leads.csv"

# Output CSV schema — only these fields are written to the final file.
# Agent fields like 'scraped_content' are used internally but not exported.
OUTPUT_HEADERS = ["Name", "Email", "Company", "Website", "Lead_Score", "Pitch", "Status"]

# Courtesy delay between leads (seconds).
# Respects AGENT 2's rate-limit needs and AGENT 3's API quota.
# Do NOT set below 2 — Google and most websites will flag rapid requests.
INTER_LEAD_DELAY = 3

# ──────────────────────────────────────────────────────────────────────────────
# API KEY RESOLUTION
# Priority order (most secure first):
#   1. Environment variable  GEMINI_API_KEY  (recommended for production)
#   2. CLI argument          python main.py YOUR_KEY  (for quick testing)
#   3. Falls back to empty string → AGENT 3 will log a CRITICAL error
#      and return fallback responses (pipeline still runs, scores will be 0).
# NEVER hardcode your API key in source files.
# ──────────────────────────────────────────────────────────────────────────────
def resolve_api_key() -> str:
    """
    Resolves the Gemini API key from environment variables or CLI arguments.
    Logs a warning if neither source provides a key so the operator is alerted
    before the pipeline runs (rather than discovering it mid-batch).

    Returns:
        str: The API key, or an empty string if not found.
    """
    # Priority 1: Environment variable (safest — never ends up in git history)
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        logger.info("API key loaded from environment variable GEMINI_API_KEY.")
        return key

    # Priority 2: CLI argument (convenient for local testing)
    if len(sys.argv) > 1:
        key = sys.argv[1].strip()
        if key:
            logger.info("API key loaded from CLI argument.")
            return key

    # Priority 3: No key found
    logger.warning(
        "No GEMINI_API_KEY found. "
        "Set it with: $env:GEMINI_API_KEY='YOUR_KEY' (PowerShell) "
        "or set GEMINI_API_KEY=YOUR_KEY (CMD). "
        "Pipeline will run but AI scoring will return fallback values."
    )
    return ""


# ──────────────────────────────────────────────────────────────────────────────
# HELPER: build_output_row
# Maps a fully-enriched lead dict to exactly the OUTPUT_HEADERS schema.
# Isolates the CSV write format from the rest of the pipeline logic.
# ──────────────────────────────────────────────────────────────────────────────
def build_output_row(lead: dict, status: str = "OK") -> dict:
    """
    Constructs the exact dict that gets written as a row to the output CSV.

    Args:
        lead   (dict): Fully-enriched lead dict (AGENT 1 + 2 + 3 data merged).
        status (str):  "OK" on success, or an error message on failure.

    Returns:
        dict: Flat dict matching OUTPUT_HEADERS exactly.
    """
    return {
        "Name":       lead.get("Name", "N/A"),
        "Email":      lead.get("Email", "N/A"),
        "Company":    lead.get("Company", "N/A"),
        "Website":    lead.get("Website", "N/A"),
        "Lead_Score": lead.get("lead_score", 0),
        "Pitch":      lead.get("pitch", "N/A"),
        "Status":     status,
    }


# ──────────────────────────────────────────────────────────────────────────────
# MAIN PIPELINE FUNCTION
# ──────────────────────────────────────────────────────────────────────────────
def run_pipeline(api_key: str) -> None:
    """
    Executes the full 3-agent lead enrichment pipeline end-to-end.

    Pipeline Flow:
        1. AGENT 1 reads and validates the input CSV.
        2. For each validated lead:
            a. AGENT 2 scrapes the lead's website.
            b. AGENT 3 scores the lead and generates a pitch.
            c. The enriched row is written to the output CSV immediately
               (partial results are preserved even if the pipeline crashes).
        3. A final summary is printed to the console and logged.

    Self-Healing:
        Each lead is wrapped in a try/except block. A failure on any single
        lead logs a WARNING and writes a "FAILED" status row to the CSV,
        then continues to the next lead. The pipeline is never aborted by
        a single bad record.

    Args:
        api_key (str): Google Gemini API key for AGENT 3.
    """
    run_start = datetime.now()

    logger.info("=" * 70)
    logger.info("  LEAD SNIPER — PIPELINE START")
    logger.info("  Run ID   : %s", run_start.strftime("%Y%m%d_%H%M%S"))
    logger.info("  Input    : %s", INPUT_CSV)
    logger.info("  Output   : %s", OUTPUT_CSV)
    logger.info("  AI Key   : %s", "SET ✓" if api_key else "MISSING ✗ (scores will be 0)")
    logger.info("=" * 70)

    # ── INIT AGENTS ───────────────────────────────────────────────────────────
    ingestor = LeadIngestor()
    scout    = WebScout()
    brain    = LeadBrain()

    # ── AGENT 1: INGEST ───────────────────────────────────────────────────────
    logger.info("► AGENT 1: Reading and validating leads from '%s'...", INPUT_CSV)
    validated_leads = ingestor.ingest_csv(INPUT_CSV)

    if not validated_leads:
        logger.critical(
            "CRITICAL — AGENT 1 returned zero valid leads. "
            "Check '%s' exists and contains rows with valid Website URLs. "
            "Pipeline aborted.",
            INPUT_CSV,
        )
        scout.close()
        return

    total = len(validated_leads)
    logger.info("✓ AGENT 1 complete. %d validated leads ready for processing.\n", total)

    # ── TRACKING COUNTERS ─────────────────────────────────────────────────────
    success_count = 0
    failed_count  = 0

    # ── OPEN OUTPUT CSV ───────────────────────────────────────────────────────
    # File is opened once and kept open for the duration of the loop.
    # Each row is flushed immediately so partial results survive crashes.
    try:
        output_file = open(OUTPUT_CSV, mode="w", newline="", encoding="utf-8")
        writer = csv.DictWriter(output_file, fieldnames=OUTPUT_HEADERS)
        writer.writeheader()
        logger.info("► Output CSV initialized: '%s'", OUTPUT_CSV)
    except OSError as file_err:
        logger.critical(
            "CRITICAL — Cannot open output file '%s': %s. Pipeline aborted.",
            OUTPUT_CSV, file_err,
        )
        scout.close()
        return

    # ── MAIN PROCESSING LOOP ─────────────────────────────────────────────────
    logger.info("\n%s", "=" * 70)
    logger.info("► Starting 3-agent enrichment loop...")
    logger.info("%s\n", "=" * 70)

    for index, lead in enumerate(validated_leads, start=1):
        company   = lead.get("Company",  f"Lead #{index}")
        lead_name = lead.get("Name",     "Unknown")
        url       = lead.get("Website",  "")

        logger.info("─" * 70)
        logger.info("[%d/%d] ► %s (%s)", index, total, company, lead_name)
        logger.info("─" * 70)

        # ── PER-LEAD SELF-HEALING GUARD ───────────────────────────────────────
        # Any exception here is caught, logged, and a FAILED row is written.
        # The pipeline continues to the next lead without interruption.
        try:
            # ── AGENT 2: SCRAPE ───────────────────────────────────────────────
            logger.info("  AGENT 2 ► Scraping: %s", url)
            scraped_data = scout.scrape_website(
                url,
                email=lead.get("Email", ""),
                person_name=lead.get("Name", ""),
            )

            # Merge verification signals into the lead dict.
            lead["domain_alive"]         = scraped_data.get("domain_alive", False)
            lead["email_found_on_page"]  = scraped_data.get("email_found_on_page", False)
            lead["email_domain_matches"] = scraped_data.get("email_domain_matches", False)
            lead["person_found_on_page"] = scraped_data.get("person_found_on_page", False)
            lead["person_context"]       = scraped_data.get("person_context", "")

            # Merge scraped fields into the lead dict (single unified object).
            if "error" in scraped_data:
                lead["scrape_error"]    = scraped_data["error"]
                lead["scraped_title"]   = None
                lead["scraped_content"] = None
                logger.warning(
                    "  AGENT 2 ✗ Scrape failed for %s: %s",
                    company, scraped_data["error"],
                )
            else:
                lead["scrape_error"]    = None
                lead["scraped_title"]   = scraped_data.get("title")
                lead["scraped_content"] = scraped_data.get("content")
                logger.info(
                    "  AGENT 2 ✓ Scraped '%s' (%d chars of content)",
                    scraped_data.get("title", "No title"),
                    len(scraped_data.get("content", "")),
                )

            # ── AGENT 3: SCORE & PITCH ────────────────────────────────────────
            logger.info("  AGENT 3 ► Scoring and generating pitch...")
            ai_result = brain.analyze_and_pitch(
                lead_data=lead,
                scraped_data=lead,
                api_key=api_key,
            )

            lead["lead_score"] = ai_result["lead_score"]
            lead["pitch"]      = ai_result["pitch"]

            # ── WRITE TO OUTPUT CSV ───────────────────────────────────────────
            row = build_output_row(lead, status="OK")
            writer.writerow(row)
            output_file.flush()  # Write immediately — don't buffer

            # ── CONSOLE SUCCESS LOG ───────────────────────────────────────────
            success_count += 1
            print(
                f"\n  ✅  Processed {company} — "
                f"Score: {lead['lead_score']}/10\n"
                f"      Pitch: {lead['pitch'][:100]}...\n"
            )
            logger.info(
                "  ✓ Processed %s | Score: %d/10",
                company, lead["lead_score"],
            )

        except Exception as lead_error:
            # ── PER-LEAD FAILURE HANDLER ──────────────────────────────────────
            # The try/except here prevents ONE bad lead from killing the run.
            # The failed lead is recorded in the CSV with a FAILED status.
            failed_count += 1
            error_message = str(lead_error)

            logger.warning(
                "  ✗ FAILED to process %s: %s — Writing error row and continuing.",
                company, error_message,
            )

            try:
                error_lead = lead.copy()
                error_lead["lead_score"] = 0
                error_lead["pitch"]      = "Processing error — see main.log"
                error_row = build_output_row(error_lead, status=f"FAILED: {error_message[:80]}")
                writer.writerow(error_row)
                output_file.flush()
            except Exception as write_err:
                logger.error(
                    "  Could not write error row for %s: %s",
                    company, write_err,
                )

        # ── INTER-LEAD COURTESY DELAY ─────────────────────────────────────────
        # Respect AGENT 2's and AGENT 3's rate limits between each lead.
        # Skip the delay after the final lead — no point waiting on exit.
        if index < total:
            logger.info(
                "  ⏳ Waiting %ds before next lead (rate-limit courtesy)...",
                INTER_LEAD_DELAY,
            )
            time.sleep(INTER_LEAD_DELAY)

    # ── CLOSE OUTPUT FILE ─────────────────────────────────────────────────────
    output_file.close()
    logger.info("Output CSV closed and saved: '%s'", OUTPUT_CSV)

    # ── CLOSE SCOUT SESSION ───────────────────────────────────────────────────
    scout.close()

    # ── FINAL SUMMARY ─────────────────────────────────────────────────────────
    run_end     = datetime.now()
    elapsed     = run_end - run_start
    elapsed_str = str(elapsed).split(".")[0]  # HH:MM:SS, no microseconds

    logger.info("\n%s", "=" * 70)
    logger.info("  LEAD SNIPER — PIPELINE COMPLETE")
    logger.info("  Duration   : %s", elapsed_str)
    logger.info("  Total Leads: %d", total)
    logger.info("  Successful : %d ✅", success_count)
    logger.info("  Failed     : %d ✗", failed_count)
    logger.info("  Output     : %s", OUTPUT_CSV)
    logger.info("%s\n", "=" * 70)

    print("\n" + "=" * 70)
    print(f"  🎯 LEAD SNIPER COMPLETE")
    print(f"  ✅  Processed : {success_count}/{total} leads")
    print(f"  ✗   Failed    : {failed_count}/{total} leads")
    print(f"  ⏱   Duration  : {elapsed_str}")
    print(f"  📄  Output    : {OUTPUT_CSV}")
    print("=" * 70 + "\n")


# ──────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    api_key = resolve_api_key()
    run_pipeline(api_key)
