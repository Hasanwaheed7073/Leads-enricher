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
import re
import socket
from typing import Optional
from urllib.parse import urlparse, urljoin

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
    # PRIVATE HELPER: _check_domain_alive
    # Verifies the domain is actually registered and reachable.
    # ──────────────────────────────────────────────────────────────────────────
    def _check_domain_alive(self, url: str) -> bool:
        """
        Checks if the domain behind a URL is actually registered and reachable.

        Two-layer check:
            1. DNS resolution — can we resolve the hostname to an IP?
            2. HTTP HEAD request — does the server respond at all?

        Returns True if the domain is alive (even if it returns 403/500).
        Returns False if DNS fails or the server is completely unreachable.
        """
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname
            if not hostname:
                logger.warning("Cannot extract hostname from URL: %s", url)
                return False

            # ── Layer 1: DNS Resolution ───────────────────────────────────────
            try:
                ip = socket.gethostbyname(hostname)
                logger.debug("DNS resolved: %s → %s", hostname, ip)
            except socket.gaierror:
                logger.warning("DNS resolution FAILED for: %s — domain not registered", hostname)
                return False

            # ── Layer 2: HTTP HEAD request ────────────────────────────────────
            try:
                resp = self.session.head(
                    url,
                    headers=self._get_headers(),
                    timeout=7,
                    allow_redirects=True,
                )
                logger.debug(
                    "HEAD %s → HTTP %d (domain alive)",
                    url, resp.status_code,
                )
                return True
            except requests.exceptions.ConnectionError:
                # DNS resolved but server refused connection — could be
                # a parked domain or firewall. Still "alive" enough to flag.
                logger.warning(
                    "DNS resolved for %s but connection refused — "
                    "domain exists but server is down.",
                    hostname,
                )
                return False
            except requests.exceptions.Timeout:
                logger.warning("HEAD request timed out for %s — server unresponsive.", url)
                return False

        except Exception as e:
            logger.warning("Domain liveness check failed for %s: %s", url, str(e))
            return False

    # ──────────────────────────────────────────────────────────────────────────
    # PRIVATE HELPER: _find_email_on_page
    # Searches for the CSV email on the scraped page content.
    # ──────────────────────────────────────────────────────────────────────────
    def _find_email_on_page(self, soup: BeautifulSoup, email: str, url: str) -> dict:
        """
        Checks if the lead's email address appears on the website.
        Also checks if the email domain matches the website domain.

        Returns:
            dict: {
                "email_found_on_page": bool,
                "email_domain_matches": bool,
            }
        """
        result = {
            "email_found_on_page": False,
            "email_domain_matches": False,
        }

        if not email or "@" not in email:
            return result

        email_lower = email.lower().strip()
        email_domain = email_lower.split("@")[1]

        # ── Check if email domain matches website domain ──────────────────
        try:
            parsed = urlparse(url)
            site_domain = parsed.hostname or ""
            # Strip 'www.' prefix for comparison
            site_domain_clean = site_domain.lower().replace("www.", "")
            email_domain_clean = email_domain.lower()

            # Check if email domain matches or is a subdomain of the site
            if email_domain_clean == site_domain_clean:
                result["email_domain_matches"] = True
            elif site_domain_clean.endswith("." + email_domain_clean):
                result["email_domain_matches"] = True
            elif email_domain_clean.endswith("." + site_domain_clean):
                result["email_domain_matches"] = True

            # Flag known dummy/generic email domains
            DUMMY_DOMAINS = {
                "example.com", "example.org", "example.net",
                "test.com", "test.org", "sample.com",
                "placeholder.com", "fake.com", "dummy.com",
                "email.com", "mail.com", "noemail.com",
            }
            if email_domain_clean in DUMMY_DOMAINS:
                result["email_domain_matches"] = False
                logger.warning(
                    "Email '%s' uses a known dummy domain: %s",
                    email, email_domain_clean,
                )

        except Exception as e:
            logger.debug("Email domain comparison failed: %s", str(e))

        # ── Check if exact email appears in page text ─────────────────────
        page_text = soup.get_text(separator=" ", strip=True).lower()
        if email_lower in page_text:
            result["email_found_on_page"] = True
            logger.debug("Email '%s' found in page text.", email)
            return result

        # ── Check mailto: links ───────────────────────────────────────────
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].lower()
            if href.startswith("mailto:") and email_lower in href:
                result["email_found_on_page"] = True
                logger.debug("Email '%s' found in mailto link.", email)
                return result

        logger.debug("Email '%s' NOT found on page.", email)
        return result

    # ──────────────────────────────────────────────────────────────────────────
    # PRIVATE HELPER: _find_person_on_page
    # Searches for the lead's name in the scraped content.
    # ──────────────────────────────────────────────────────────────────────────
    def _find_person_on_page(
        self, soup: BeautifulSoup, person_name: str, url: str
    ) -> dict:
        """
        Searches the website for the lead's name to verify they are actually
        associated with the business.

        Search targets:
            - Full page text
            - Meta tags (author, description)
            - Structured data (JSON-LD)
            - Common subpages: /about, /team, /contact, /about-us, /our-team

        Returns:
            dict: {
                "person_found_on_page": bool,
                "person_context": str  (e.g., "Found on About page")
            }
        """
        result = {
            "person_found_on_page": False,
            "person_context": "",
        }

        if not person_name or len(person_name.strip()) < 2:
            return result

        name_lower = person_name.lower().strip()
        # Also check first name and last name separately if multi-word
        name_parts = name_lower.split()

        # ── Search main page text ─────────────────────────────────────────
        page_text = soup.get_text(separator=" ", strip=True).lower()
        if name_lower in page_text:
            result["person_found_on_page"] = True
            result["person_context"] = "Found on main page"
            logger.debug("Person '%s' found on main page.", person_name)
            return result

        # ── Search meta tags ──────────────────────────────────────────────
        for meta in soup.find_all("meta"):
            content = (meta.get("content") or "").lower()
            if name_lower in content:
                result["person_found_on_page"] = True
                result["person_context"] = "Found in meta tags"
                logger.debug("Person '%s' found in meta tags.", person_name)
                return result

        # ── Search JSON-LD structured data ────────────────────────────────
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                ld_text = script.string or ""
                if name_lower in ld_text.lower():
                    result["person_found_on_page"] = True
                    result["person_context"] = "Found in structured data"
                    return result
            except Exception:
                pass

        # ── Search common subpages ────────────────────────────────────────
        subpages = ["/about", "/about-us", "/team", "/our-team", "/contact", "/staff"]
        for subpage in subpages:
            try:
                sub_url = urljoin(url, subpage)
                sub_resp = self.session.get(
                    sub_url,
                    headers=self._get_headers(),
                    timeout=7,
                    allow_redirects=True,
                )
                if sub_resp.status_code == 200:
                    try:
                        sub_soup = BeautifulSoup(sub_resp.text, "lxml")
                    except Exception:
                        sub_soup = BeautifulSoup(sub_resp.text, "html.parser")

                    sub_text = sub_soup.get_text(separator=" ", strip=True).lower()
                    if name_lower in sub_text:
                        result["person_found_on_page"] = True
                        result["person_context"] = f"Found on {subpage} page"
                        logger.debug(
                            "Person '%s' found on subpage: %s",
                            person_name, sub_url,
                        )
                        return result
            except Exception:
                continue  # Subpage unreachable — skip silently

        logger.debug("Person '%s' NOT found on website.", person_name)
        return result

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
    # PRIVATE HELPER: _scrape_via_jina
    # ──────────────────────────────────────────────────────────────────────────
    def _scrape_via_jina(self, url: str) -> dict:
        """
        Fallback scraper using Jina Reader API (https://r.jina.ai/).
        Bypasses bot protection and JS-rendering issues.
        Returns a dict with 'title' and 'content' (markdown).
        """
        jina_url = f"https://r.jina.ai/{url}"
        headers = {"Accept": "application/json"}
        try:
            resp = self.session.get(jina_url, headers=headers, timeout=REQUEST_TIMEOUT * 2)
            resp.raise_for_status()
            data = resp.json().get("data", {})
            title = data.get("title") or "No title found"
            content = data.get("content") or "No content extracted"
            return {"title": title, "content": content[:MAX_CONTENT_CHARS]}
        except Exception as e:
            logger.warning("Jina Reader API fallback failed for %s: %s", url, str(e))
            return None

    # ──────────────────────────────────────────────────────────────────────────
    # PUBLIC METHOD: scrape_website
    # Core scraping unit. Self-healing with exponential-backoff retry logic.
    # ──────────────────────────────────────────────────────────────────────────
    def scrape_website(self, url: str, email: str = "", person_name: str = "") -> dict:
        """
        Visits a single URL, extracts structured content, and runs verification
        checks against the lead's email and name.

        Self-Healing Behaviour (per custom_rules.md — Directive 4):
            - Network error / timeout → logs error, returns {"url", "error"}.
            - HTTP 4xx/5xx           → logs warning, returns {"url", "error"}.
            - Auto-retry             → up to MAX_RETRIES with exponential backoff.
            - Parsing failure        → logs warning, returns best-effort result.

        Verification Signals (NEW):
            - domain_alive:          Is the domain registered and reachable?
            - email_found_on_page:   Does the CSV email appear on the website?
            - email_domain_matches:  Does the email domain match the site domain?
            - person_found_on_page:  Does the CSV person name appear on the website?
            - person_context:        Where the person was found (if at all).

        Args:
            url         (str): A validated URL string (output of AGENT 1).
            email       (str): The lead's email address for verification.
            person_name (str): The lead's name for verification.

        Returns:
            dict: Success → {"url", "title", "content", verification signals}
                  Failure → {"url", "error", "domain_alive": False}
        """
        logger.info("Scraping: %s (email=%s, person=%s)", url, email, person_name)

        # ── PRE-FLIGHT: Domain Liveness Check ─────────────────────────────────
        # Before wasting time on retries, verify the domain actually exists.
        domain_alive = self._check_domain_alive(url)

        if not domain_alive:
            logger.error(
                "✗ Domain is DEAD for %s — not registered or completely unreachable.",
                url,
            )
            return {
                "url":                  url,
                "error":                "Domain not registered or unreachable (DNS failed)",
                "domain_alive":         False,
                "email_found_on_page":  False,
                "email_domain_matches": False,
                "person_found_on_page": False,
                "person_context":       "",
            }

        last_error: Optional[str] = None

        # ── RETRY LOOP ────────────────────────────────────────────────────────
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.debug("Attempt %d/%d for: %s", attempt, MAX_RETRIES, url)

                use_jina = False
                fetch_err_msg = ""
                
                try:
                    response = self.session.get(
                        url,
                        headers=self._get_headers(),
                        timeout=REQUEST_TIMEOUT,
                        allow_redirects=True,  # Follow HTTP 301/302 redirects
                    )
                    
                    if response.status_code in (401, 403, 429, 500, 502, 503):
                        use_jina = True
                        fetch_err_msg = f"HTTP {response.status_code}"
                    else:
                        response.raise_for_status()
                except requests.exceptions.RequestException as req_err:
                    use_jina = True
                    fetch_err_msg = str(req_err)
                
                if use_jina:
                    logger.warning("Primary request failed for %s (%s). Attempting Jina Reader fallback...", url, fetch_err_msg)
                    jina_res = self._scrape_via_jina(url)
                    if jina_res:
                        title = jina_res["title"]
                        content = jina_res["content"]
                        # Create a pseudo-soup for verification checks
                        soup = BeautifulSoup(f"<html><head><title>{title}</title></head><body><p>{content}</p></body></html>", "html.parser")
                    else:
                        # If Jina also failed, raise exception to trigger retry loop
                        raise requests.exceptions.RequestException(f"Primary fetch failed ({fetch_err_msg}) and Jina fallback also failed.")
                else:
                    # ── SUCCESSFUL PRIMARY RESPONSE ───────────────────────────────
                    logger.debug(
                        "HTTP %d received for: %s (%.2f KB)",
                        response.status_code,
                        url,
                        len(response.content) / 1024,
                    )

                    # ── HTML PARSING ──────────────────────────────────────────────
                    try:
                        soup = BeautifulSoup(response.text, "lxml")
                    except Exception:
                        soup = BeautifulSoup(response.text, "html.parser")

                    # ── CONTENT EXTRACTION ────────────────────────────────────────
                    title   = self._extract_title(soup)
                    content = self._extract_paragraph_content(soup)
                    
                    # ── FALLBACK FOR INSUFFICIENT CONTENT (JS SPA) ────────────────
                    if len(content.strip()) < 200:
                        logger.info("Primary scrape yielded insufficient content (< 200 chars) for %s. Attempting Jina Reader...", url)
                        jina_res = self._scrape_via_jina(url)
                        if jina_res and len(jina_res["content"]) > len(content.strip()):
                            title = jina_res["title"]
                            content = jina_res["content"]
                            soup = BeautifulSoup(f"<html><head><title>{title}</title></head><body><p>{content}</p></body></html>", "html.parser")

                # ── VERIFICATION CHECKS ───────────────────────────────────────
                email_result  = self._find_email_on_page(soup, email, url)
                person_result = self._find_person_on_page(soup, person_name, url)

                logger.info(
                    "✓ Scraped: %s | Title: '%s' | Content: %d chars | "
                    "Email on page: %s | Email domain match: %s | "
                    "Person on page: %s",
                    url, title, len(content),
                    email_result["email_found_on_page"],
                    email_result["email_domain_matches"],
                    person_result["person_found_on_page"],
                )

                return {
                    "url":                  url,
                    "title":                title,
                    "content":              content,
                    "domain_alive":         True,
                    "email_found_on_page":  email_result["email_found_on_page"],
                    "email_domain_matches": email_result["email_domain_matches"],
                    "person_found_on_page": person_result["person_found_on_page"],
                    "person_context":       person_result["person_context"],
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
        # Domain is alive (passed DNS check) but we couldn't scrape content.
        # Return an error — Agent 3 will NOT get fake content to infer from.
        logger.error(
            "✗ Scrape failed for %s after %d attempts. Last error: %s",
            url, MAX_RETRIES, last_error,
        )
        return {
            "url":                  url,
            "error":                f"Website unreachable after {MAX_RETRIES} attempts: {last_error}",
            "domain_alive":         True,  # DNS resolved, but scrape failed
            "email_found_on_page":  False,
            "email_domain_matches": False,
            "person_found_on_page": False,
            "person_context":       "",
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

            email       = lead.get("Email", "")
            person_name = lead.get("Name", "")
            scrape_result = self.scrape_website(url, email=email, person_name=person_name)

            # ── MERGE STRATEGY ────────────────────────────────────────────────
            # Prefix scraped keys to avoid collision with AGENT 1's field names
            # (e.g., lead already has a "url" key from AGENT 1 as "Website").
            enriched_lead = lead.copy()

            # ── Merge verification signals ────────────────────────────────────
            enriched_lead["domain_alive"]         = scrape_result.get("domain_alive", False)
            enriched_lead["email_found_on_page"]  = scrape_result.get("email_found_on_page", False)
            enriched_lead["email_domain_matches"] = scrape_result.get("email_domain_matches", False)
            enriched_lead["person_found_on_page"] = scrape_result.get("person_found_on_page", False)
            enriched_lead["person_context"]       = scrape_result.get("person_context", "")

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
