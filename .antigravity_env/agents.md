# Multi-Agent Architecture — Lead Sniper AI

> **Purpose of this file:** Define the contract every agent must honor. Read before any change to agent code. Update only when an agent's responsibility, input, or output changes.

---

## System Overview

Lead Sniper AI is an autonomous Lead Research Engine. It ingests raw leads, verifies them against the live web, and generates personalized outreach — all on a zero-cost stack.

The system is **multi-vertical by design**: HVAC, Career Coaching, and any future industry (Roofing, Solar, Dental, Real Estate, SaaS, etc.) are configured via prompt templates — never hardcoded into agent logic.

---

## Agent Roster

### AGENT 1 — Ingestor (gent1_ingestor.py)
- **Responsibility:** Read CSV → sanitize → validate → return clean lead list.
- **Input:** Path to a CSV file with headers including at minimum Website (other fields: Name, Email, Role, Company, Industry, Location, LinkedIn).
- **Output:** list[dict] of validated leads, one dict per row, only with expected schema keys.
- **Must:** Skip rows with invalid/missing Website. Log every skip with line number + reason. Never crash on a single bad row.
- **Must NOT:** Make any network call. Make any AI call. Mutate input files.

### AGENT 2 — Scout (gent2_scout.py)
- **Responsibility:** Visit each lead's website, scrape content, run verification signals.
- **Input:** A single URL + optional email + optional person name.
- **Output:** dict with keys: url, 	itle, content, domain_alive, email_found_on_page, email_domain_matches, person_found_on_page, person_context. On failure: same dict with error key set.
- **Must:** DNS-check domain before scraping. Retry on transient failures (max 3 attempts, exponential backoff). Fall back to Jina Reader API when primary fetch is blocked or returns thin content. Rotate User-Agent on every request.
- **Must NOT:** Score leads. Generate pitches. Make AI calls. Hammer servers (always insert courtesy delays).

### AGENT 3 — Brain (gent3_brain.py)
- **Responsibility:** Two-phase AI pipeline — qualify+score (Phase 1), then pitch (Phase 2).
- **Input:** Enriched lead dict (Agent 1 + Agent 2 merged) + target industry + API key pool.
- **Output Phase 1:** {is_valid, score, summary, category}. Output Phase 2: {pitch}.
- **Must:** Rotate API keys on 4xx/5xx errors. 3-layer JSON repair on malformed LLM responses. Apply post-AI score caps based on verification signals (cap at 2 if site unscrapeable, cap at 4 if email unverified, cap at 6 if person not found).
- **Must NOT:** Trust the LLM blindly — always run hard filters and post-AI caps. Skip Phase 2 for leads that failed Phase 1 (saves quota).

---

## Future Agents (Reserved Slots)

When extending the system, follow the same contract pattern. Reserved future agents:

- **AGENT 4 — Sender:** Deliver pitches via email/LinkedIn. Inputs: qualified leads + pitches. Output: send status per lead.
- **AGENT 5 — Tracker:** Monitor reply/open rates, feed back into scoring.
- **AGENT 6 — Enricher+:** Pull additional context from public APIs (LinkedIn data, Crunchbase, Apollo free tier, etc.).

Do NOT implement reserved agents until explicitly requested. Their slot existing here is for architectural awareness only.

---

## Cross-Agent Rules

1. **Stateless by default.** Agents do not share memory. They communicate only via dict payloads passed by the orchestrator (main.py) or UI (pp_ui.py).
2. **Logging is per-agent.** Each agent writes to its own log file (gent1_ingestor.log, etc.). Never share log files.
3. **Surgical extension.** Adding a feature to one agent must not require changes in another agent unless the contract above is being intentionally renegotiated.
4. **Vertical-agnostic core.** Industry-specific logic (HVAC rules, Career Coaching rules, etc.) lives in prompt_templates.md — NEVER inside agent code.
5. **Self-healing is mandatory.** Every external call (HTTP, DNS, AI API, file I/O) must have try/except + retry + graceful degradation.

---

## Change Log Discipline

When any agent's contract above changes, also append an entry to .antigravity_env/decisions.md explaining what changed and why. The contract here and the decision record there must stay in sync.
