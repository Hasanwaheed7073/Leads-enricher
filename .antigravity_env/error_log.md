# Error Log — Lead Sniper AI

> **Purpose of this file:** Append-only record of every bug discovered, the root cause, and the fix applied. Read BEFORE touching any file that has past entries here. The goal is simple: never reintroduce a bug that has already been fixed.
>
> **Update discipline:** Append a new entry whenever a bug is fixed (or discovered, even if not yet fixed). Status field tracks lifecycle: OPEN → INVESTIGATING → FIXED → VERIFIED. Do NOT delete entries — even fixed bugs stay in the log as institutional memory.
>
> **Required reading per `custom_rules.md` Rule 9:** When fixing any bug, append an entry here. When touching any file, scan this log for past issues in that file.

---

## Entry Template

```
### BUG-NNN — [Short symptom]
- **Date discovered:** YYYY-MM-DD
- **Date fixed:** YYYY-MM-DD (or — if still open)
- **Status:** OPEN | INVESTIGATING | FIXED | VERIFIED
- **Severity:** CRITICAL | HIGH | MEDIUM | LOW
- **File(s) affected:** path/to/file.py:line_number
- **Symptom:** What the user/operator sees when this bug triggers.
- **Reproduction:** Minimum steps to reliably trigger it.
- **Root cause:** What actually went wrong (not just the symptom).
- **Fix applied:** Specific change made to resolve it. Reference the prompt or commit if applicable.
- **Regression guard:** What to check on future edits to prevent this coming back.
```

---

## Severity Definitions

- **CRITICAL** — Crashes the app, corrupts data, exposes secrets, or makes the product unusable for clients.
- **HIGH** — Breaks a major feature for some users; workarounds exist but are painful.
- **MEDIUM** — Wrong output, mislabeled UI, broken edge case. Functional but embarrassing.
- **LOW** — Cosmetic, log noise, performance nit.

---

## Active Bugs (OPEN / INVESTIGATING)

---

### BUG-004 — Hardcoded vertical logic prevents adding new industries without code edits
- **Date discovered:** 2026-05-02 (during initial audit)
- **Date fixed:** —
- **Status:** OPEN
- **Severity:** HIGH (sellability blocker)
- **File(s) affected:** `agent3_brain.py:609-700` (Phase 1 prompt branching) and `agent3_brain.py:840-867` (Phase 2 prompt branching) and `app_ui.py:683-687` (UI checkbox)
- **Symptom:** To add a new vertical (Roofing, Solar, Dental, Real Estate, etc.), a developer must edit `agent3_brain.py` and add a new `elif is_X_vertical:` branch — duplicating ~50 lines of prompt template per vertical. UI must also be edited to add another checkbox. This pattern doesn't scale beyond 3-4 verticals before the file becomes unmaintainable. Violates `custom_rules.md` Rule 5 (No Hardcoded Verticals).
- **Reproduction:** Look at `agent3_brain.py` around line 609. The HVAC and Career Coaching prompts are hardcoded as Python f-strings inside an `if is_career_coaching: ... else: ...` branch. There is no extension point.
- **Root cause:** Original implementation grew organically from a single-vertical (HVAC) tool. Career Coaching was added as a quick toggle. The pattern was never refactored into a config-driven template system because the third vertical was never added.
- **Fix applied:** — (scheduled in Roadmap item #5). Plan: externalize all vertical prompts into `prompt_templates.md` (or a structured `prompt_templates.json`), have agent3_brain.py load templates at runtime, replace the boolean checkbox with a dropdown of available templates.
- **Regression guard:** After fix, no Python file may contain industry-specific phrases like "HVAC", "Career Coach", "Roofing", etc. — these belong only in template files. Add a CI check / pre-commit hook that greps for vertical names in `.py` files and fails if found.

---

## Resolved Bugs (FIXED / VERIFIED)

### BUG-001 — `main.py` calls non-existent method, CLI mode is broken
- **Date discovered:** 2026-05-02 (during initial audit)
- **Date fixed:** 2026-05-02
- **Status:** FIXED
- **Severity:** HIGH
- **File(s) affected:** `main.py` (full-file repair)
- **Symptom:** Running `python main.py` crashed immediately with `AttributeError: 'LeadBrain' object has no attribute 'analyze_and_pitch'`. CLI / cron / scheduled-batch mode was unusable. Only the Streamlit UI worked.
- **Reproduction (pre-fix):** From project root, run `python main.py` after setting any API key. Crash on first lead processed.
- **Root cause:** `main.py` was written against an older version of `agent3_brain.py` that exposed a single `analyze_and_pitch()` method. The brain was later refactored into a two-phase pipeline (`qualify_and_summarize()` + `generate_pitch()` — see ADR-001 evolution) but `main.py` was never updated to match. Also still referenced the legacy `GEMINI_API_KEY` env var while the rest of the codebase had moved to multi-key rotation via `AI_API_KEYS` (see ADR-003).
- **Fix applied:** Full surgical rewrite of `main.py` (Prompt 13 of Phase 3 bug fixes). Changes: (1) Replaced `brain.analyze_and_pitch()` calls with the correct two-phase sequence — `brain.qualify_and_summarize()` followed by `brain.generate_pitch()` only when Phase 1 returned `is_valid=True`. (2) Replaced single `GEMINI_API_KEY` env var with multi-key `AI_API_KEYS` (comma-separated) matching ADR-003 rotation pattern. (3) Added `argparse` CLI with flags `--input-csv`, `--output-csv`, `--api-base-url`, `--model`, `--api-key`, `--target-industry`. (4) Output CSV schema expanded from 7 to 9 columns to include the `Category` and `Summary` fields produced by Phase 1 (previously computed and discarded). (5) Imported `DEFAULT_API_BASE_URL` and `DEFAULT_MODEL` from `agent3_brain` so CLI defaults track brain defaults automatically. Bumped version to 2.0.0.
- **Regression guard:** Any future change to method names on `LeadBrain` MUST grep the entire repo for callers (`grep -rn 'brain\.' --include='*.py'`) and update them in lockstep. Added to `debug_protocol.md` Triage Tree 1: "if CLI is broken, first check `main.py` against current `LeadBrain` API." When `prompt_templates.md` is wired into `agent3_brain.py` (Roadmap #5), `main.py` will need a follow-up surgical edit to add `--vertical` flag — flagged in `main.py` docstring under "Note on verticals."

---

---

### BUG-002 — Settings page slider had mismatched label and binding
- **Date discovered:** 2026-05-02 (during initial audit)
- **Date fixed:** 2026-05-02
- **Status:** FIXED
- **Severity:** MEDIUM
- **File(s) affected:** `app_ui.py` (Settings page slider widget) and `agent3_brain.py` (qualify_and_summarize method signature + threshold logic)
- **Symptom:** The Settings page had a slider labeled "Minimum Qualification Score" with min=1 / max=10 / help="Courtesy delay between API calls to respect rate limits." The label said one thing, the help text said another, and the value wrote to `st.session_state.delay_seconds`. Whichever value the user thought they were setting, the OTHER one was unconfigurable.
- **Reproduction (pre-fix):** Open Streamlit UI → Settings page → look at the slider above the "Save Settings" button. Try to change the qualification threshold. You were actually changing the inter-call delay. The qualification threshold had no UI control.
- **Root cause:** Copy-paste bug during a feature merge. Two separate features (qualification threshold + inter-lead delay) had been collapsed into one slider widget. The label belonged to one feature; the binding belonged to the other.
- **Fix applied:** Interpretation C selected — split into two functional sliders (Prompt 16 of Phase 3 bug fixes). Changes: (1) Added `st.session_state.min_qualification_score` initialization (default 5) alongside existing `delay_seconds` initialization. (2) Replaced the single broken slider with two new sliders: "Minimum Qualification Score" (range 1–10, default 5, writes to `min_qualification_score`) and "Inter-Lead Delay (seconds)" (range 1–10, default 2, writes to `delay_seconds`). (3) Added `min_qualification_score` to the settings_to_save persistence dict. (4) Added `min_score: int = 5` parameter to `agent3_brain.LeadBrain.qualify_and_summarize()` signature. (5) Replaced hardcoded `is_valid = score >= 5` with configurable `is_valid = score >= min_score`. (6) Wired UI through to brain via `min_score=min_qualification_score` keyword argument. Default value of 5 preserves backward compatibility with main.py and any other callers that do not pass the new parameter.
- **Regression guard:** When adding any Streamlit slider, the label, help text, and `st.session_state.<key>` binding must reference the same concept. Added to debug_protocol.md Triage Tree 6 (UI stale-data section) and to Patterns Observed below. When adding a new tunable to the UI, follow the wiring chain end-to-end: session_state init → slider widget → settings_to_save dict → settings-resolution block → method call site. Skipping any link in the chain creates ghost controls.

---

### BUG-003 — Default provider/model mismatch caused first-run 400 error
- **Date discovered:** 2026-05-02 (during initial audit)
- **Date fixed:** 2026-05-02
- **Status:** FIXED
- **Severity:** MEDIUM
- **File(s) affected:** `app_ui.py` (session_state default for selected_provider + api_base_url) and `agent3_brain.py` (DEFAULT_API_BASE_URL constant + comment block).
- **Symptom:** Fresh install, user added an API key per the default provider preset (Grok / x.ai), clicked "Start Qualification" — first AI call returned HTTP 400 "model not found." The default model `llama-3.3-70b-versatile` was a Groq-specific Llama variant, not a Grok model. The CLI suffered the same bug because `main.py` imports `DEFAULT_API_BASE_URL` from `agent3_brain` and that constant pointed at the x.ai endpoint.
- **Reproduction (pre-fix):** Fresh checkout, no `settings.json`. Open UI. Settings page showed provider="Grok (x.ai)" and model="llama-3.3-70b-versatile". Added a Grok API key. Ran qualification. 400 error. Or: `python main.py --api-key <key>` with no other args — same 400.
- **Root cause:** Default provider was Grok but default model was a Groq-specific model. Two services with confusingly similar names. The combination shipped as the out-of-box default but had never been validated as a working pair.
- **Fix applied:** Option A selected — default provider switched to Groq (Prompt 18 of Phase 3 bug fixes). Two surgical str_replace operations across two files. Changes: (1) In `app_ui.py`, the session_state initialization now defaults `selected_provider="Groq"` and `api_base_url="https://api.groq.com/openai/v1/chat/completions"`. (2) In `agent3_brain.py`, the `DEFAULT_API_BASE_URL` constant now equals `"https://api.groq.com/openai/v1/chat/completions"` instead of the x.ai endpoint. Comment block above the constant updated to explain the pairing requirement and cross-references this BUG-003 entry. The `DEFAULT_MODEL = "llama-3.3-70b-versatile"` constant was deliberately preserved — it is the correct Groq model. Grok remains fully supported as an opt-in choice via the `provider_presets` dict and Settings page dropdown — only the DEFAULT changed. Total surface area: ~10 lines across 2 files.
- **Regression guard:** Provider preset URL and default model name MUST be validated as a working pair before being shipped as defaults. The deferred long-term improvement (a startup self-test that pings the configured endpoint with a tiny prompt and logs a warning on 400) remains in `context.md` as a future enhancement candidate — not blocking, but recommended for the next round of polish. When adding a new provider preset to `app_ui.py`, MUST simultaneously verify a known-working default model exists for that provider and document the pairing in a comment.

---

## Patterns Observed

*This section captures cross-cutting bug patterns we've seen multiple times — early warning signs to watch for.*

- **Pattern:** Refactors that change method names break orphaned callers. (See BUG-001.) **Mitigation:** Always grep for callers before renaming a method.
- **Pattern:** UI labels drift from their session_state bindings during copy-paste. (See BUG-002.) **Mitigation:** When adding/duplicating Streamlit widgets, verify label + help + binding all describe the same concept.
- **Pattern:** Defaults shipped without end-to-end validation. (See BUG-003.) **Mitigation:** Default provider/model/template combos should pass a smoke test in CI before merge.
- **Pattern:** Vertical-specific logic creeping into agent code. (See BUG-004.) **Mitigation:** Enforced by `custom_rules.md` Rule 5 + planned prompt template externalization.
