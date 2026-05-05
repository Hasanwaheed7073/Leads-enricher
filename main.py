"""
================================================================================
LEAD SNIPER — MASTER ORCHESTRATOR (CLI MODE)
================================================================================
Responsibility:
    Wire AGENT 1 (Ingestor) → AGENT 2 (Scout) → AGENT 3 (Brain) into a single
    autonomous pipeline. Reads raw lead CSV, scrapes each website, qualifies +
    scores the lead via AI (Phase 1), generates a personalized pitch (Phase 2,
    only if Phase 1 passes), and writes the final enriched output to a results
    CSV — all in one command.

Architecture Reference:
    .antigravity_env/agents.md   — Multi-Agent system contract
    .antigravity_env/custom_rules.md — Core directives (Zero-Cost, Self-Healing)
    .antigravity_env/decisions.md    — ADR-001, ADR-003, ADR-007 enforced here
    .antigravity_env/error_log.md    — BUG-001 fixed in this revision

Design Principles (per custom_rules.md):
    - ZERO-COST: No paid services. Multi-key free-tier rotation.
    - SELF-HEALING: Each lead is wrapped in try/except — one failure never
      crashes the entire pipeline. Failed leads are written with error markers.
    - SURGICAL: This file only orchestrates. No business logic lives here.
    - SELLABLE QUALITY: Progress logging, graceful exit, partial output
      preservation (CSV is written per-row, not batched), resumable design.

Usage:
    # Recommended: set API keys as a comma-separated env var.
    $env:AI_API_KEYS = "key1,key2,key3"        # PowerShell
    set AI_API_KEYS=key1,key2,key3              # CMD
    export AI_API_KEYS="key1,key2,key3"         # bash/zsh

    python main.py
    python main.py --input-csv leads.csv --output-csv enriched.csv
    python main.py --api-base-url https://api.groq.com/openai/v1/chat/completions \
                   --model llama-3.3-70b-versatile

    # Quick test: pass a single key as the first positional arg.
    python main.py --api-key YOUR_KEY

Free-tier API key sources (per custom_rules.md Tier 1, Directive 1):
    Groq:        https://console.groq.com/keys
    Grok (x.ai): https://x.ai/api
    OpenRouter:  https://openrouter.ai/keys
    Together AI: https://api.together.xyz
    Local Ollama: no key needed; --api-base-url http://localhost:11434/v1/chat/completions

Note on verticals:
    This file currently runs HVAC-only qualification (matches the pre-fix
    behavior of the original main.py). The Career Coaching toggle and other
    verticals live in app_ui.py for now. After prompt_templates.md is wired
    into agent3_brain.py (Roadmap item #5), a --vertical flag will be added
    here in a separate, surgical prompt. See error_log.md BUG-004.

Author:     Lead Architect via Antigravity Engine
Version:    2.0.0  (BUG-001 fix; multi-key rotation; argparse CLI)
================================================================================
"""

import argparse
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
from agent3_brain    import LeadBrain, DEFAULT_API_BASE_URL, DEFAULT_MODEL

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
# DEFAULT PIPELINE CONFIGURATION
# All defaults defined here. Overridable via CLI flags (see argparse section).
# Change these to repurpose the CLI for any industry/CSV without editing code.
# ──────────────────────────────────────────────────────────────────────────────

# Default input CSV. Overridable via --input-csv.
DEFAULT_INPUT_CSV = "leads.csv"

# Default output CSV. Overridable via --output-csv.
DEFAULT_OUTPUT_CSV = "scored_leads.csv"

# Output CSV schema — only these fields are written to the final file.
OUTPUT_HEADERS = [
    "Name", "Email", "Company", "Website",
    "Lead_Score", "Category", "Summary", "Pitch", "Status",
]

# Courtesy delay between leads (seconds). Respects rate limits across
# AGENT 2 (scraping) and AGENT 3 (LLM API). Do NOT set below 2.
INTER_LEAD_DELAY = 3

# Default target industry for CLI mode. HVAC matches pre-fix behavior.
# Will be replaced by --vertical flag once prompt_templates.md is wired in
# (see error_log.md BUG-004 + context.md Roadmap item #5).
DEFAULT_TARGET_INDUSTRY = "HVAC Contractors"


# ──────────────────────────────────────────────────────────────────────────────
# CLI ARGUMENT PARSING
# ──────────────────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments for the CLI orchestrator.

    All flags are optional — sensible defaults are provided. API keys can
    come from --api-key (single, for testing) or AI_API_KEYS env var
    (comma-separated, for production).

    Returns:
        argparse.Namespace with attributes: input_csv, output_csv,
        api_base_url, model, api_key, target_industry.
    """
    parser = argparse.ArgumentParser(
        description="Lead Sniper AI — autonomous lead enrichment pipeline (CLI mode).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "For multi-key rotation, set AI_API_KEYS env var "
            "(comma-separated keys). For testing, use --api-key."
        ),
    )
    parser.add_argument(
        "--input-csv",
        default=DEFAULT_INPUT_CSV,
        help=f"Path to input leads CSV. Default: {DEFAULT_INPUT_CSV}",
    )
    parser.add_argument(
        "--output-csv",
        default=DEFAULT_OUTPUT_CSV,
        help=f"Path to output enriched CSV. Default: {DEFAULT_OUTPUT_CSV}",
    )
    parser.add_argument(
        "--api-base-url",
        default=DEFAULT_API_BASE_URL,
        help=f"Full URL to OpenAI-compatible /v1/chat/completions endpoint. Default: {DEFAULT_API_BASE_URL}",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Model identifier supported by the chosen provider. Default: {DEFAULT_MODEL}",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Single API key for quick testing. For production, set AI_API_KEYS env var instead.",
    )
    parser.add_argument(
        "--target-industry",
        default=DEFAULT_TARGET_INDUSTRY,
        help=f"Industry to qualify leads against. Default: {DEFAULT_TARGET_INDUSTRY}",
    )
    return parser.parse_args()


# ──────────────────────────────────────────────────────────────────────────────
# API KEY RESOLUTION
# Priority order (most secure first, multi-key first):
#   1. AI_API_KEYS env var (comma-separated)  — production, enables rotation
#   2. --api-key CLI flag (single key)         — quick testing
#   3. None found                              — log CRITICAL, run with empty pool
# NEVER hardcode keys.
# ──────────────────────────────────────────────────────────────────────────────
def resolve_api_keys(cli_single_key: str | None) -> list[str]:
    """
    Build the API key pool from env var or CLI argument.

    Per ADR-003 (key rotation), the pipeline accepts a list of keys and
    rotates on 4xx/5xx errors. A single key works (rotation is a no-op),
    but multi-key is recommended for production.

    Args:
        cli_single_key: Optional single key passed via --api-key.

    Returns:
        list[str]: Cleaned list of API keys. May be empty.
    """
    # Priority 1: env var with comma-separated keys (multi-key rotation).
    raw_env = os.environ.get("AI_API_KEYS", "").strip()
    if raw_env:
        keys = [k.strip() for k in raw_env.split(",") if k.strip()]
        if keys:
            logger.info(
                "API keys loaded from AI_API_KEYS env var: %d key(s) ready for rotation.",
                len(keys),
            )
            return keys

    # Priority 2: single key from CLI flag.
    if cli_single_key and cli_single_key.strip():
        logger.info("Single API key loaded from --api-key flag (no rotation).")
        return [cli_single_key.strip()]

    # Priority 3: nothing found.
    logger.critical(
        "No API keys found. Set AI_API_KEYS env var (comma-separated) "
        "or pass --api-key. AGENT 3 will return fallback responses and "
        "all leads will score 0."
    )
    return []


# ──────────────────────────────────────────────────────────────────────────────
# HELPER: build_output_row
# Maps a fully-enriched lead dict to exactly the OUTPUT_HEADERS schema.
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
        "Category":   lead.get("category", "Unknown"),
        "Summary":    lead.get("summary", "N/A"),
        "Pitch":      lead.get("pitch", "N/A"),
        "Status":     status,
    }


# ──────────────────────────────────────────────────────────────────────────────
# MAIN PIPELINE FUNCTION
# ──────────────────────────────────────────────────────────────────────────────
def run_pipeline(args: argparse.Namespace, api_keys: list[str]) -> None:
    """
    Executes the full 3-agent two-phase enrichment pipeline end-to-end.

    Pipeline Flow:
        1. AGENT 1 reads and validates the input CSV.
        2. For each validated lead:
            a. AGENT 2 scrapes the lead's website (with verification signals).
            b. AGENT 3 Phase 1: qualify + score against target industry.
            c. AGENT 3 Phase 2: generate pitch (only if Phase 1 passed).
            d. The enriched row is written immediately (per-row flush, ADR-007).
        3. A final summary is printed to console and logged.

    Self-Healing (per custom_rules.md Tier 1, Directive 4):
        Each lead is wrapped in a try/except block. A failure on any single
        lead logs a WARNING and writes a "FAILED" status row to the CSV,
        then continues to the next lead. The pipeline is never aborted by
        a single bad record.

    Args:
        args:     Parsed CLI arguments (input_csv, output_csv, api_base_url, model, target_industry).
        api_keys: List of API keys for AGENT 3 rotation (per ADR-003).
    """
    run_start = datetime.now()

    logger.info("=" * 70)
    logger.info("  LEAD SNIPER — PIPELINE START")
    logger.info("  Run ID         : %s", run_start.strftime("%Y%m%d_%H%M%S"))
    logger.info("  Input CSV      : %s", args.input_csv)
    logger.info("  Output CSV     : %s", args.output_csv)
    logger.info("  Target Industry: %s", args.target_industry)
    logger.info("  AI Provider    : %s", args.api_base_url)
    logger.info("  AI Model       : %s", args.model)
    logger.info("  API Keys Loaded: %d", len(api_keys))
    logger.info("=" * 70)

    ingestor = LeadIngestor()
    scout    = WebScout()
    brain    = LeadBrain()

    # ── AGENT 1: INGEST ───────────────────────────────────────────────────────
    logger.info("► AGENT 1: Reading and validating leads from '%s'...", args.input_csv)
    validated_leads = ingestor.ingest_csv(args.input_csv)

    if not validated_leads:
        logger.critical(
            "CRITICAL — AGENT 1 returned zero valid leads. "
            "Check '%s' exists and contains rows with valid Website URLs. "
            "Pipeline aborted.",
            args.input_csv,
        )
        scout.close()
        return

    total = len(validated_leads)
    logger.info("✓ AGENT 1 complete. %d validated leads ready for processing.\n", total)

    # ── TRACKING COUNTERS ─────────────────────────────────────────────────────
    success_count      = 0
    qualified_count    = 0
    disqualified_count = 0
    failed_count       = 0

    # ── OPEN OUTPUT CSV ───────────────────────────────────────────────────────
    # File is opened once and kept open for the duration of the loop.
    # Each row is flushed immediately so partial results survive crashes (ADR-007).
    try:
        output_file = open(args.output_csv, mode="w", newline="", encoding="utf-8")
        writer = csv.DictWriter(output_file, fieldnames=OUTPUT_HEADERS)
        writer.writeheader()
        logger.info("► Output CSV initialized: '%s'", args.output_csv)
    except OSError as file_err:
        logger.critical(
            "CRITICAL — Cannot open output file '%s': %s. Pipeline aborted.",
            args.output_csv, file_err,
        )
        scout.close()
        return

    # ── MAIN PROCESSING LOOP ─────────────────────────────────────────────────
    logger.info("\n%s", "=" * 70)
    logger.info("► Starting 3-agent two-phase enrichment loop...")
    logger.info("%s\n", "=" * 70)

    for index, lead in enumerate(validated_leads, start=1):
        company   = lead.get("Company",  f"Lead #{index}")
        lead_name = lead.get("Name",     "Unknown")
        url       = lead.get("Website",  "")

        logger.info("─" * 70)
        logger.info("[%d/%d] ► %s (%s)", index, total, company, lead_name)
        logger.info("─" * 70)

        # ── PER-LEAD SELF-HEALING GUARD ───────────────────────────────────────
        try:
            # ── AGENT 2: SCRAPE + VERIFY ──────────────────────────────────────
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

            # Merge scraped fields.
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

            # ── AGENT 3 — PHASE 1: QUALIFY & SUMMARIZE ────────────────────────
            logger.info("  AGENT 3 (Phase 1) ► Qualifying against '%s'...", args.target_industry)
            phase1 = brain.qualify_and_summarize(
                lead_data=lead,
                scraped_data=lead,
                target_industry=args.target_industry,
                api_keys=api_keys,
                api_base_url=args.api_base_url,
                model_name=args.model,
            )

            is_valid = phase1.get("is_valid", False)
            score    = phase1.get("score", 0)
            summary  = phase1.get("summary", "Error.")
            category = phase1.get("category", "Unknown")

            lead["lead_score"] = score
            lead["summary"]    = summary
            lead["category"]   = category

            # ── AGENT 3 — PHASE 2: GENERATE PITCH (only for valid leads) ─────
            if is_valid:
                logger.info("  AGENT 3 (Phase 2) ► Generating pitch (lead qualified)...")
                phase2 = brain.generate_pitch(
                    lead_data=lead,
                    summary=summary,
                    api_keys=api_keys,
                    api_base_url=args.api_base_url,
                    model_name=args.model,
                )
                lead["pitch"] = phase2.get("pitch", "Error generating pitch.")
                qualified_count += 1
                row_status = "OK"
            else:
                lead["pitch"] = "SKIPPED — Industry mismatch or unverifiable."
                disqualified_count += 1
                row_status = "DISQUALIFIED"
                logger.info("  ⏭️  Skipping pitch — lead failed Phase 1 qualification.")

            # ── WRITE TO OUTPUT CSV ───────────────────────────────────────────
            row = build_output_row(lead, status=row_status)
            writer.writerow(row)
            output_file.flush()  # Per ADR-007: flush per-row, not batched.

            # ── CONSOLE SUCCESS LOG ───────────────────────────────────────────
            success_count += 1
            print(
                f"\n  ✅  {company} — "
                f"Score: {score}/10 | Category: {category} | "
                f"{'QUALIFIED' if is_valid else 'DISQUALIFIED'}\n"
                f"      Pitch: {str(lead['pitch'])[:100]}...\n"
            )
            logger.info(
                "  ✓ Processed %s | Score: %s/10 | Valid: %s",
                company, score, is_valid,
            )

        except Exception as lead_error:
            # ── PER-LEAD FAILURE HANDLER ──────────────────────────────────────
            failed_count += 1
            error_message = str(lead_error)

            logger.warning(
                "  ✗ FAILED to process %s: %s — Writing error row and continuing.",
                company, error_message,
            )

            try:
                error_lead = lead.copy()
                error_lead["lead_score"] = 0
                error_lead["category"]   = "Error"
                error_lead["summary"]    = "Processing error — see main.log"
                error_lead["pitch"]      = "Processing error — see main.log"
                error_row = build_output_row(
                    error_lead,
                    status=f"FAILED: {error_message[:80]}",
                )
                writer.writerow(error_row)
                output_file.flush()
            except Exception as write_err:
                logger.error(
                    "  Could not write error row for %s: %s",
                    company, write_err,
                )

        # ── INTER-LEAD COURTESY DELAY ─────────────────────────────────────────
        if index < total:
            logger.info(
                "  ⏳ Waiting %ds before next lead (rate-limit courtesy)...",
                INTER_LEAD_DELAY,
            )
            time.sleep(INTER_LEAD_DELAY)

    # ── CLOSE OUTPUT FILE ─────────────────────────────────────────────────────
    output_file.close()
    logger.info("Output CSV closed and saved: '%s'", args.output_csv)

    # ── CLOSE SCOUT SESSION ───────────────────────────────────────────────────
    scout.close()

    # ── FINAL SUMMARY ─────────────────────────────────────────────────────────
    run_end     = datetime.now()
    elapsed     = run_end - run_start
    elapsed_str = str(elapsed).split(".")[0]

    logger.info("\n%s", "=" * 70)
    logger.info("  LEAD SNIPER — PIPELINE COMPLETE")
    logger.info("  Duration       : %s", elapsed_str)
    logger.info("  Total Leads    : %d", total)
    logger.info("  Processed OK   : %d ✅", success_count)
    logger.info("  Qualified      : %d 🎯", qualified_count)
    logger.info("  Disqualified   : %d ⏭", disqualified_count)
    logger.info("  Failed         : %d ✗", failed_count)
    logger.info("  Output         : %s", args.output_csv)
    logger.info("%s\n", "=" * 70)

    print("\n" + "=" * 70)
    print(f"  🎯 LEAD SNIPER COMPLETE")
    print(f"  ✅  Processed   : {success_count}/{total} leads")
    print(f"  🎯 Qualified   : {qualified_count}/{total} leads")
    print(f"  ⏭  Disqualified: {disqualified_count}/{total} leads")
    print(f"  ✗  Failed      : {failed_count}/{total} leads")
    print(f"  ⏱  Duration    : {elapsed_str}")
    print(f"  📄 Output      : {args.output_csv}")
    print("=" * 70 + "\n")


# ──────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    args = parse_args()
    api_keys = resolve_api_keys(cli_single_key=args.api_key)
    run_pipeline(args, api_keys)
