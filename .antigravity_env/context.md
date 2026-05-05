# Project Context — Lead Sniper AI

> **Purpose of this file:** A living snapshot of the project's current state. Updated whenever a meaningful change ships. Read at the START of every session to understand where the project is RIGHT NOW. The IDE consults this before any code change to avoid undoing recent work or duplicating completed tasks.
>
> **Update discipline:** When a task completes that changes the system meaningfully, update the relevant section below. Do not delete history — append to the timeline section instead.

---

## Project Identity

- **Name:** Lead Sniper AI
- **Type:** Multi-agent lead enrichment + outreach pipeline (zero-cost, self-hostable)
- **Comparable to:** Clay.com (free, self-hosted alternative)
- **Owner:** Software agency (internal use + white-label client deployments)
- **Stack:** Python 3.14 · Streamlit · Pandas · Requests + BeautifulSoup + lxml · Any OpenAI-compatible LLM API (Groq / Grok / OpenRouter / Together / Ollama)

---

## Architecture (current)

```
CSV upload (UI or CLI)
      ↓
AGENT 1 — Ingestor       (validates, sanitizes)
      ↓
AGENT 2 — Scout          (DNS check + scrape + verification signals)
      ↓
AGENT 3 — Brain Phase 1  (qualify against industry → score 0-10)
      ↓
AGENT 3 — Brain Phase 2  (generate 3-sentence pitch — only if Phase 1 passed)
      ↓
Output CSV + .leads_history.csv (persistent DB)
```

**Entry points:**
- `app_ui.py` — Streamlit UI (production interface)
- `main.py` — CLI orchestrator (CURRENTLY BROKEN — see Known Issues)
- Each agent file is independently runnable for testing

---

## Verticals Currently Configured

- **HVAC Contractors** — full prompt + scoring rubric (default)
- **Career Coaching** — secondary vertical (toggled via `is_career_coaching` flag in UI)

**Status:** Both verticals are currently HARDCODED inside `agent3_brain.py` as an `if is_career_coaching:` branch. This is an anti-pattern (violates `custom_rules.md` Rule 5 — No Hardcoded Verticals). Scheduled for refactor — see Roadmap section.

**Future verticals planned:** Roofing, Solar, Dental, Real Estate, SaaS, Insurance, Legal Services. Each will become a template entry in `prompt_templates.md` once the externalization refactor is complete.

---

## Current System Health

### ✅ Working
- Streamlit UI (Dashboard, Leads Table, Settings pages)
- CSV upload + ingestion via Agent 1
- Multi-key API rotation in Agent 3 (auto-rotates on 4xx/5xx)
- 3-layer JSON repair on malformed LLM responses
- DNS check + Jina Reader API fallback in Agent 2
- Email verification (domain match + on-page presence)
- Person verification (name search across main page + /about, /team, /contact subpages)
- Post-AI score caps (cap at 2 if site unscrapeable, 4 if email unverified, 6 if person not found)
- Per-row error isolation (one bad lead never crashes the batch)
- Settings persistence via `settings.json` (gitignored)
- Historical leads database via `.leads_history.csv` (gitignored)

### ❌ Known Issues (to fix)
- **Hardcoded vertical logic** in `agent3_brain.py` (see Verticals section above).

### ⚠️ Sellability Gaps (to build)
- No `README.md` — no onboarding for clients or future devs.
- No `.env.example` — secrets handling is implicit.
- No `LICENSE` — blocks legal white-label distribution.
- No `Dockerfile` — clients can't one-command deploy.
- No branding/config layer — "Lead Sniper AI" is hardcoded in UI strings.
- No CSV input template for client onboarding.
- No multi-user / no auth — single-user Streamlit (fine for internal, blocker for SaaS).

---

## Roadmap (priority-ordered)

1. ✅ **Repo hygiene** (completed — see Timeline)
2. ✅ **Env scaffolding** (in progress — currently building this file)
3. ✅ **Fix `main.py`** (completed 2026-05-02 — see Timeline + error_log.md BUG-001)
4. ✅ **Fix Settings slider bug + provider/model mismatch** (BUG-002 + BUG-003 both done 2026-05-02 — see Timeline + error_log.md)
5. ⏳ **Externalize industry prompts** into `prompt_templates.md` (kills hardcoded vertical logic — unlocks white-label)
6. ⏳ **Add `README.md`, `.env.example`, `LICENSE`, CSV template**
7. ⏳ **Add `Dockerfile` + simple deploy doc**
8. ⏳ **Branding/config layer** (per-client app name, logo, accent color)
9. ⏳ **Per-vertical CSV column mappers** (handle clients with non-standard CSV headers)
10. ⏳ **Future agents** (Sender, Tracker, Enricher+ — reserved slots in `agents.md`)

---

## Timeline (append-only)

### 2026-05-02 — Phase 1: Repo Hygiene complete
- Created `.gitignore` covering Python, secrets, logs, runtime artifacts, IDE files.
- Deleted ~5.3 MB of stale logs (`agent1_ingestor.log`, `agent2_scout.log`, `agent3_brain.log`).
- Deleted `__pycache__/` (auto-regenerates).
- Deleted `scratch/transform_ui.py` (dev throwaway with hardcoded Windows path).
- **Repo is now client-presentable from a hygiene standpoint.**

### 2026-05-02 — Phase 2: Env Scaffolding complete
- Upgraded `agents.md` from thin 555-byte stub to full agent contracts with Must/Must-NOT rules + reserved future agent slots.
- Upgraded `custom_rules.md` from 4 founding directives to 16 enforceable rules across 3 tiers + conflict resolution clause.
- Upgraded `gemini.md` from 4 short instructions to full AI assistant operating manual with mandatory read order, behavioral directives, refusal conditions, and session-start checklist.
- Created `context.md` (this file).
- Created `decisions.md` (10 ADRs back-documented from existing code patterns + 2 new ADRs for hygiene + scaffolding).
- Created `error_log.md` (4 OPEN bugs seeded from initial audit + 4 observed patterns).
- Created `debug_protocol.md` (7 triage trees + 6 anti-patterns + universal first-steps protocol).
- Created `prompt_templates.md` (HVAC + Career Coaching templates extracted verbatim, 7 reserved vertical slots, full Loader Contract spec).
- **Env folder is now production-grade. Every future session starts oriented.**

### 2026-05-02 — Phase 3: Bug Fixes in progress
- **BUG-001 FIXED:** Repaired `main.py` (full surgical rewrite, version 2.0.0). Replaced broken `analyze_and_pitch()` calls with correct two-phase `qualify_and_summarize()` + `generate_pitch()` sequence. Replaced legacy single-key `GEMINI_API_KEY` env var with multi-key `AI_API_KEYS` (matches ADR-003 rotation). Added `argparse` CLI with `--input-csv`, `--output-csv`, `--api-base-url`, `--model`, `--api-key`, `--target-industry` flags. Output CSV schema expanded from 7 to 9 columns (added `Category` and `Summary`). CLI mode is now fully functional. See `error_log.md` BUG-001 (now in Resolved section) for full details.
- **BUG-002 FIXED:** Split the broken Settings slider into two functional sliders. New `Minimum Qualification Score` slider (range 1–10, default 5, persisted to settings.json) is wired through `app_ui.py` → `agent3_brain.LeadBrain.qualify_and_summarize(min_score=...)` and replaces the hardcoded `>= 5` threshold. Existing `Inter-Lead Delay (seconds)` slider (range 1–10, default 2) was relabeled and now matches its actual function. Backward compatibility preserved via `min_score: int = 5` default parameter — `main.py` and any other callers continue working unchanged. Touched 2 files, 7 surgical str_replace operations, ~30 lines modified out of ~2,400 across both files. See `error_log.md` BUG-002 (now in Resolved section) for full details.
- **BUG-003 FIXED:** Default provider switched from `Grok (x.ai)` to `Groq` to match the default model `llama-3.3-70b-versatile`. Fixed in two places: `app_ui.py` session_state initialization (so fresh UI installs work out of the box) and `agent3_brain.py` `DEFAULT_API_BASE_URL` constant (so CLI / `main.py` first-runs also work). Grok remains fully supported as an opt-in choice — only the default changed. Total fix: ~10 lines across 2 files via str_replace. See `error_log.md` BUG-003 (now in Resolved section) for full details.

**Phase 3 status:** 3 of 4 bugs fixed (BUG-001 ✅, BUG-002 ✅, BUG-003 ✅). BUG-004 (hardcoded vertical logic) remains OPEN but is intentionally not addressed in Phase 3 — it is scheduled to be resolved by the Roadmap #5 refactor (externalize industry prompts into `prompt_templates.md`), which is a multi-prompt structural change rather than a point fix.

### 2026-05-02 — Phase 3: Bug Fixes complete (point fixes)
- All 3 point-fix bugs (BUG-001, BUG-002, BUG-003) now in Resolved section of `error_log.md`.
- BUG-004 deferred to Phase 4 (Roadmap #5) by design — it is a structural anti-pattern, not a point bug.
- **Next: Phase 4 — Externalize industry prompts (Roadmap #5).** This is the white-label unlock. After Phase 4, adding a new vertical (Roofing, Solar, Dental, etc.) becomes a markdown edit in `prompt_templates.md` rather than a Python code change.

---

## Quick Reference

- **Add a new vertical:** edit `.antigravity_env/prompt_templates.md` (no code changes — once Roadmap item #5 is done).
- **Debug a failure:** read `.antigravity_env/debug_protocol.md` first.
- **Avoid reintroducing a bug:** read `.antigravity_env/error_log.md` before touching the file in question.
- **Understand a past architectural choice:** read `.antigravity_env/decisions.md`.
