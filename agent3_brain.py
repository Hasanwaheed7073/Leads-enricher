"""
================================================================================
LEAD SNIPER — AGENT 3: BRAIN (QUALIFIER, SCORER & PITCHER)
================================================================================
Responsibility:
    Receive an enriched lead dict (AGENT 1 context + AGENT 2 scraped content),
    run TWO-PHASE AI processing:
        Phase 1: Qualify the lead against a target industry and score it (1–10).
        Phase 2: Generate a personalized 3-sentence cold outreach pitch.
    Supports automatic API key rotation on 429 rate-limit errors.

Architecture Reference:
    .antigravity_env/agents.md   — Multi-Agent system contract
    .antigravity_env/custom_rules.md — Core directives (Zero-Cost, Self-Healing)

Design Principles (per custom_rules.md):
    - ZERO-COST: Uses any OpenAI-compatible REST API (Grok, Llama, OpenRouter,
      Groq, Together AI, local Ollama, etc.). No paid SDK required.
    - SELF-HEALING: AI calls wrapped in try/except with key rotation + retry
      logic + 3-layer JSON repair. Malformed responses are caught gracefully.
    - SURGICAL: Handles ONLY qualification, scoring, and pitch generation.
    - SELLABLE QUALITY: Two-phase prompt pipeline, key rotation, full audit
      logging, modular class importable by any orchestrator.

Dependencies (free & open-source):
    pip install requests   (already installed for AGENT 2)

    Compatible API Providers (all have free tiers):
        - Groq:       https://console.groq.com/keys
        - OpenRouter:  https://openrouter.ai/keys
        - Together AI: https://api.together.xyz
        - Local Ollama: http://localhost:11434/v1

Author:     Lead Architect via Antigravity Engine
Version:    3.0.0
================================================================================
"""

import json
import logging
import re
import time
import random
from typing import Optional

# ──────────────────────────────────────────────────────────────────────────────
# HTTP CLIENT
# Uses `requests` (already installed for AGENT 2). No proprietary SDK needed.
# Any OpenAI-compatible REST endpoint works: Grok, Llama, Groq, Ollama, etc.
# ──────────────────────────────────────────────────────────────────────────────
import requests

# ──────────────────────────────────────────────────────────────────────────────
# LOGGING CONFIGURATION
# Mirrors AGENT 1 & AGENT 2 patterns for a unified log trail.
# ──────────────────────────────────────────────────────────────────────────────
LOG_FILE = "agent3_brain.log"

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger("AGENT_3_BRAIN")


# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────

# Default model — override via parameter or environment variable.
# Examples: "grok-3-mini", "llama-3.1-70b", "mixtral-8x7b", "gpt-4o-mini"
DEFAULT_MODEL = "llama-3.3-70b-versatile"

# Default API base URL — override via parameter or environment variable.
# This should point to any OpenAI-compatible /v1/chat/completions endpoint.
# Examples:
#   Grok:        https://api.x.ai/v1/chat/completions
#   Groq:        https://api.groq.com/openai/v1/chat/completions
#   OpenRouter:  https://openrouter.ai/api/v1/chat/completions
#   Together AI: https://api.together.xyz/v1/chat/completions
#   Ollama:      http://localhost:11434/v1/chat/completions
DEFAULT_API_BASE_URL = "https://api.x.ai/v1/chat/completions"

# AI request timeout in seconds.
AI_REQUEST_TIMEOUT = 30

# Auto-retry settings for transient AI API errors (429, 503, network blips).
# With key rotation, each "retry" may use a different API key, maximizing
# throughput across multiple free-tier accounts.
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # Exponential: 2s, 4s, 8s

# Phase-specific fallback responses returned when the AI fails after all retries.
FALLBACK_QUALIFY = {
    "is_valid": False,
    "score":    0,
    "summary":  "Error.",
    "category": "Unknown",
}

FALLBACK_PITCH = {
    "pitch": "Error generating pitch.",
}

# Generation parameters — low temperature = focused, structured output.
# High temperature would introduce creative drift in a JSON-constrained task.
DEFAULT_TEMPERATURE = 0.4
DEFAULT_MAX_TOKENS  = 512  # Generous for 3-sentence pitch + summary


# ──────────────────────────────────────────────────────────────────────────────
# CLASS: LeadBrain
# ──────────────────────────────────────────────────────────────────────────────
class LeadBrain:
    """
    AGENT 3 — Brain (Qualifier, Scorer & Pitcher)

    Two-phase AI pipeline with automatic API key rotation:

        Phase 1 — qualify_and_summarize():
            Checks if the lead matches a target industry, scores (1–10),
            and generates a 2-sentence business summary.

        Phase 2 — generate_pitch():
            Uses the qualified summary to write a hyper-personalized
            3-sentence cold outreach email.

    API Key Rotation:
        All methods accept `api_keys` as a list[str]. If a key hits a 429
        (rate limit), the system automatically rotates to the next key and
        retries — maximizing throughput across multiple free-tier accounts.

    Usage (standalone):
        brain = LeadBrain()
        phase1 = brain.qualify_and_summarize(
            lead_data       = {...},
            scraped_data    = {...},
            target_industry = "HVAC",
            api_keys        = ["key1", "key2"],
            api_base_url    = "https://api.x.ai/v1/chat/completions",
            model_name      = "grok-3-mini",
        )

        if phase1["is_valid"]:
            phase2 = brain.generate_pitch(
                lead_data    = {...},
                summary      = phase1["summary"],
                api_keys     = ["key1", "key2"],
                api_base_url = "https://api.x.ai/v1/chat/completions",
                model_name   = "grok-3-mini",
            )

    Usage (full pipeline):
        from agent1_ingestor import LeadIngestor
        from agent2_scout    import WebScout
        from agent3_brain    import LeadBrain

        leads    = LeadIngestor().ingest_csv("leads.csv")
        scout    = WebScout()
        enriched = scout.scrape_all(leads)
        brain    = LeadBrain()

        for lead in enriched:
            p1 = brain.qualify_and_summarize(lead, lead, "HVAC", api_keys=["k1","k2"])
            lead["is_valid"] = p1["is_valid"]
            lead["score"]    = p1["score"]
            lead["summary"]  = p1["summary"]

            if p1["is_valid"]:
                p2 = brain.generate_pitch(lead, p1["summary"], api_keys=["k1","k2"])
                lead["pitch"] = p2["pitch"]
    """

    def __init__(self):
        # ── KEY ROTATION STATE ────────────────────────────────────────────────
        # Tracks which API key in the list to use next. Shared across all
        # method calls on this instance so rotation persists across leads.
        self._active_key_index = 0

        logger.info(
            "LeadBrain v3.0 initialized. Two-phase pipeline | "
            "API key rotation enabled | Default model: %s",
            DEFAULT_MODEL,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # PRIVATE HELPER: _get_next_key
    # Rotates to the next API key in the pool.
    # ──────────────────────────────────────────────────────────────────────────
    def _get_next_key(self, api_keys: list[str]) -> str:
        """
        Returns the current active key and advances the index for next call.
        Wraps around to the beginning when the end of the list is reached.

        Args:
            api_keys (list[str]): Pool of API keys to rotate through.

        Returns:
            str: The current active API key.
        """
        if not api_keys:
            return ""
        key = api_keys[self._active_key_index % len(api_keys)]
        return key

    def _rotate_key(self, api_keys: list[str]) -> str:
        """
        Increments the active key index and returns the NEW key.
        Called when a 429 or failure is detected on the current key.

        Args:
            api_keys (list[str]): Pool of API keys to rotate through.

        Returns:
            str: The next API key in the rotation.
        """
        self._active_key_index = (self._active_key_index + 1) % len(api_keys)
        new_key = api_keys[self._active_key_index]
        logger.info(
            "🔄 API key rotated → Key #%d (ending ...%s)",
            self._active_key_index + 1,
            new_key[-6:] if len(new_key) > 6 else "***",
        )
        return new_key

    # ──────────────────────────────────────────────────────────────────────────
    # PRIVATE HELPER: _parse_json_response
    # 3-layer self-healing JSON extractor — reused by both phases.
    # ──────────────────────────────────────────────────────────────────────────
    def _parse_json_response(self, raw_text: str) -> Optional[dict]:
        """
        Parses the AI's raw text output into a Python dict.

        Self-Healing JSON Extraction (3 layers):
            Layer 1: Direct json.loads() on the raw text.
            Layer 2: Strip markdown code fences (```json ... ```) and retry.
            Layer 3: Regex-extract the first {...} block found in the text.

        If all layers fail, returns None (caller handles fallback).

        Args:
            raw_text (str): The raw string returned by the AI model.

        Returns:
            dict | None: Parsed response, or None on failure.
        """
        if not raw_text or not raw_text.strip():
            logger.warning("AI returned an empty response.")
            return None

        text = raw_text.strip()

        # ── Layer 1: Try parsing as-is ─────────────────────────────────────
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            logger.debug("Layer 1 JSON parse failed. Trying markdown strip...")

        # ── Layer 2: Strip markdown code fences ────────────────────────────
        stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.DOTALL).strip()
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            logger.debug("Layer 2 JSON parse failed. Trying regex extraction...")

        # ── Layer 3: Regex extract first JSON object block ──────────────────
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                logger.debug("Layer 3 JSON extraction failed.")

        logger.warning("All JSON parse layers failed. Raw output: %s", text[:300])
        return None

    # ──────────────────────────────────────────────────────────────────────────
    # PRIVATE METHOD: _call_api
    # Single AI call using a generic OpenAI-compatible REST endpoint.
    # Now accepts a system_prompt parameter so each phase can set its own role.
    # ──────────────────────────────────────────────────────────────────────────
    def _call_api(
        self,
        system_prompt: str,
        user_prompt:   str,
        api_key:       str,
        api_base_url:  str,
        model_name:    str,
    ) -> Optional[str]:
        """
        Sends a prompt to any OpenAI-compatible /v1/chat/completions endpoint.

        Args:
            system_prompt (str): The system role instructions.
            user_prompt   (str): The user-facing data and task.
            api_key       (str): Bearer token for the API provider.
            api_base_url  (str): Full URL to /v1/chat/completions.
            model_name    (str): Model identifier (e.g., "grok-3-mini").

        Returns:
            str | None: Raw AI response text, or None on failure.
        """
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
        }

        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature":  DEFAULT_TEMPERATURE,
            "max_tokens":   DEFAULT_MAX_TOKENS,
        }

        response = requests.post(
            api_base_url,
            json=payload,
            headers=headers,
            timeout=AI_REQUEST_TIMEOUT,
        )
        response.raise_for_status()

        data = response.json()

        try:
            text = data["choices"][0]["message"]["content"]
            return text
        except (KeyError, IndexError, TypeError) as parse_err:
            logger.warning(
                "API response structure unexpected: %s | Raw: %s",
                parse_err,
                json.dumps(data)[:300],
            )
            return None

    # ──────────────────────────────────────────────────────────────────────────
    # PRIVATE METHOD: _call_with_rotation
    # Core retry engine with API key rotation on 429 errors.
    # Both Phase 1 and Phase 2 delegate to this method.
    # ──────────────────────────────────────────────────────────────────────────
    def _call_with_rotation(
        self,
        system_prompt: str,
        user_prompt:   str,
        api_keys:      list[str],
        api_base_url:  str,
        model_name:    str,
        lead_name:     str,
    ) -> Optional[dict]:
        """
        Executes an AI call with automatic key rotation and retry logic.

        Rotation Logic:
            - On HTTP 429 (rate limit): rotate to the next API key, retry.
            - On HTTP 400/401/403: unrecoverable, stop retrying and return None.
            - On network/other error: retry with backoff (same key).
            - Up to MAX_RETRIES total attempts across all keys.

        Args:
            system_prompt (str):       System role instructions.
            user_prompt   (str):       User-facing data and task.
            api_keys      (list[str]): Pool of API keys to rotate through.
            api_base_url  (str):       Full URL to /v1/chat/completions.
            model_name    (str):       Model identifier.
            lead_name     (str):       Lead name for logging context.

        Returns:
            dict | None: Parsed JSON response, or None on total failure.
        """
        last_error: Optional[str] = None

        for attempt in range(1, MAX_RETRIES + 1):
            current_key = self._get_next_key(api_keys)

            try:
                logger.debug(
                    "AI call attempt %d/%d for: %s (Key #%d, ending ...%s @ %s)",
                    attempt, MAX_RETRIES, lead_name,
                    (self._active_key_index % len(api_keys)) + 1,
                    current_key[-6:] if len(current_key) > 6 else "***",
                    api_base_url,
                )

                raw_text = self._call_api(
                    system_prompt, user_prompt,
                    current_key, api_base_url, model_name,
                )

                if raw_text is None:
                    raise ValueError("AI returned no text content.")

                logger.debug("Raw AI response received (%d chars).", len(raw_text))

                # ── 3-layer JSON parsing ──────────────────────────────────────
                result = self._parse_json_response(raw_text)

                if result is None:
                    raise ValueError(
                        f"JSON repair failed after 3 layers. Raw: {raw_text[:200]}"
                    )

                return result

            except requests.exceptions.HTTPError as http_err:
                status_code = http_err.response.status_code if http_err.response else 0
                last_error  = f"HTTP {status_code}: {http_err}"

                # ── KEY ROTATION ON ANY 4xx/5xx ERROR ────────────────────
                # Rotate to the next API key on rate limits, auth errors,
                # server errors — any HTTP failure may be key-specific.
                if len(api_keys) > 1:
                    old_key_num = (self._active_key_index % len(api_keys)) + 1
                    logger.warning(
                        "HTTP %d for '%s' on Key #%d. Rotating to next key...",
                        status_code, lead_name, old_key_num,
                    )
                    self._rotate_key(api_keys)

                    # Surface the rotation event in the Streamlit UI so the
                    # user can visually track key switches in real-time.
                    try:
                        import streamlit as st
                        st.warning(
                            f"⚠️ API Key #{old_key_num} hit HTTP {status_code} — "
                            f"rotated to Key #{(self._active_key_index % len(api_keys)) + 1}",
                            icon="🔄",
                        )
                    except Exception:
                        pass  # Not running inside Streamlit — ignore silently.

                    wait = RETRY_BACKOFF_BASE + random.uniform(0.5, 1.5)
                    time.sleep(wait)
                else:
                    logger.warning(
                        "HTTP %d for '%s' — only 1 key available, no rotation possible.",
                        status_code, lead_name,
                    )

            except requests.exceptions.RequestException as req_err:
                last_error = str(req_err)
                logger.warning(
                    "Network error for '%s': %s (Attempt %d/%d)",
                    lead_name, last_error, attempt, MAX_RETRIES,
                )

            except Exception as general_err:
                last_error = str(general_err)
                logger.warning(
                    "Unexpected error for '%s': %s (Attempt %d/%d)",
                    lead_name, last_error, attempt, MAX_RETRIES,
                )

            # ── EXPONENTIAL BACKOFF ───────────────────────────────────────────
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF_BASE ** attempt + random.uniform(0.1, 0.9)
                logger.debug("Waiting %.1fs before retry %d...", wait, attempt + 1)
                time.sleep(wait)

        # ── ALL KEYS EXHAUSTED ────────────────────────────────────────────────
        exhaustion_msg = (
            f"All API keys exhausted for '{lead_name}' after {MAX_RETRIES} attempts. "
            f"Please wait 60 seconds and retry. Last error: {last_error}"
        )
        logger.error("✗ %s", exhaustion_msg)

        # Surface the exhaustion message in the Streamlit UI.
        try:
            import streamlit as st
            st.error(f"🚨 {exhaustion_msg}", icon="🔑")
        except Exception:
            pass

        return None

    # ══════════════════════════════════════════════════════════════════════════
    #   PHASE 1: QUALIFY & SUMMARIZE
    # ══════════════════════════════════════════════════════════════════════════

    def qualify_and_summarize(
        self,
        lead_data:       dict,
        scraped_data:    dict,
        target_industry: str,
        api_keys:        list[str],
        api_base_url:    str = DEFAULT_API_BASE_URL,
        model_name:      str = DEFAULT_MODEL,
        is_career_coaching: bool = False,
    ) -> dict:
        """
        Phase 1 — Industry Qualification, Scoring & Summarization.

        Sends the lead + scraped context to the AI and asks:
            1. Does this business match the target industry?
            2. If yes, score it 1–10.
            3. Generate a 2-sentence business summary.

        This phase acts as a strict FILTER — leads that don't match the
        target industry (e.g., a marketing agency found in an HVAC list)
        are flagged as invalid and skip Phase 2 entirely, saving API quota.

        API Key Rotation:
            If any key hits a 429, the system auto-rotates to the next key
            in the `api_keys` list and retries (up to MAX_RETRIES total).

        Args:
            lead_data       (dict):       Validated lead from AGENT 1.
            scraped_data    (dict):       Enriched lead from AGENT 2.
            target_industry (str):        The industry to qualify against (e.g., "HVAC").
            api_keys        (list[str]):  Pool of API keys for rotation.
            api_base_url    (str):        Full URL to /v1/chat/completions.
            model_name      (str):        Model identifier.

        Returns:
            dict: {"is_valid": bool, "score": int (1–10), "summary": str}
            On failure: {"is_valid": False, "score": 0, "summary": "Error."}
        """
        lead_name = lead_data.get("Name", "Unknown Lead")

        logger.info("=" * 60)
        logger.info("AGENT 3 — Phase 1: Qualify & Summarize → %s", lead_name)
        logger.info("=" * 60)

        # ── PRE-FLIGHT: API keys validation ───────────────────────────────────
        if not api_keys or not any(k.strip() for k in api_keys):
            logger.critical(
                "CRITICAL — No API keys provided for lead: %s.",
                lead_name,
            )
            return FALLBACK_QUALIFY.copy()

        # ── PRE-FLIGHT: Check for scrape errors ───────────────────────────────
        if scraped_data.get("scrape_error"):
            logger.warning(
                "Lead '%s' has a scrape error: %s.",
                lead_name,
                scraped_data["scrape_error"],
            )

        # ── PRE-AI HARD FILTERS ───────────────────────────────────────────────
        # These checks run BEFORE making any AI calls, saving API quota on
        # leads that are clearly invalid based on verifiable signals.

        domain_alive         = scraped_data.get("domain_alive", True)
        email_domain_matches = scraped_data.get("email_domain_matches", True)
        email_found_on_page  = scraped_data.get("email_found_on_page", False)
        person_found_on_page = scraped_data.get("person_found_on_page", False)
        person_context       = scraped_data.get("person_context", "")

        # HARD FILTER 1: Dead domain = instant disqualification.
        # If the domain doesn't even exist, this is fake/stale data.
        if not domain_alive:
            logger.warning(
                "HARD FILTER: '%s' — Domain is DEAD. Auto-disqualified.",
                lead_name,
            )
            return {
                "is_valid": False,
                "score":    0,
                "summary":  (
                    f"DISQUALIFIED — Website domain is not registered or unreachable. "
                    f"Cannot verify this is a real {target_industry} business."
                ),
            }

        # ── BUILD CLEAN CONTEXT ───────────────────────────────────────────────
        # Strip internal pipeline keys irrelevant to the AI.
        clean_lead = {
            k: v for k, v in lead_data.items()
            if k not in (
                "scrape_error", "scraped_title", "scraped_content",
                "domain_alive", "email_found_on_page", "email_domain_matches",
                "person_found_on_page", "person_context",
            )
            and v  # Drop empty/None fields to reduce token cost
        }

        clean_scraped = {
            "page_title":   scraped_data.get("scraped_title") or scraped_data.get("title", "N/A"),
            "page_content": scraped_data.get("scraped_content") or scraped_data.get("content", "N/A"),
        }

        # ── VERIFICATION CONTEXT (passed to AI) ───────────────────────────────
        verification_context = {
            "domain_alive":           domain_alive,
            "website_was_scrapeable": scraped_data.get("scrape_error") is None,
            "email_found_on_page":    email_found_on_page,
            "email_domain_matches":   email_domain_matches,
            "person_found_on_page":   person_found_on_page,
            "person_context":         person_context,
        }

        # ── SYSTEM PROMPT ─────────────────────────────────────────────────────
        if is_career_coaching:
            system_prompt = (
                "You are an expert Career Coaching industry analyst and lead verification specialist. "
                "Your job is to determine if the provided data belongs to a REAL, ACTIVE Career Coach "
                "or coaching professional. Focus on verifying if the data is true or false based on the signals. "
                "You ALWAYS respond with raw JSON only — no markdown, no code fences, no explanation."
            )
            
            user_prompt = f"""Analyze ALL signals to verify if this lead is a REAL Career Coach or related professional.

Lead data:
{json.dumps(clean_lead, indent=2)}

Scraped website context:
{json.dumps(clean_scraped, indent=2)}

Verification signals:
{json.dumps(verification_context, indent=2)}

=== CRITICAL VERIFICATION RULES ===
1. Verify if the person or company offers career coaching, executive coaching, or professional development services.
2. If website_was_scrapeable is false → the website could not be loaded. Maximum score: 2. You MUST crawl the website to qualify the lead.
3. If the data is clearly dummy or completely unrelated, score low.

=== SCORING RUBRIC ===
- Score 9-10: Working website with strong evidence of Career Coaching services.
- Score 7-8: Working website, likely a Career Coach based on the data.
- Score 5-6: Plausible coach or related consulting professional.
- Score 1-4: Insufficient evidence or unrelated business.
- Score 0: Fake data or dead domain.

Set is_valid to true ONLY if score is 5 or above.
Also determine a short, 1-3 word "category" for this lead.

Return ONLY a raw JSON object:
{{"is_valid": true, "score": 8, "summary": "one sentence explaining the score, mentioning which checks passed/failed", "category": "Executive Coach"}}"""
        else:
            system_prompt = (
                "You are an expert HVAC industry analyst and lead verification specialist. "
                "Your job is to determine if a business is a REAL, ACTIVE HVAC contractor "
                "with a working website. You must cross-reference ALL verification signals. "
                "Do NOT qualify based on company name alone — you need real evidence. "
                "You ALWAYS respond with raw JSON only — no markdown, no code fences, no explanation."
            )

            # ── USER PROMPT ───────────────────────────────────────────────────────
            # Multi-signal qualification with strict verification requirements.
            user_prompt = f"""Analyze ALL signals to determine if this lead is a REAL, VERIFIED business in the "{target_industry}" industry.

Lead data:
{json.dumps(clean_lead, indent=2)}

Scraped website context:
{json.dumps(clean_scraped, indent=2)}

Verification signals:
{json.dumps(verification_context, indent=2)}

=== CRITICAL VERIFICATION RULES (FOLLOW STRICTLY) ===

1. WEBSITE MUST BE REAL:
   - If website_was_scrapeable is false → the website could not be loaded. Maximum score: 2.
   - If the page content is generic, parked, or "coming soon" → Maximum score: 3.
   - Having an HVAC-sounding company name is NOT ENOUGH to qualify without a working website.

2. EMAIL MUST BE VERIFIABLE:
   - If email_domain_matches is false AND email_found_on_page is false → the email is likely fake or from a purchased list. Penalize by -3 points.
   - If the email uses a known dummy domain (example.com, test.com, etc.) → Maximum score: 1.
   - If email domain matches the website domain → this is a positive signal.

3. PERSON MUST BE FINDABLE:
   - If person_found_on_page is false → the person named in the CSV was NOT found on the website. Penalize by -2 points.
   - If person_found_on_page is true → this is a strong positive signal.

4. WEBSITE CONTENT MUST CONFIRM INDUSTRY:
   - The page content must mention HVAC-related services: heating, cooling, AC, furnace, etc.
   - Generic "home services" without specific HVAC mentions → Score 3-4 maximum.
   - Clear HVAC content with service descriptions → Score 7-10.

=== SCORING RUBRIC ===
- Score 9-10: Working website with clear HVAC content + email domain matches + person found on site
- Score 7-8: Working website with clear HVAC content but email/person not fully verified
- Score 5-6: Working website with HVAC-adjacent content (plumbing, home services)
- Score 3-4: Working website but weak/generic content, or significant verification failures
- Score 1-2: Website doesn't work OR email is clearly fake
- Score 0: Domain is dead, email is dummy, no real signals

Set is_valid to true ONLY if score is 5 or above (stricter threshold).
Also, based on the specific services mentioned (e.g., Commercial, Residential, Plumbing, Roofing), determine a short, 1-3 word "category" for this lead.

Return ONLY a raw JSON object:
{{"is_valid": true, "score": 8, "summary": "one sentence explaining the score, mentioning which checks passed/failed", "category": "Commercial HVAC"}}"""

        # ── CALL AI WITH KEY ROTATION ─────────────────────────────────────────
        result = self._call_with_rotation(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            api_keys=api_keys,
            api_base_url=api_base_url,
            model_name=model_name,
            lead_name=lead_name,
        )

        if result is None:
            logger.error("Phase 1 failed for '%s'. Returning fallback.", lead_name)
            return FALLBACK_QUALIFY.copy()

        # ── VALIDATE & COERCE RESPONSE ────────────────────────────────────────
        is_valid = result.get("is_valid")
        if isinstance(is_valid, str):
            is_valid = is_valid.lower() in ("true", "yes", "1")
        is_valid = bool(is_valid)

        raw_score = result.get("score")
        try:
            score = int(raw_score) if raw_score not in (None, "", 0) else 0
            score = max(0, min(10, score))  # Clamp to 0–10
        except (TypeError, ValueError):
            score = 0

        # ── GUARD: Flag unverifiable scores ────────────────────────────────
        if score == 0:
            score = "Unverified"
            summary = "Could not be verified — manual review needed."
        else:
            summary = str(result.get("summary", "Error.")).strip() or "Error."

        # ── POST-AI SCORE CEILING ENFORCEMENT ─────────────────────────────────
        # Even if the AI over-scores, hard caps prevent false positives.
        if isinstance(score, int):

            # CAP 1: Website content was not scrapeable → max 2
            if scraped_data.get("scrape_error") is not None:
                if score > 2:
                    logger.warning(
                        "SCORE CAP: '%s' capped from %d to 2 — website was not scrapeable.",
                        lead_name, score,
                    )
                    score = 2
                    summary += " [Capped: website not scrapeable]"

            if not is_career_coaching:
                # CAP 2: Email doesn't match AND not on page → max 4
                if not email_domain_matches and not email_found_on_page:
                    if score > 4:
                        logger.warning(
                            "SCORE CAP: '%s' capped from %d to 4 — email not verified.",
                            lead_name, score,
                        )
                        score = 4
                        summary += " [Capped: email unverified]"

                # CAP 3: Person not found on website → max 6
                if not person_found_on_page:
                    if score > 6:
                        logger.warning(
                            "SCORE CAP: '%s' capped from %d to 6 — person not found on website.",
                            lead_name, score,
                        )
                        score = 6
                        summary += " [Capped: person not on website]"

            # Enforce is_valid based on final capped score
            is_valid = score >= 5

        category = str(result.get("category", "Unknown")).strip() or "Unknown"

        logger.info(
            "✓ Phase 1 → %s | Valid: %s | Score: %s/10 | Category: %s | Summary: %.80s...",
            lead_name, is_valid, score, category, summary,
        )

        return {"is_valid": is_valid, "score": score, "summary": summary, "category": category}

    # ══════════════════════════════════════════════════════════════════════════
    #   PHASE 2: GENERATE PITCH
    # ══════════════════════════════════════════════════════════════════════════

    def generate_pitch(
        self,
        lead_data:    dict,
        summary:      str,
        api_keys:     list[str],
        api_base_url: str = DEFAULT_API_BASE_URL,
        model_name:   str = DEFAULT_MODEL,
        is_career_coaching: bool = False,
    ) -> dict:
        """
        Phase 2 — Personalized Pitch Generation.

        Uses the qualified summary from Phase 1 to write a hyper-personalized
        3-sentence cold outreach email pitch.

        Only called for leads that passed Phase 1 qualification (is_valid=True).
        This two-phase approach saves API quota by skipping irrelevant leads.

        API Key Rotation:
            Same rotation logic as Phase 1 — 429s trigger auto-swap.

        Args:
            lead_data    (dict):       Validated lead from AGENT 1.
            summary      (str):        Business summary from Phase 1.
            api_keys     (list[str]):  Pool of API keys for rotation.
            api_base_url (str):        Full URL to /v1/chat/completions.
            model_name   (str):        Model identifier.

        Returns:
            dict: {"pitch": str}
            On failure: {"pitch": "Error generating pitch."}
        """
        lead_name = lead_data.get("Name", "Unknown Lead")
        company   = lead_data.get("Company", "Unknown Company")

        logger.info("─" * 60)
        logger.info("AGENT 3 — Phase 2: Generate Pitch → %s (%s)", lead_name, company)
        logger.info("─" * 60)

        # ── PRE-FLIGHT: API keys validation ───────────────────────────────────
        if not api_keys or not any(k.strip() for k in api_keys):
            logger.critical("CRITICAL — No API keys provided for pitch generation.")
            return FALLBACK_PITCH.copy()

        # ── SYSTEM PROMPT ─────────────────────────────────────────────────────
        system_prompt = (
            "You are an expert B2B SDR (Sales Development Representative) "
            "with 10 years of experience writing high-converting cold outreach emails. "
            "You write concise, personalized, conversational pitches. "
            "You ALWAYS respond with raw JSON only — no markdown, no code fences, no explanation."
        )

        # ── USER PROMPT ───────────────────────────────────────────────────────
        if is_career_coaching:
            user_prompt = f"""Write a 3-sentence personalized cold email pitch to {lead_name} at {company}, who is a Career Coach.

Use this business summary for context:
"{summary}"

Rules for the pitch:
- Sentence 1: Open by referencing a SPECIFIC detail from the summary (not generic flattery).
- Sentence 2: Clearly state the value proposition — what you can do to help them grow their coaching business.
- Sentence 3: End with a soft, low-friction call-to-action.
- Keep it conversational, not corporate.

Return ONLY a raw JSON object with one key:
{{"pitch": "Your three sentence pitch here."}}"""
        else:
            user_prompt = f"""Write a 3-sentence personalized cold email pitch to {lead_name} at {company}.

Use this business summary for context:
"{summary}"

Rules for the pitch:
- Sentence 1: Open by referencing a SPECIFIC detail from the summary (not generic flattery).
- Sentence 2: Clearly state the value proposition — what you can do for THEM specifically.
- Sentence 3: End with a soft, low-friction call-to-action.
- Keep it conversational, not corporate.

Return ONLY a raw JSON object with one key:
{{"pitch": "Your three sentence pitch here."}}"""

        # ── CALL AI WITH KEY ROTATION ─────────────────────────────────────────
        result = self._call_with_rotation(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            api_keys=api_keys,
            api_base_url=api_base_url,
            model_name=model_name,
            lead_name=lead_name,
        )

        if result is None:
            logger.error("Phase 2 failed for '%s'. Returning fallback.", lead_name)
            return FALLBACK_PITCH.copy()

        pitch = str(result.get("pitch", "Error generating pitch.")).strip()
        if not pitch:
            pitch = "Error generating pitch."

        logger.info(
            "✓ Phase 2 → %s | Pitch: %.100s...",
            lead_name, pitch,
        )

        return {"pitch": pitch}

    # ──────────────────────────────────────────────────────────────────────────
    # PUBLIC METHOD: process_all
    # Batch processor — runs both phases for every lead in the enriched list.
    # ──────────────────────────────────────────────────────────────────────────
    def process_all(
        self,
        enriched_leads:  list[dict],
        target_industry: str,
        api_keys:        list[str],
        api_base_url:    str = DEFAULT_API_BASE_URL,
        model_name:      str = DEFAULT_MODEL,
    ) -> list[dict]:
        """
        Two-phase batch processor for all enriched leads.

        For each lead:
            1. Phase 1: qualify_and_summarize() — filter + score + summarize.
            2. Phase 2: generate_pitch() — only if Phase 1 says is_valid=True.

        Args:
            enriched_leads  (list[dict]): Output of AGENT 2's scrape_all().
            target_industry (str):        Industry to qualify against.
            api_keys        (list[str]):  Pool of API keys for rotation.
            api_base_url    (str):        Full URL to /v1/chat/completions.
            model_name      (str):        Model identifier.

        Returns:
            list[dict]: Final lead dicts with qualification, score, and pitch merged in.
        """
        total = len(enriched_leads)
        logger.info("=" * 60)
        logger.info(
            "AGENT 3 — Starting two-phase batch. Total leads: %d | Industry: %s",
            total, target_industry,
        )
        logger.info("=" * 60)

        final_leads = []

        for index, lead in enumerate(enriched_leads, start=1):
            lead_name = lead.get("Name", f"Lead #{index}")
            logger.info("[%d/%d] Processing: %s", index, total, lead_name)

            final_lead = lead.copy()

            # ── PHASE 1 ──────────────────────────────────────────────────────
            p1 = self.qualify_and_summarize(
                lead_data=lead,
                scraped_data=lead,
                target_industry=target_industry,
                api_keys=api_keys,
                api_base_url=api_base_url,
                model_name=model_name,
            )

            final_lead["is_valid"] = p1["is_valid"]
            final_lead["score"]    = p1["score"]
            final_lead["summary"]  = p1["summary"]

            # ── PHASE 2 (only for valid leads) ────────────────────────────────
            if p1["is_valid"]:
                p2 = self.generate_pitch(
                    lead_data=lead,
                    summary=p1["summary"],
                    api_keys=api_keys,
                    api_base_url=api_base_url,
                    model_name=model_name,
                )
                final_lead["pitch"] = p2["pitch"]
            else:
                final_lead["pitch"] = "SKIPPED — Industry mismatch."
                logger.info(
                    "⏭️ Skipping pitch for '%s' — failed industry qualification.",
                    lead_name,
                )

            final_leads.append(final_lead)

        # ── BATCH SUMMARY ─────────────────────────────────────────────────────
        valid_count   = sum(1 for l in final_leads if l.get("is_valid"))
        invalid_count = total - valid_count
        scored        = [l for l in final_leads if l.get("score", 0) > 0]
        avg_score     = sum(l["score"] for l in scored) / len(scored) if scored else 0

        logger.info("-" * 60)
        logger.info(
            "AGENT 3 — Batch complete. "
            "Valid: %d | Invalid: %d | Avg Score: %.1f/10 | Total: %d",
            valid_count, invalid_count, avg_score, total,
        )
        logger.info("=" * 60)

        return final_leads

    # ──────────────────────────────────────────────────────────────────────────
    # PUBLIC METHOD: export_to_json
    # Dump final lead list to JSON for inspection or CSV export downstream.
    # ──────────────────────────────────────────────────────────────────────────
    def export_to_json(
        self,
        final_leads: list[dict],
        output_path: str = "final_leads.json",
    ) -> None:
        """
        Serializes the completed lead list (with scores and pitches) to JSON.

        Args:
            final_leads (list[dict]): Output of process_all().
            output_path (str): Destination JSON file path.
        """
        try:
            with open(output_path, mode="w", encoding="utf-8") as f:
                json.dump(final_leads, f, indent=4, ensure_ascii=False)
            logger.info(
                "Exported %d final leads to '%s'.", len(final_leads), output_path
            )
        except Exception as e:
            logger.error("Failed to export final leads to JSON: %s", str(e))


# ──────────────────────────────────────────────────────────────────────────────
# STANDALONE ENTRY POINT
# Allows direct testing: `python agent3_brain.py <api_key>`
# In production, the orchestrator imports LeadBrain and calls process_all().
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    import os

    # Resolve API config from environment or CLI args.
    raw_keys     = os.environ.get("AI_API_KEYS", sys.argv[1] if len(sys.argv) > 1 else "")
    api_keys     = [k.strip() for k in raw_keys.split(",") if k.strip()]
    api_base_url = os.environ.get("AI_API_BASE_URL", DEFAULT_API_BASE_URL)
    model_name   = os.environ.get("AI_MODEL_NAME", DEFAULT_MODEL)

    # Synthetic test data matching the output shape of AGENT 1 + AGENT 2.
    test_lead = {
        "Name":             "Jane Doe",
        "Email":            "jane@acmehvac.com",
        "Role":             "Owner",
        "Company":          "Acme HVAC Services",
        "Industry":         "HVAC",
        "Location":         "Austin, TX",
        "LinkedIn":         "https://linkedin.com/in/janedoe",
        "Website":          "https://acmehvac.com",
        "scraped_title":    "Acme HVAC — Heating, Cooling & Air Quality",
        "scraped_content":  (
            "We provide residential and commercial HVAC installation, repair, "
            "and maintenance services across Central Texas. Licensed and insured "
            "with 15 years of experience. Free estimates available."
        ),
        "scrape_error": None,
    }

    brain = LeadBrain()

    print("\n── Phase 1: Qualify & Summarize ──")
    p1 = brain.qualify_and_summarize(
        lead_data=test_lead,
        scraped_data=test_lead,
        target_industry="HVAC",
        api_keys=api_keys,
        api_base_url=api_base_url,
        model_name=model_name,
    )
    print(json.dumps(p1, indent=4))

    if p1["is_valid"]:
        print("\n── Phase 2: Generate Pitch ──")
        p2 = brain.generate_pitch(
            lead_data=test_lead,
            summary=p1["summary"],
            api_keys=api_keys,
            api_base_url=api_base_url,
            model_name=model_name,
        )
        print(json.dumps(p2, indent=4))
    else:
        print("\n✗ Lead did not pass industry qualification. Pitch skipped.")
