"""
================================================================================
LEAD SNIPER — AGENT 3: BRAIN (SCORER & PITCHER)
================================================================================
Responsibility:
    Receive an enriched lead dict (AGENT 1 context + AGENT 2 scraped content),
    send it to an AI inference endpoint for analysis, and return a lead score
    (1–10) plus a highly personalized 3-sentence outreach pitch.

Architecture Reference:
    .antigravity_env/agents.md   — Multi-Agent system contract
    .antigravity_env/custom_rules.md — Core directives (Zero-Cost, Self-Healing)

Design Principles (per custom_rules.md):
    - ZERO-COST: Uses any OpenAI-compatible REST API (Grok, Llama, OpenRouter,
      Groq, Together AI, local Ollama, etc.). No paid SDK required.
    - SELF-HEALING: AI call wrapped in try/except with retry logic and JSON
      repair. Malformed AI responses are caught and handled gracefully.
    - SURGICAL: Handles ONLY scoring and pitch generation. No I/O, no scraping.
    - SELLABLE QUALITY: Prompt-engineered for SDR-grade output, fully modular,
      importable by the main orchestrator without modification.

Dependencies (free & open-source):
    pip install requests   (already installed for AGENT 2)

    Compatible API Providers (all have free tiers):
        - Groq:       https://console.groq.com/keys
        - OpenRouter:  https://openrouter.ai/keys
        - Together AI: https://api.together.xyz
        - Local Ollama: http://localhost:11434/v1

Author:     Lead Architect via Antigravity Engine
Version:    2.0.0
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
DEFAULT_MODEL = "grok-3-mini"

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
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # Exponential: 2s, 4s, 8s

# Fallback response returned when the AI fails after all retries.
FALLBACK_RESPONSE = {
    "lead_score": 0,
    "pitch": "Error generating pitch.",
}

# Generation parameters — low temperature = focused, structured output.
# High temperature would introduce creative drift in a JSON-constrained task.
DEFAULT_TEMPERATURE = 0.4
DEFAULT_MAX_TOKENS  = 512  # Pitch is 3 sentences — 512 tokens is generous


# ──────────────────────────────────────────────────────────────────────────────
# CLASS: LeadBrain
# ──────────────────────────────────────────────────────────────────────────────
class LeadBrain:
    """
    AGENT 3 — Brain (Scorer & Pitcher)

    Takes a merged lead dict (AGENT 1 + AGENT 2 data) and returns a structured
    AI analysis containing a lead score and a personalized outreach pitch.

    Uses a generic OpenAI-compatible REST API — works with Grok, Llama, Groq,
    OpenRouter, Together AI, local Ollama, or any /v1/chat/completions endpoint.

    Usage (standalone):
        brain = LeadBrain()
        result = brain.analyze_and_pitch(
            lead_data     = {"Name": "Jane", "Company": "Acme", ...},
            scraped_data  = {"title": "Acme Corp", "content": "We build..."},
            api_key       = "YOUR_API_KEY",
            api_base_url  = "https://api.x.ai/v1/chat/completions",
            model_name    = "grok-3-mini",
        )

    Usage (with full pipeline):
        from agent1_ingestor import LeadIngestor
        from agent2_scout    import WebScout
        from agent3_brain    import LeadBrain

        leads    = LeadIngestor().ingest_csv("leads.csv")
        scout    = WebScout()
        enriched = scout.scrape_all(leads)
        brain    = LeadBrain()

        for lead in enriched:
            result = brain.analyze_and_pitch(
                lead, lead, api_key="YOUR_KEY",
                api_base_url="https://api.x.ai/v1/chat/completions",
                model_name="grok-3-mini",
            )
            lead.update(result)

    Returns:
        {"lead_score": int (1–10), "pitch": str}
        On failure:
        {"lead_score": 0, "pitch": "Error generating pitch."}
    """

    def __init__(self):
        logger.info(
            "LeadBrain initialized. API mode: OpenAI-compatible REST | "
            "Default model: %s | Default endpoint: %s",
            DEFAULT_MODEL,
            DEFAULT_API_BASE_URL,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # PRIVATE HELPER: _build_prompt
    # Constructs the strict, SDR-optimised prompt sent to the AI.
    # ──────────────────────────────────────────────────────────────────────────
    def _build_prompt(self, lead_data: dict, scraped_data: dict) -> str:
        """
        Builds the final prompt string. Strips the scraped_data of the
        'scrape_error' key to keep the AI context clean and focused.

        The prompt enforces:
            1. A strict JSON-only response format (no markdown, no prose).
            2. An integer score between 1 and 10.
            3. A 3-sentence pitch that references specific website details.

        Args:
            lead_data    (dict): Validated lead from AGENT 1.
            scraped_data (dict): Enriched data from AGENT 2.

        Returns:
            str: The fully constructed prompt string.
        """
        # Strip internal pipeline keys irrelevant to the AI.
        clean_lead = {
            k: v for k, v in lead_data.items()
            if k not in ("scrape_error", "scraped_title", "scraped_content")
            and v  # Drop empty/None fields to reduce token cost
        }

        # Build a concise scraped context object for the AI.
        clean_scraped = {
            "page_title": scraped_data.get("scraped_title") or scraped_data.get("title", "N/A"),
            "page_content": scraped_data.get("scraped_content") or scraped_data.get("content", "N/A"),
        }

        prompt = f"""You are an expert B2B SDR (Sales Development Representative) with 10 years of experience writing high-converting cold outreach emails.

Review this lead's information:
{json.dumps(clean_lead, indent=2)}

Their company website context:
{json.dumps(clean_scraped, indent=2)}

Your task:
1. Score this lead from 1 to 10 based on how likely they are to convert (10 = perfect fit, highly specific business context, 1 = generic/unclear).
2. Write a highly personalized, conversational 3-sentence outreach pitch that:
   - Opens by referencing a SPECIFIC detail from their website content (not generic flattery).
   - Clearly states the value proposition in sentence 2.
   - Ends with a soft, low-friction call-to-action in sentence 3.

CRITICAL RULES:
- Return ONLY a raw JSON object. No markdown. No code fences. No explanation.
- The JSON must have exactly two keys: "lead_score" (integer, 1–10) and "pitch" (string).
- Do NOT wrap the JSON in ```json or any other formatting.

Example of the ONLY acceptable output format:
{{"lead_score": 8, "pitch": "Your sentence one. Your sentence two. Your sentence three."}}"""

        return prompt

    # ──────────────────────────────────────────────────────────────────────────
    # PRIVATE HELPER: _parse_ai_response
    # Extracts and validates the JSON object from the AI's raw text output.
    # Handles markdown wrappers and stray text that the model might emit.
    # ──────────────────────────────────────────────────────────────────────────
    def _parse_ai_response(self, raw_text: str) -> Optional[dict]:
        """
        Parses the AI's raw text output into a validated Python dict.

        Self-Healing JSON Extraction (3 layers):
            Layer 1: Direct json.loads() on the raw text.
            Layer 2: Strip markdown code fences (```json ... ```) and retry.
            Layer 3: Regex-extract the first {...} block found in the text.

        If all layers fail, returns None (caller handles fallback).

        Args:
            raw_text (str): The raw string returned by the AI model.

        Returns:
            dict | None: Parsed and validated response, or None on failure.
        """
        if not raw_text or not raw_text.strip():
            logger.warning("AI returned an empty response.")
            return None

        text = raw_text.strip()

        # ── Layer 1: Try parsing as-is ─────────────────────────────────────
        try:
            parsed = json.loads(text)
            return self._validate_ai_dict(parsed)
        except json.JSONDecodeError:
            logger.debug("Layer 1 JSON parse failed. Trying markdown strip...")

        # ── Layer 2: Strip markdown code fences ────────────────────────────
        # AI models sometimes wrap JSON in ```json ... ``` despite instructions.
        stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.DOTALL).strip()
        try:
            parsed = json.loads(stripped)
            return self._validate_ai_dict(parsed)
        except json.JSONDecodeError:
            logger.debug("Layer 2 JSON parse failed. Trying regex extraction...")

        # ── Layer 3: Regex extract first JSON object block ──────────────────
        match = re.search(r"\{.*?\}", text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                return self._validate_ai_dict(parsed)
            except json.JSONDecodeError:
                logger.debug("Layer 3 JSON extraction failed.")

        logger.warning("All JSON parse layers failed. Raw AI output: %s", text[:300])
        return None

    # ──────────────────────────────────────────────────────────────────────────
    # PRIVATE HELPER: _validate_ai_dict
    # Ensures the parsed dict has the required keys with the correct types.
    # ──────────────────────────────────────────────────────────────────────────
    def _validate_ai_dict(self, parsed: dict) -> Optional[dict]:
        """
        Validates that the parsed AI response contains:
            - "lead_score": an integer between 1 and 10
            - "pitch": a non-empty string

        Coerces types where safely possible (e.g., "8" → 8).
        Returns None if validation cannot be satisfied.
        """
        if not isinstance(parsed, dict):
            logger.warning("Parsed response is not a dict: %s", type(parsed))
            return None

        # Coerce lead_score to int if it came back as a string.
        raw_score = parsed.get("lead_score")
        try:
            score = int(raw_score)
        except (TypeError, ValueError):
            logger.warning("Invalid lead_score value: '%s'", raw_score)
            return None

        if not (1 <= score <= 10):
            logger.warning("lead_score out of range [1–10]: %d", score)
            score = max(1, min(10, score))  # Clamp instead of failing

        pitch = parsed.get("pitch", "").strip()
        if not pitch:
            logger.warning("AI returned an empty pitch string.")
            return None

        return {"lead_score": score, "pitch": pitch}

    # ──────────────────────────────────────────────────────────────────────────
    # PRIVATE METHOD: _call_api
    # Single AI call path using a generic OpenAI-compatible REST endpoint.
    # Works with: Grok, Groq, OpenRouter, Together AI, Ollama, etc.
    # ──────────────────────────────────────────────────────────────────────────
    def _call_api(
        self,
        prompt:       str,
        api_key:      str,
        api_base_url: str,
        model_name:   str,
    ) -> Optional[str]:
        """
        Sends the prompt to any OpenAI-compatible /v1/chat/completions endpoint
        using the standard messages format. Returns the raw AI response text.

        Payload follows the OpenAI chat completions schema, which is also used
        natively by Grok (x.ai), Groq, OpenRouter, Together AI, and Ollama.

        Args:
            prompt       (str): The user-facing portion of the prompt.
            api_key      (str): Bearer token for the API provider.
            api_base_url (str): Full URL to the /v1/chat/completions endpoint.
            model_name   (str): Model identifier (e.g., "grok-3-mini").

        Returns:
            str | None: Raw AI response text, or None on failure.
        """
        # ── REQUEST HEADERS ───────────────────────────────────────────────────
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
        }

        # ── PAYLOAD — OpenAI Chat Completions format ──────────────────────────
        # System message sets the AI's role; user message provides the data.
        # response_format forces JSON output (supported by most providers).
        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an expert B2B SDR (Sales Development Representative) "
                        "with 10 years of experience writing high-converting cold "
                        "outreach emails. You ALWAYS respond with raw JSON only — "
                        "no markdown, no code fences, no explanation."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "response_format": {"type": "json_object"},
            "temperature":  DEFAULT_TEMPERATURE,
            "max_tokens":   DEFAULT_MAX_TOKENS,
        }

        # ── SEND REQUEST ──────────────────────────────────────────────────────
        response = requests.post(
            api_base_url,
            json=payload,
            headers=headers,
            timeout=AI_REQUEST_TIMEOUT,
        )
        response.raise_for_status()

        data = response.json()

        # ── PARSE RESPONSE — OpenAI standard structure ────────────────────────
        # Expected path: data["choices"][0]["message"]["content"]
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
    # PUBLIC METHOD: analyze_and_pitch
    # Core analysis pipeline. Self-healing with retry and JSON repair.
    # ──────────────────────────────────────────────────────────────────────────
    def analyze_and_pitch(
        self,
        lead_data:     dict,
        scraped_data:  dict,
        api_key:       str,
        api_base_url:  str = DEFAULT_API_BASE_URL,
        model_name:    str = DEFAULT_MODEL,
    ) -> dict:
        """
        Main analysis method. Builds the AI prompt, calls any OpenAI-compatible
        endpoint, parses the response, and returns a structured scoring/pitch dict.

        Self-Healing Behaviour (per custom_rules.md — Directive 4):
            - API key missing         → logs CRITICAL, returns fallback.
            - No website context      → logs warning, still attempts (lower score expected).
            - Network / API error     → logs error, retries up to MAX_RETRIES.
            - Rate limit (HTTP 429)   → logs warning, waits and retries.
            - Malformed JSON response → runs 3-layer JSON repair before giving up.
            - All retries fail         → logs CRITICAL, returns FALLBACK_RESPONSE.

        Args:
            lead_data     (dict): Validated lead dict from AGENT 1 (LeadIngestor).
            scraped_data  (dict): Enriched lead dict from AGENT 2 (WebScout).
                                  Can be the same merged dict passed from orchestrator.
            api_key       (str):  Bearer token for your AI provider.
            api_base_url  (str):  Full URL to the /v1/chat/completions endpoint.
            model_name    (str):  Model identifier (e.g., "grok-3-mini").

        Returns:
            dict: {"lead_score": int, "pitch": str}
        """
        lead_name = lead_data.get("Name", "Unknown Lead")

        logger.info("=" * 60)
        logger.info("AGENT 3 — Analyzing lead: %s", lead_name)
        logger.info("=" * 60)

        # ── PRE-FLIGHT: API key validation ────────────────────────────────────
        if not api_key or not api_key.strip():
            logger.critical(
                "CRITICAL — No API key provided for lead: %s. "
                "Set your API key via environment variable or CLI argument.",
                lead_name,
            )
            return FALLBACK_RESPONSE.copy()

        # ── PRE-FLIGHT: Check for scrape errors ───────────────────────────────
        if scraped_data.get("scrape_error"):
            logger.warning(
                "Lead '%s' has a scrape error: %s. "
                "Proceeding with CSV-only context (lower score expected).",
                lead_name,
                scraped_data["scrape_error"],
            )

        # ── BUILD PROMPT ──────────────────────────────────────────────────────
        prompt = self._build_prompt(lead_data, scraped_data)
        logger.debug("Prompt built. Length: %d chars.", len(prompt))

        # ── RETRY LOOP ────────────────────────────────────────────────────────
        last_error: Optional[str] = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.debug(
                    "AI call attempt %d/%d for: %s (via %s @ %s)",
                    attempt,
                    MAX_RETRIES,
                    lead_name,
                    model_name,
                    api_base_url,
                )

                # ── CALL OpenAI-COMPATIBLE REST API ───────────────────────────
                raw_text = self._call_api(prompt, api_key, api_base_url, model_name)

                if raw_text is None:
                    raise ValueError("AI returned no text content.")

                logger.debug("Raw AI response received (%d chars).", len(raw_text))

                # ── JSON PARSING (3-layer self-healing) ───────────────────────
                result = self._parse_ai_response(raw_text)

                if result is None:
                    raise ValueError(
                        f"JSON repair failed after 3 layers. Raw: {raw_text[:200]}"
                    )

                # ── SUCCESS ───────────────────────────────────────────────────
                logger.info(
                    "✓ Lead: %s | Score: %d/10 | Pitch: %.80s...",
                    lead_name,
                    result["lead_score"],
                    result["pitch"],
                )
                return result

            except requests.exceptions.HTTPError as http_err:
                status_code = http_err.response.status_code if http_err.response else 0
                last_error  = f"HTTP {status_code}: {http_err}"

                if status_code == 429:
                    # Rate limited — wait longer before retrying.
                    wait = RETRY_BACKOFF_BASE ** attempt + random.uniform(1, 3)
                    logger.warning(
                        "Rate limited (429) for '%s'. "
                        "Waiting %.1fs before retry %d...",
                        lead_name, wait, attempt + 1,
                    )
                    time.sleep(wait)
                elif status_code in (400, 401, 403):
                    # Auth/bad request errors — retrying won't fix these.
                    logger.critical(
                        "CRITICAL — Unrecoverable HTTP %d for '%s': %s",
                        status_code, lead_name, http_err,
                    )
                    break
                else:
                    logger.warning(
                        "AI call failed for '%s': %s (Attempt %d/%d)",
                        lead_name, last_error, attempt, MAX_RETRIES,
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

        # ── ALL RETRIES EXHAUSTED ─────────────────────────────────────────────
        logger.error(
            "✗ AGENT 3 failed for '%s' after %d attempts. "
            "Last error: %s. Returning fallback.",
            lead_name,
            MAX_RETRIES,
            last_error,
        )
        return FALLBACK_RESPONSE.copy()

    # ──────────────────────────────────────────────────────────────────────────
    # PUBLIC METHOD: process_all
    # Batch processor — iterates over AGENT 2's full enriched lead list.
    # ──────────────────────────────────────────────────────────────────────────
    def process_all(
        self,
        enriched_leads: list[dict],
        api_key:        str,
        api_base_url:   str = DEFAULT_API_BASE_URL,
        model_name:     str = DEFAULT_MODEL,
    ) -> list[dict]:
        """
        Runs analyze_and_pitch() for every lead in the enriched list.
        Merges the AI output (lead_score, pitch) back into each lead dict
        so the orchestrator receives a single, fully-resolved object per lead.

        Args:
            enriched_leads (list[dict]): Output of AGENT 2's scrape_all().
            api_key        (str):        Bearer token for your AI provider.
            api_base_url   (str):        Full URL to /v1/chat/completions.
            model_name     (str):        Model identifier.

        Returns:
            list[dict]: Final lead dicts with 'lead_score' and 'pitch' merged in.
        """
        total = len(enriched_leads)
        logger.info("=" * 60)
        logger.info("AGENT 3 — Starting batch analysis. Total leads: %d", total)
        logger.info("=" * 60)

        final_leads = []

        for index, lead in enumerate(enriched_leads, start=1):
            lead_name = lead.get("Name", f"Lead #{index}")
            logger.info("[%d/%d] Analyzing: %s", index, total, lead_name)

            # Both lead_data and scraped_data reference the same merged dict —
            # AGENT 2 already merged the scraped fields into the lead object.
            ai_result = self.analyze_and_pitch(
                lead_data=lead,
                scraped_data=lead,
                api_key=api_key,
                api_base_url=api_base_url,
                model_name=model_name,
            )

            final_lead = lead.copy()
            final_lead["lead_score"] = ai_result["lead_score"]
            final_lead["pitch"]      = ai_result["pitch"]
            final_leads.append(final_lead)

        # ── BATCH SUMMARY ─────────────────────────────────────────────────────
        scored     = sum(1 for l in final_leads if l.get("lead_score", 0) > 0)
        failed     = total - scored
        avg_score  = (
            sum(l["lead_score"] for l in final_leads if l.get("lead_score", 0) > 0) / scored
            if scored > 0 else 0
        )

        logger.info("-" * 60)
        logger.info(
            "AGENT 3 — Batch complete. "
            "Scored: %d | Failed: %d | Avg Score: %.1f/10",
            scored, failed, avg_score,
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
    api_key      = os.environ.get("AI_API_KEY", sys.argv[1] if len(sys.argv) > 1 else "")
    api_base_url = os.environ.get("AI_API_BASE_URL", DEFAULT_API_BASE_URL)
    model_name   = os.environ.get("AI_MODEL_NAME", DEFAULT_MODEL)

    # Synthetic test data matching the output shape of AGENT 1 + AGENT 2.
    test_lead = {
        "Name":             "Jane Doe",
        "Email":            "jane@acmesaas.com",
        "Role":             "CEO",
        "Company":          "Acme SaaS",
        "Industry":         "B2B Software",
        "Location":         "Austin, TX",
        "LinkedIn":         "https://linkedin.com/in/janedoe",
        "Website":          "https://acmesaas.com",
        "scraped_title":    "Acme SaaS — AI-Powered CRM for SMBs",
        "scraped_content":  (
            "We help small and medium-sized businesses automate their "
            "sales pipeline using AI. Our platform integrates with Salesforce "
            "and HubSpot. Founded in 2019, we serve 500+ customers globally."
        ),
        "scrape_error": None,
    }

    brain = LeadBrain()
    result = brain.analyze_and_pitch(
        lead_data=test_lead,
        scraped_data=test_lead,
        api_key=api_key,
        api_base_url=api_base_url,
        model_name=model_name,
    )

    print("\n── AGENT 3 Result ──")
    print(json.dumps(result, indent=4))
