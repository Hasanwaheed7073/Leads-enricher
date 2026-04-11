"""
================================================================================
LEAD SNIPER — AGENT 2: SCOUT
================================================================================
Responsibility:
    Receive a validated lead list from AGENT 1 (Ingestor), visit each lead's
    website, and extract meaningful content (title + paragraph text) for
    downstream analysis by AGENT 3 (Scorer & Pitcher).

Architecture Reference:
    .antigravity_env/agents.md   — Multi-Agent system contract
    .antigravity_env/custom_rules.md — Core directives (Zero-Cost, Self-Healing)

Design Principles (per custom_rules.md):
    - ZERO-COST: Uses only `requests` and `beautifulsoup4` (both free/OSS).
    - SELF-HEALING: All HTTP calls wrapped in try/except with retry logic.
    - SURGICAL: Handles ONLY scraping. No scoring, no pitching.
    - SELLABLE QUALITY: Stealth headers, rate limiting, full audit logging,
      importable by the main orchestrator without modification.

Dependencies (free & open-source):
    pip install requests beautifulsoup4 lxml

Author:     Lead Architect via Antigravity Engine
Version:    1.0.0
================================================================================
"""

import json
import logging
import time
import random
from typing import Optional

import requests
from bs4 import BeautifulSoup

# ──────────────────────────────────────────────────────────────────────────────
# LOGGING CONFIGURATION
# Mirrors AGENT 1's logging pattern for a unified log trail across all agents.
# ──────────────────────────────────────────────────────────────────────────────
LOG_FILE = "agent2_scout.log"

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger("AGENT_2_SCOUT")


# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────

# Maximum combined character count extracted from <p> tags per page.
# Keeps the payload lean for AGENT 3's AI context window.
MAX_CONTENT_CHARS = 1000

# HTTP request timeout in seconds. Prevents indefinite hangs on slow servers.
REQUEST_TIMEOUT = 10

# Auto-retry settings (per custom_rules.md — Directive 4: SELF-HEALING).
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # Seconds. Retry waits: 2s, 4s, 8s (exponential).

# Courtesy delay range between requests (seconds).
# Mimics human browsing cadence and avoids IP rate-limiting.
MIN_DELAY_SECONDS = 1.5
MAX_DELAY_SECONDS = 4.0

# ──────────────────────────────────────────────────────────────────────────────
# STEALTH CONFIGURATION
# Rotating User-Agent pool. Mimics real browser traffic to bypass basic
# bot-blocking. A single static UA is easy to fingerprint and block.
# ──────────────────────────────────────────────────────────────────────────────
USER_AGENT_POOL = [
    # Chrome on Windows 11
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
    "Gecko/20100101 Firefox/125.0",
    # Firefox on Linux
    "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) "
    "Gecko/20100101 Firefox/124.0",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
]

# Realistic browser headers sent with every request.
# Absence of these headers is a primary bot-detection signal.
BASE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "DNT": "1",  # Do Not Track — also a common browser header signal
}


# ──────────────────────────────────────────────────────────────────────────────
# CLASS: WebScout
# ──────────────────────────────────────────────────────────────────────────────
class WebScout:
    """
    AGENT 2 — Scout

    Visits each lead's website and extracts structured content for AGENT 3.
    Designed to consume the output of AGENT 1 (LeadIngestor) directly.

    Usage (standalone):
        scout = WebScout()
        result = scout.scrape_website("https://example.com")

    Usage (with AGENT 1 output):
        from agent1_ingestor import LeadIngestor
        from agent2_scout import WebScout

        leads  = LeadIngestor().ingest_csv("leads.csv")
        scout  = WebScout()
        results = scout.scrape_all(leads)

    Returns per lead:
        {
            "url":     "https://example.com",
            "title":   "Example Domain",
            "content": "This domain is for use in illustrative examples..."
        }

    On failure:
        {
            "url":   "https://bad-url.com",
            "error": "Connection timed out after 10s"
        }
    """

    def __init__(self):
        # Initialise a persistent requests.Session for connection reuse
        # (faster than creating a new connection per request).
        self.session = requests.Session()
        logger.info("WebScout initialized. Session ready.")

    # ──────────────────────────────────────────────────────────────────────────
    # PRIVATE HELPER: _get_headers
    # Returns a fresh headers dict with a randomly selected User-Agent.
    # ──────────────────────────────────────────────────────────────────────────
    def _get_headers(self) -> dict:
        """
        Builds a stealth header dict by randomly selecting from the UA pool.
        Called fresh on every request attempt to maximise rotation diversity.
        """
        headers = BASE_HEADERS.copy()
        headers["User-Agent"] = random.choice(USER_AGENT_POOL)
        return headers

    # ──────────────────────────────────────────────────────────────────────────
    # PRIVATE HELPER: _extract_title
    # Safely extracts the <title> text from a BeautifulSoup object.
    # ──────────────────────────────────────────────────────────────────────────
    def _extract_title(self, soup: BeautifulSoup) -> str:
        """
        Returns the page <title> tag text, stripped of whitespace.
        Falls back to "No title found" if the tag is absent or empty.
        """
        title_tag = soup.find("title")
        if title_tag and title_tag.get_text(strip=True):
            return title_tag.get_text(strip=True)
        return "No title found"

    # ──────────────────────────────────────────────────────────────────────────
    # PRIVATE HELPER: _extract_paragraph_content
    # Aggregates <p> tag text up to MAX_CONTENT_CHARS characters.
    # ──────────────────────────────────────────────────────────────────────────
    def _extract_paragraph_content(self, soup: BeautifulSoup) -> str:
        """
        Collects text from all <p> tags and concatenates them, capped at
        MAX_CONTENT_CHARS to keep AGENT 3's AI context window efficient.

        Empty paragraphs (ads, whitespace dividers) are filtered out.
        Returns "No content extracted" if no paragraphs are found.
        """
        paragraphs = soup.find_all("p")
        content_parts = []
        total_chars = 0

        for p in paragraphs:
            text = p.get_text(separator=" ", strip=True)
            if not text:
                continue  # Skip empty/whitespace-only <p> tags

            remaining_capacity = MAX_CONTENT_CHARS - total_chars
            if remaining_capacity <= 0:
                break  # Budget exhausted — stop collecting

            # Slice the paragraph if it would exceed the character budget.
            content_parts.append(text[:remaining_capacity])
            total_chars += len(text)

        if not content_parts:
            return "No content extracted"

        return " ".join(content_parts)

    # ──────────────────────────────────────────────────────────────────────────
    # PUBLIC METHOD: scrape_website
    # Core scraping unit. Self-healing with exponential-backoff retry logic.
    # ──────────────────────────────────────────────────────────────────────────
    def scrape_website(self, url: str) -> dict:
        """
        Visits a single URL, extracts structured content, and returns a dict.

        Self-Healing Behaviour (per custom_rules.md — Directive 4):
            - Network error / timeout → logs error, returns {"url", "error"}.
            - HTTP 4xx/5xx           → logs warning, returns {"url", "error"}.
            - Auto-retry             → up to MAX_RETRIES with exponential backoff.
            - Parsing failure        → logs warning, returns best-effort result.

        Args:
            url (str): A validated URL string (output of AGENT 1).

        Returns:
            dict: Success → {"url", "title", "content"}
                  Failure → {"url", "error"}
        """
        logger.info("Scraping: %s", url)

        last_error: Optional[str] = None

        # ── RETRY LOOP ────────────────────────────────────────────────────────
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.debug("Attempt %d/%d for: %s", attempt, MAX_RETRIES, url)

                response = self.session.get(
                    url,
                    headers=self._get_headers(),
                    timeout=REQUEST_TIMEOUT,
                    allow_redirects=True,  # Follow HTTP 301/302 redirects
                )

                # ── HTTP STATUS CHECK ─────────────────────────────────────────
                # raise_for_status() converts 4xx/5xx into exceptions so they
                # are caught by the RequestException handler below.
                response.raise_for_status()

                # ── SUCCESSFUL RESPONSE ───────────────────────────────────────
                logger.debug(
                    "HTTP %d received for: %s (%.2f KB)",
                    response.status_code,
                    url,
                    len(response.content) / 1024,
                )

                # ── HTML PARSING ──────────────────────────────────────────────
                # lxml is the fastest parser; falls back to html.parser if
                # lxml is not installed (no crash, just slightly slower).
                try:
                    soup = BeautifulSoup(response.text, "lxml")
                except Exception:
                    logger.debug("lxml unavailable, falling back to html.parser.")
                    soup = BeautifulSoup(response.text, "html.parser")

                # ── CONTENT EXTRACTION ────────────────────────────────────────
                title   = self._extract_title(soup)
                content = self._extract_paragraph_content(soup)

                logger.info(
                    "✓ Scraped: %s | Title: '%s' | Content: %d chars",
                    url,
                    title,
                    len(content),
                )

                return {
                    "url":     url,
                    "title":   title,
                    "content": content,
                }

            except requests.exceptions.Timeout:
                last_error = f"Request timed out after {REQUEST_TIMEOUT}s"
                logger.warning(
                    "Scrape failed for %s: %s (Attempt %d/%d)",
                    url, last_error, attempt, MAX_RETRIES,
                )

            except requests.exceptions.ConnectionError:
                last_error = "Connection error — host unreachable or DNS failure"
                logger.warning(
                    "Scrape failed for %s: %s (Attempt %d/%d)",
                    url, last_error, attempt, MAX_RETRIES,
                )

            except requests.exceptions.HTTPError as http_err:
                # HTTP 4xx/5xx — retrying these is rarely useful, so we bail
                # immediately instead of waiting through backoff cycles.
                last_error = f"HTTP error: {http_err}"
                logger.warning("Scrape failed for %s: %s — Not retrying.", url, last_error)
                break

            except requests.exceptions.RequestException as req_err:
                last_error = str(req_err)
                logger.warning(
                    "Scrape failed for %s: %s (Attempt %d/%d)",
                    url, last_error, attempt, MAX_RETRIES,
                )

            # ── EXPONENTIAL BACKOFF ────────────────────────────────────────────
            # Wait before the next retry. Adds a small jitter to prevent
            # thundering-herd behaviour when scraping multiple sites.
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF_BASE ** attempt + random.uniform(0.1, 0.9)
                logger.debug("Waiting %.1fs before retry %d...", wait, attempt + 1)
                time.sleep(wait)

        # ── ALL RETRIES EXHAUSTED ─────────────────────────────────────────────
        logger.error("✗ Scrape failed for %s after %d attempts. Last error: %s",
                     url, MAX_RETRIES, last_error)
        return {
            "url":   url,
            "error": last_error or "Unknown scrape failure",
        }

    # ──────────────────────────────────────────────────────────────────────────
    # PUBLIC METHOD: scrape_all
    # Batch processor. Accepts AGENT 1's full lead list directly.
    # ──────────────────────────────────────────────────────────────────────────
    def scrape_all(self, leads: list[dict]) -> list[dict]:
        """
        Iterates over every lead from AGENT 1 and scrapes each website.
        Merges the scraped data back into the lead dict so AGENT 3 receives a
        single enriched object per lead — no data joins required downstream.

        Rate Limiting:
            A randomised courtesy delay (MIN_DELAY_SECONDS to MAX_DELAY_SECONDS)
            is inserted between each request to avoid triggering bot-detection
            systems that monitor request frequency.

        Args:
            leads (list[dict]): Validated lead list from LeadIngestor.ingest_csv().

        Returns:
            list[dict]: Enriched lead dicts with "scraped_title" and
                        "scraped_content" (or "scrape_error") merged in.
        """
        total = len(leads)
        logger.info("=" * 60)
        logger.info("AGENT 2 — Starting batch scrape. Total leads: %d", total)
        logger.info("=" * 60)

        enriched_leads = []

        for index, lead in enumerate(leads, start=1):
            url       = lead.get("Website", "")
            lead_name = lead.get("Name", f"Lead #{index}")

            logger.info("[%d/%d] Processing: %s | %s", index, total, lead_name, url)

            scrape_result = self.scrape_website(url)

            # ── MERGE STRATEGY ────────────────────────────────────────────────
            # Prefix scraped keys to avoid collision with AGENT 1's field names
            # (e.g., lead already has a "url" key from AGENT 1 as "Website").
            enriched_lead = lead.copy()

            if "error" in scrape_result:
                enriched_lead["scrape_error"]   = scrape_result["error"]
                enriched_lead["scraped_title"]   = None
                enriched_lead["scraped_content"] = None
            else:
                enriched_lead["scrape_error"]    = None
                enriched_lead["scraped_title"]   = scrape_result["title"]
                enriched_lead["scraped_content"] = scrape_result["content"]

            enriched_leads.append(enriched_lead)

            # ── COURTESY DELAY ────────────────────────────────────────────────
            # Skip delay after the final lead — no point waiting on exit.
            if index < total:
                delay = random.uniform(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS)
                logger.debug("Courtesy delay: %.2fs before next request.", delay)
                time.sleep(delay)

        # ── BATCH SUMMARY ─────────────────────────────────────────────────────
        success_count = sum(1 for l in enriched_leads if l.get("scrape_error") is None)
        failure_count = total - success_count

        logger.info("-" * 60)
        logger.info(
            "AGENT 2 — Batch complete. "
            "Success: %d | Failed: %d | Total: %d",
            success_count, failure_count, total,
        )
        logger.info("=" * 60)

        return enriched_leads

    # ──────────────────────────────────────────────────────────────────────────
    # PUBLIC METHOD: export_to_json
    # Dump enriched leads to JSON for debugging or file-based handoff to AGENT 3.
    # ──────────────────────────────────────────────────────────────────────────
    def export_to_json(self, enriched_leads: list[dict], output_path: str = "enriched_leads.json") -> None:
        """
        Serializes the enriched lead list to a JSON file.
        Useful for inspecting AGENT 2's output before AGENT 3 processes it.

        Args:
            enriched_leads (list[dict]): Output of scrape_all().
            output_path (str): Destination JSON file path.
        """
        try:
            with open(output_path, mode="w", encoding="utf-8") as f:
                json.dump(enriched_leads, f, indent=4, ensure_ascii=False)
            logger.info("Exported %d enriched leads to '%s'.", len(enriched_leads), output_path)
        except Exception as e:
            logger.error("Failed to export enriched leads: %s", str(e))

    # ──────────────────────────────────────────────────────────────────────────
    # CLEANUP: close
    # Gracefully close the requests.Session when the scout is done.
    # ──────────────────────────────────────────────────────────────────────────
    def close(self) -> None:
        """
        Closes the underlying HTTP session. Call this when the orchestrator
        has finished using the WebScout instance to free socket resources.
        """
        self.session.close()
        logger.info("WebScout session closed.")


# ──────────────────────────────────────────────────────────────────────────────
# STANDALONE ENTRY POINT
# Allows direct testing: `python agent2_scout.py <url>`
# In production, the orchestrator imports WebScout and calls scrape_all().
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    # Accept an optional URL as a CLI argument for quick local testing.
    test_url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"

    scout = WebScout()
    result = scout.scrape_website(test_url)

    print("\n── Scrape Result ──")
    print(json.dumps(result, indent=4))

    scout.close()
