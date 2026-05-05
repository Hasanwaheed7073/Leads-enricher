# Debug Protocol — Lead Sniper AI

> **Purpose of this file:** When something breaks, READ THIS FIRST before grepping or guessing. This file maps failure symptoms to the most likely cause + the fastest path to root cause. Saves hours per debug session.
>
> **Update discipline:** When a new failure category emerges and is debugged, add it here as a triage tree. When a triage path proves wrong, fix it. This file is a living playbook — accuracy over completeness.
>
> **Required reading per `gemini.md` Mandatory Read Order:** consulted on every debugging task before any code is touched.

---

## Universal First Steps (Always Do These Before Triage)

When ANY failure is reported, run through these in order:

1. **Read the error message.** Not the symptom the user reported — the actual exception text or HTTP code. Most bugs are misdiagnosed because step 1 was skipped.
2. **Identify which agent / layer is failing.** Lead Sniper has 5 layers — UI (`app_ui.py`) → Orchestrator (`main.py`) → Ingestor (Agent 1) → Scout (Agent 2) → Brain (Agent 3). The error usually comes from one of them. Check the log file name in the traceback.
3. **Check `error_log.md`** for any past bug with matching symptom or affected file. If found, jump to its regression guard.
4. **Check `context.md` Known Issues section.** If the bug is already documented as OPEN, don't re-discover it.
5. **Check `.gitignore` is honored.** Sometimes "missing file" bugs are because a runtime artifact got gitignored. Settings.json missing? Logs missing? They auto-regenerate — confirm before debugging.

Only THEN proceed to the triage trees below.

---

## Triage Tree 1 — "Pipeline crashes / no output"

**Symptom:** Running `python main.py` or clicking "Start Qualification" produces no enriched leads, or crashes immediately.

```
Is the error from main.py?
├─ YES → BUG-001 territory. main.py calls non-existent method.
│        Fix: see error_log.md BUG-001. Use UI instead until fixed.
│
└─ NO → Is it from app_ui.py?
        ├─ YES → Check session_state initialization (lines 535-572).
        │        Most UI crashes = uninitialized session_state key.
        │
        └─ NO → Check which agent log has the latest entry:
                ├─ agent1_ingestor.log → CSV format issue (Triage Tree 2)
                ├─ agent2_scout.log    → Scraping issue (Triage Tree 3)
                └─ agent3_brain.log    → AI/LLM issue (Triage Tree 4)
```

---

## Triage Tree 2 — "Agent 1 (Ingestor) returns empty list"

**Symptom:** Pipeline aborts with "AGENT 1 returned zero valid leads" or similar.

```
Is the CSV file path correct and the file exists?
├─ NO → Path resolution issue. Check working directory.
│
└─ YES → Open the CSV. Does it have a 'Website' column?
         ├─ NO → Schema mismatch. Agent 1 requires Website column.
         │       (Other columns are optional and missing-tolerated.)
         │
         └─ YES → Are the Website values prefixed with http:// or https://?
                  ├─ NO → URLs without scheme are rejected (custom_rules:
                  │        ZERO-COST means no live URL repair). User must fix CSV.
                  │
                  └─ YES → Encoding issue. Check if CSV is UTF-8.
                           Excel often saves as UTF-16 or with BOM.
                           Agent 1 already handles utf-8-sig, but UTF-16 fails.
                           Fix: re-save as UTF-8 in a real text editor.
```

**Files to check:** `agent1_ingestor.py:163` (ingest_csv), `agent1_ingestor.py:227` (Website validation), `agent1_ingestor.log`.

---

## Triage Tree 3 — "Agent 2 (Scout) fails to scrape websites"

**Symptom:** Most/all leads get `scrape_error` or `domain_alive: False`.

```
Is the failure pattern "DNS failed for ALL leads"?
├─ YES → Network / firewall / VPN issue on the host running the app.
│        Test: ping any HVAC website manually. If that fails, infrastructure issue.
│
└─ NO → Is the failure pattern "DNS works, HTTP times out"?
        ├─ YES → Sites blocking the User-Agent.
        │        Agent 2 already rotates 5 UAs (lines 85-101) but some sites
        │        block all non-browser UAs. Jina fallback should kick in.
        │        Check agent2_scout.log for "Jina Reader fallback" lines.
        │        If Jina also fails → site is genuinely unreachable.
        │
        └─ NO → Is the failure "got HTML but content < 200 chars"?
                ├─ YES → JS-heavy SPA. Jina fallback should trigger automatically
                │        (agent2_scout.py:582). If not triggering, check the
                │        condition logic at that line.
                │
                └─ NO → 4xx/5xx errors? Cloudflare bot protection.
                        Jina fallback handles most of these. Check if Jina
                        Reader is reachable (it has its own free-tier limits).
```

**Files to check:** `agent2_scout.py:476` (scrape_website), `agent2_scout.py:453` (_scrape_via_jina), `agent2_scout.log`.

**Common false alarms:** Some HVAC contractors run their websites for 6 months then let domains expire. "Dead domain" is often correct — not a bug.

---

## Triage Tree 4 — "Agent 3 (Brain) returns errors / fallback responses"

**Symptom:** Lead scores are all 0, summaries say "Error.", pitches say "Error generating pitch."

```
Is the error "All API keys exhausted"?
├─ YES → Free tier quota burned. Wait 60s OR add more keys to rotation.
│        See ADR-003 — key rotation behavior.
│
└─ NO → Is the error HTTP 400 "model not found"?
        ├─ YES → BUG-003 territory. Provider/model mismatch.
        │        Check Settings: provider URL must match the model.
        │        Grok URL + Llama model = 400. Use Groq URL with Llama,
        │        or Grok URL with grok-3-mini.
        │
        └─ NO → Is the error HTTP 401/403?
                ├─ YES → API key invalid / revoked / wrong provider.
                │        Confirm key is for the URL configured.
                │
                └─ NO → Is the error "JSON parse failed after 3 layers"?
                        ├─ YES → LLM returned non-JSON despite response_format.
                        │        Some providers ignore response_format on certain
                        │        models. Try a different model on same provider.
                        │        Raw output is in agent3_brain.log — inspect to
                        │        understand if model was returning prose instead.
                        │
                        └─ NO → Network timeout. AI_REQUEST_TIMEOUT=30s
                                (agent3_brain.py:91). Increase if needed.
```

**Files to check:** `agent3_brain.py:294` (_call_api), `agent3_brain.py:357` (_call_with_rotation), `agent3_brain.py:236` (_parse_json_response), `agent3_brain.log`.

---

## Triage Tree 5 — "All leads scoring suspiciously high (false positives)"

**Symptom:** Every lead is scoring 8-10/10 even when websites are clearly not the target industry.

```
Are the post-AI score caps being applied?
├─ NO → Bug in cap logic. Check agent3_brain.py:736-770.
│        Caps must execute AFTER the AI returns a score, BEFORE it's stored.
│        Common cause: the score variable was made a string somewhere and
│        the integer comparison silently fails.
│
└─ YES → Are verification signals reaching the cap logic?
         ├─ NO → Agent 2 is not propagating signals correctly.
         │       Check the merge in app_ui.py:1217-1221 or main.py:266-270.
         │
         └─ YES → Caps applied but score still too high?
                  Check the prompt template — is the AI being told the right
                  industry? Career Coaching toggle on but target is HVAC =
                  wrong prompt evaluating leads against wrong rubric.
                  See BUG-004 — until templates are externalized, this can drift.
```

**Files to check:** `agent3_brain.py:736` (cap logic), `agent3_brain.py:609` (HVAC prompt), `agent3_brain.py:617` (Career Coaching prompt).

---

## Triage Tree 6 — "Streamlit UI shows stale data / changes don't appear"

**Symptom:** User uploads new CSV but old data persists. Or settings save but don't take effect.

```
Is the file_id check working in app_ui.py:1005?
├─ NO → Cache invalidation broken. The session_state.current_file_id
│        comparison should detect new uploads. If it's stuck, force a hard
│        refresh or clear session state.
│
└─ YES → Is settings.json being read on EVERY rerun or only on first load?
         ├─ Only first load → settings_loaded flag stuck (line 553-555).
         │                    Restart Streamlit server to reset.
         │
         └─ Every rerun → File watcher conflict. Streamlit auto-reloads on
                          settings.json change in dev mode. In prod, use the
                          "Save Settings" button + manual refresh.
```

**Files to check:** `app_ui.py:1003` (caching block), `app_ui.py:43` (load_settings), `app_ui.py:553` (settings_loaded gate).

---

## Triage Tree 7 — "Adding a new vertical doesn't work"

**Symptom:** Tried to add a new industry, but the AI still scores leads against HVAC.

```
Until Roadmap item #5 is complete, this is BUG-004 territory.
Vertical logic is hardcoded in agent3_brain.py.
Current verticals supported: HVAC (default) + Career Coaching (via toggle).

Do NOT add another `elif is_X_vertical:` branch — that violates
custom_rules.md Rule 5.

Instead: wait for the prompt_templates.md externalization refactor,
then adding a new vertical becomes a one-file edit.
```

**Files to check:** `agent3_brain.py:609`, `agent3_brain.py:840`, `app_ui.py:683`, `prompt_templates.md` (once externalized).

---

## Anti-Patterns to NEVER Apply When Debugging

1. **Do NOT add print() statements.** Use the existing logger. (custom_rules.md Tier 3, Rule 12.)
2. **Do NOT comment out failing code to "see if the rest works."** That's how regressions ship. Fix it or revert it.
3. **Do NOT increase a timeout to mask a real failure.** If something needs >30s, find out why before raising the limit.
4. **Do NOT catch and silence exceptions to make logs cleaner.** Self-healing means catch + log + recover, NEVER catch + ignore.
5. **Do NOT fix one symptom of a bug pattern.** If verification signals aren't reaching the cap logic, fix the merge — don't hardcode signal values.
6. **Do NOT assume the LLM is the problem.** It usually isn't. Check the request payload, the response shape, the JSON repair layers, and the cap logic FIRST.

---

## When the Triage Trees Don't Cover It

If the failure doesn't match any tree above, the protocol is:

1. Add detailed logging at the failure point (do NOT remove later — keep it).
2. Reproduce 3 times to confirm it's deterministic.
3. Once root cause is found, add a new entry to `error_log.md` AND a new triage tree to this file.
4. The new tree should answer: "if this symptom appears again, what's the fastest path to fix?"

This is how the protocol grows. Every novel failure becomes future debugging speed.
