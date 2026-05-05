# Architectural Decisions Log — Lead Sniper AI

> **Purpose of this file:** Append-only record of every non-trivial architectural decision made on this project. Each entry explains WHAT was decided, WHY it was chosen over alternatives, and WHEN. Read before changing any pattern documented here — these decisions exist for reasons that may not be obvious from the code alone.
>
> **Update discipline:** Append a new entry whenever ANY of these change: an agent contract, a library choice, a data flow pattern, a fallback strategy, an error-handling approach, or a deliberate trade-off. Do NOT delete old entries — superseded decisions stay in the log with a status update.
>
> **Format:** Each decision uses the ADR (Architectural Decision Record) template below.

---

## ADR Entry Template

```
### ADR-NNN — [Short Title]
- **Date:** YYYY-MM-DD
- **Status:** Active | Superseded by ADR-XXX | Deprecated
- **Context:** What problem prompted this decision? What were we trying to achieve?
- **Decision:** What did we choose to do?
- **Alternatives considered:** What else was on the table? Why were they rejected?
- **Consequences:** What does this cost us / unlock? What constraints does it impose on future work?
- **Files affected:** Which files embody this decision?
```

---

## Active Decisions

---

### ADR-001 — Three-agent pipeline (Ingestor → Scout → Brain)
- **Date:** 2026-04 (pre-existing in codebase)
- **Status:** Active
- **Context:** Lead enrichment requires distinct concerns: data validation, web research, and AI analysis. Mixing them in one file would make testing, debugging, and white-labeling impossible.
- **Decision:** Split into three independent agents, each in its own file, each with its own logger, each importable standalone. Communication via dict payloads passed by an orchestrator (UI or CLI).
- **Alternatives considered:**
  1. Monolithic `lead_processor.py` — rejected: untestable, untraceable failures, no separation of concerns.
  2. Microservices (FastAPI per agent) — rejected: violates zero-cost (deployment complexity, hosting cost), overkill for current scale.
- **Consequences:** Easy to swap any agent's implementation. Adds slight overhead in dict-passing. Each agent must be defensive about its inputs (no shared state).
- **Files affected:** `agent1_ingestor.py`, `agent2_scout.py`, `agent3_brain.py`, `main.py`, `app_ui.py`

---

### ADR-002 — Provider-agnostic LLM layer (OpenAI-compatible REST)
- **Date:** 2026-04 (pre-existing in codebase)
- **Status:** Active
- **Context:** Locking into one LLM vendor (e.g., OpenAI SDK, Anthropic SDK) creates vendor risk and violates zero-cost (most paid SDKs assume paid usage). Need flexibility to use whichever free tier has quota today.
- **Decision:** Use raw `requests.post()` to any OpenAI-compatible `/v1/chat/completions` endpoint. Provider URL + model name + API key are all parameters, configurable per-call.
- **Alternatives considered:**
  1. Use the official OpenAI SDK — rejected: forces OpenAI-specific patterns, harder to point at Groq/Together/Ollama.
  2. Use LangChain — rejected: heavy dependency, opinionated, not zero-cost-aligned.
- **Consequences:** Zero vendor lock-in — works with Groq, Grok, OpenRouter, Together AI, Ollama, future providers. Slight cost: must maintain our own request/response handling. Massive upside: free-tier rotation across multiple providers is now trivial.
- **Files affected:** `agent3_brain.py` (`_call_api()`, `_call_with_rotation()`)

---

### ADR-003 — API key rotation on 4xx/5xx errors
- **Date:** 2026-04 (pre-existing in codebase)
- **Status:** Active
- **Context:** Free tier providers rate-limit individual API keys (typically 30-60 RPM). For batch processing of hundreds of leads, one key is insufficient. Buying paid tier violates zero-cost.
- **Decision:** Accept a `list[str]` of API keys per call. On HTTP 429 (rate limit) or other 4xx/5xx errors, automatically rotate to the next key in the pool and retry. Index persists across calls on the same `LeadBrain` instance — so if Key #2 is hot, the next lead also starts on #2.
- **Alternatives considered:**
  1. Single key + back off + retry — rejected: too slow for batch work, throughput drops by 10x.
  2. Round-robin every call — rejected: defeats the purpose of "stick with the working key."
- **Consequences:** Throughput multiplied by N keys (where N = pool size). Users can stack 3-5 free Groq accounts and process 1000+ leads/day at zero cost. Slight complexity in the rotation index management.
- **Files affected:** `agent3_brain.py` (`_get_next_key()`, `_rotate_key()`, `_call_with_rotation()`)

---

### ADR-004 — 3-layer JSON repair on LLM responses
- **Date:** 2026-04 (pre-existing in codebase)
- **Status:** Active
- **Context:** Even with `response_format: {type: "json_object"}` set, LLMs occasionally return JSON wrapped in markdown code fences, or with a leading sentence ("Here's the JSON: ..."), or with extra text after the closing brace. Crashing on these is unacceptable for batch work.
- **Decision:** Three-layer fallback parser in `_parse_json_response()`:
  - Layer 1: `json.loads()` directly.
  - Layer 2: Strip markdown code fences (` ```json ... ``` `), then `json.loads()`.
  - Layer 3: Regex-extract first `{...}` block from the text, then `json.loads()`.
  - All three fail → return `None`, caller uses fallback dict.
- **Alternatives considered:**
  1. Use the LLM's structured output mode only — rejected: not all providers support it consistently (Groq did, others didn't at time of writing).
  2. Single-layer parse + retry — rejected: wastes API quota on a problem we can solve client-side.
- **Consequences:** Pipeline survives malformed AI output. Tiny CPU cost per response. Eliminates ~5-10% of false failures in testing.
- **Files affected:** `agent3_brain.py` (`_parse_json_response()`)

---

### ADR-005 — Jina Reader API as scrape fallback
- **Date:** 2026-04 (pre-existing in codebase)
- **Status:** Active
- **Context:** Many lead websites are blocked behind Cloudflare bot protection or are JavaScript-heavy SPAs that return empty HTML to `requests`. Without a fallback, ~30-40% of legitimate leads fail to scrape.
- **Decision:** When primary `requests` fetch fails (4xx/5xx) OR returns thin content (<200 chars after parsing), fall back to Jina Reader's free API at `https://r.jina.ai/<url>`. Jina handles JS rendering and bot bypass for free.
- **Alternatives considered:**
  1. Selenium / Playwright — rejected: heavy dependency, requires browser binaries, slow, fights zero-cost (cloud Selenium services are paid).
  2. ScrapingBee / Bright Data — rejected: paid services, violates Tier 1 directive.
  3. Accept the failure rate — rejected: Phase 1 score caps at 2 if site unscrapeable, so we'd lose half our leads to no fault of theirs.
- **Consequences:** Scrape success rate jumps from ~60% to ~90%. Adds dependency on Jina's free service availability (mitigated: failure of Jina is non-fatal, just returns the error). Slightly slower per-lead when fallback triggers.
- **Files affected:** `agent2_scout.py` (`_scrape_via_jina()`, `scrape_website()`)

---

### ADR-006 — Post-AI score caps based on verification signals
- **Date:** 2026-04 (pre-existing in codebase)
- **Status:** Active
- **Context:** LLMs over-score leads when given any plausible-sounding signal. A company name like "Cool Air Houston LLC" will get scored 8/10 for HVAC even if the website is dead, the email is fake, and the person doesn't exist. We need ground-truth checks that the AI cannot override.
- **Decision:** After Agent 3 returns a score, apply hard caps based on Agent 2's verification signals:
  - Site unscrapeable → score capped at 2
  - Email domain doesn't match AND email not on page → score capped at 4
  - Person name not found on website → score capped at 6
  - Dead domain (DNS fail) → instant 0, skip Phase 2 entirely
- **Alternatives considered:**
  1. Pass verification signals to AI and trust it — rejected: AI ignores them when company name is convincing.
  2. Use signals as soft hints in the prompt — rejected: same problem, AI optimizes for narrative coherence over evidence.
- **Consequences:** Score quality up dramatically. Some legitimate leads get capped (e.g., a real HVAC company whose website was temporarily down) — accepted trade-off. Caps are documented in summary text so reviewer knows why.
- **Files affected:** `agent3_brain.py` (`qualify_and_summarize()` post-processing block)

---

### ADR-007 — Per-row CSV writes (no batching)
- **Date:** 2026-04 (pre-existing in codebase)
- **Status:** Active
- **Context:** Pipeline runs can take hours for large batches. If the process crashes at lead #487 of 1000, losing 487 enriched rows is unacceptable.
- **Decision:** Open output CSV once at start, write each row immediately after enrichment, flush after every write. Partial output survives any crash.
- **Alternatives considered:**
  1. Batch writes every N rows — rejected: still loses N-1 rows on crash, marginal speed gain not worth the risk.
  2. SQLite backing store + final CSV export — rejected: adds dependency, adds complexity, current solution is simple and works.
- **Consequences:** Output is always resumable from where it stopped. Slightly more disk I/O. Tiny performance cost.
- **Files affected:** `main.py` (output CSV loop), `app_ui.py` (`.leads_history.csv` append logic)

---

### ADR-008 — Streamlit as UI framework
- **Date:** 2026-04 (pre-existing in codebase)
- **Status:** Active
- **Context:** Need a polished UI for non-technical users (clients, agency staff). Building React + FastAPI is overkill and violates zero-cost (frontend hosting). Need something that runs locally OR deploys free to Streamlit Cloud.
- **Decision:** Streamlit. Single-file Python UI, free local run, free Streamlit Cloud deploys, native pandas DataFrame rendering (perfect for spreadsheet-style lead tables).
- **Alternatives considered:**
  1. Flask + React — rejected: violates zero-cost (frontend hosting), slow to build.
  2. Gradio — rejected: less polished, weaker for spreadsheet UIs.
  3. Pure CLI — rejected: clients won't use a CLI.
- **Consequences:** Single-user limitation (one Streamlit session = one user). For multi-user/SaaS we'd need a different solution. Acceptable for current agency use case (internal tool + per-client deployment). Streamlit's session state quirks require careful caching of expensive operations.
- **Files affected:** `app_ui.py`

---

### ADR-009 — Repo hygiene baseline (gitignore + log purge)
- **Date:** 2026-05-02
- **Status:** Active
- **Context:** Initial codebase had 5.3 MB of stale logs, `__pycache__/` committed, dev throwaway script in `scratch/`, no `.gitignore`. Blocks client-facing presentation and signals "unfinished" to anyone reading the repo.
- **Decision:** Established a `.gitignore` covering Python artifacts, secrets, runtime files, IDE files, OS files, and Lead-Sniper-specific outputs. Deleted committed logs, `__pycache__/`, and `scratch/`. Logs auto-regenerate at runtime — no functional impact.
- **Alternatives considered:**
  1. Leave as-is, gitignore only — rejected: existing committed files persist in git history without `git rm`.
  2. `git rm` everything via complex script — rejected: surgical violation, also handled in dedicated prompts already.
- **Consequences:** Repo is client-presentable. Disk footprint reduced ~5.3 MB. Future commits won't reintroduce these files. No code change required.
- **Files affected:** `.gitignore` (created), `agent1_ingestor.log` (deleted), `agent2_scout.log` (deleted), `agent3_brain.log` (deleted), `__pycache__/` (deleted), `scratch/transform_ui.py` (deleted)

---

### ADR-010 — Environment scaffolding upgrade (`.antigravity_env/`)
- **Date:** 2026-05-02
- **Status:** Active
- **Context:** Original env folder had 3 thin files (~1.5KB total) acting as starter stubs. The system was designed to "self-upgrade and self-debug over time" but the env folder lacked the structure to support that. Without a context layer, every IDE session starts from scratch.
- **Decision:** Upgrade existing 3 files (`agents.md`, `custom_rules.md`, `gemini.md`) to full contracts. Create 5 new files: `context.md` (live state), `decisions.md` (this file — ADR log), `error_log.md` (bug memory), `debug_protocol.md` (failure triage), `prompt_templates.md` (multi-vertical externalization).
- **Alternatives considered:**
  1. Skip the scaffolding, build features directly — rejected: every future prompt would lose context, multi-vertical refactor would be guess-driven.
  2. Single mega-file `project_brain.md` — rejected: too large to read every session, no separation of concerns.
- **Consequences:** Every IDE session now starts fully oriented. Context persists across days/weeks/months. Multi-vertical refactor (Roadmap item #5) becomes mechanical. Slight ongoing cost: env files must be kept up to date as the project evolves (enforced by `custom_rules.md` Rules 9 + 10).
- **Files affected:** All 8 files in `.antigravity_env/`

---

## Superseded Decisions

*None yet. When a decision is superseded by a later one, move it here and link to the replacement.*

---

## Deprecated Decisions

*None yet. Decisions that are no longer in effect but kept for historical reference.*
