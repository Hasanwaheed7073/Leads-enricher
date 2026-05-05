# Core Directives — Lead Sniper AI

> **Purpose of this file:** The non-negotiable rules every code change must follow. Read before writing or editing ANY file in this project. These directives outrank personal preference, convenience, or AI suggestion.

---

## Tier 1 — Founding Directives (Never Override)

### 1. ZERO-COST ARCHITECTURE
Every library, API, or service used must have a permanent free tier or be open-source. No paid SDKs. No trial-only services. No "$5/mo and up" tools.
- ✅ Allowed: requests, BeautifulSoup, lxml, Streamlit, pandas, Groq free tier, OpenRouter free models, Together AI free tier, local Ollama, Jina Reader free endpoint.
- ❌ Forbidden: OpenAI paid API, Anthropic paid API, Apollo paid tier, Clearbit, ZoomInfo, any paid scraping service, any tool requiring credit card to start.

### 2. SURGICAL EDITS ONLY
Never rewrite an entire file when a single function needs changing. Use precise insertions, deletions, and replacements.
- Edits must list `do_not_touch` files explicitly.
- Multi-file edits must be split into multiple prompts unless the changes are atomically dependent.
- If unsure whether an edit is surgical, ASK before proceeding.

### 3. SELLABLE QUALITY
All output must be production-ready, modular, and packaged so the final product can be deployed and sold.
- Code must be importable without modification.
- Logging must be present at INFO level for happy-path and WARNING/ERROR for failures.
- No commented-out code blocks left behind.
- No `print()` statements for debugging — use the logger.
- No hardcoded credentials, paths, or client names anywhere.

### 4. SELF-HEALING
All data pipelines (especially scraping/API calls) must include try/except blocks with detailed error logging and auto-retry mechanisms.
- Per-lead failures never crash the batch.
- All retries use exponential backoff with jitter.
- Fallback strategies must be documented in `decisions.md`.

---

## Tier 2 — Operational Rules (Enforced on Every Change)

### 5. NO HARDCODED VERTICALS
Industry-specific logic (HVAC scoring rubrics, Career Coaching qualifications, etc.) lives EXCLUSIVELY in `prompt_templates.md`. Never inside `agent3_brain.py` or any other code file.
- The `is_career_coaching` boolean flag pattern is a temporary anti-pattern. Do not extend it. New verticals are added by appending a template to `prompt_templates.md`, not by adding a new boolean.

### 6. NO COMMITTED SECRETS
API keys, tokens, passwords, and client-specific credentials are never written to any file that could be committed.
- `settings.json` is gitignored — but assume it could leak. Never log full key values; mask all but last 6 chars.
- `.env` files are the canonical secret store. A `.env.example` template (no real values) is the only env file ever committed.

### 7. NO PAID FEATURE LEAKAGE
If a future request would require a paid service (e.g., "add SendGrid for emails"), STOP and propose the free-tier equivalent (e.g., "use Gmail API free tier or SMTP"). Never silently introduce a paid dependency.

### 8. CONTEXT FILES ARE SACRED
Before any code change, read in this order: `custom_rules.md` (this file), `agents.md`, `context.md`, `decisions.md`, `error_log.md`, `debug_protocol.md`, `prompt_templates.md`. Do not skip. Do not skim.

### 9. APPEND TO `error_log.md` ON BUG FIXES
Whenever a bug is fixed, append an entry to `.antigravity_env/error_log.md` with: date, file affected, symptom, root cause, fix applied. This builds a debugging memory the IDE consults on future failures.

### 10. APPEND TO `decisions.md` ON ARCHITECTURE CHANGES
Whenever an architectural decision is made (changing an agent's contract, swapping a library, restructuring data flow), append to `.antigravity_env/decisions.md` with: date, decision, alternatives considered, why chosen.

### 11. WHITE-LABEL READY
The app must be deployable for multiple clients without code changes. Branding, app name, accent color, target industry, and AI provider config all live in user-editable config — never in code.

### 12. LOG, DON'T PRINT
All runtime feedback uses the logging module. Streamlit `st.write` / `st.info` / `st.error` are UI-only and must mirror what's already in the logger.

---

## Tier 3 — Style Rules (Non-Critical but Enforced)

### 13. COMMENTS EXPLAIN WHY, NOT WHAT
A comment that says `# increment counter` is noise. A comment that says `# courtesy delay to avoid Google's bot detection` is signal.

### 14. CONSTANTS AT TOP OF FILE
Magic numbers and config values live in named constants near the top, not buried in function bodies.

### 15. UTF-8 EVERYWHERE
All file I/O specifies `encoding="utf-8"` (or `utf-8-sig` for CSV files that may have BOM). Never rely on system default encoding.

### 16. UNIX LINE ENDINGS
All files use LF line endings, not CRLF. Even on Windows.

---

## Conflict Resolution

If two rules conflict in a specific situation, Tier 1 outranks Tier 2 outranks Tier 3. If a Tier 1 rule blocks a request, refuse the request and propose an alternative — do not violate the directive.

If a rule itself seems wrong for a specific case, do NOT silently violate it. Flag the conflict, propose the rule update, and wait for explicit confirmation before proceeding.
