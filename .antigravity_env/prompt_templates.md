# Prompt Templates Registry — Lead Sniper AI

> **Purpose of this file:** The single source of truth for every industry-specific prompt used by Agent 3 (Brain). To add a new vertical (Roofing, Solar, Dental, etc.), edit this file — DO NOT modify any `.py` file. Per `custom_rules.md` Rule 5 (No Hardcoded Verticals).
>
> **Status note:** As of 2026-05-02, this file is the documented spec but is NOT YET wired into `agent3_brain.py`. The agent currently uses an `is_career_coaching` boolean and hardcoded f-string prompts (BUG-004). Wiring is scheduled in Roadmap item #5. Until then, this file is the design target — when the refactor ships, the agent will load templates from here at runtime.
>
> **Update discipline:** Adding a vertical = appending a new template block below. Removing a vertical = marking it `Status: Deprecated` (do not delete — clients may be using it). Modifying a live vertical's prompt = update + append a note to `decisions.md` explaining why.

---

## Template Schema (every vertical MUST follow this exact structure)

Each vertical is a YAML-like block with these required fields:

```
### TEMPLATE — [Vertical Name]
- **id:** snake_case_identifier  (used as the dropdown value in UI; never change once shipped)
- **display_name:** Human-Readable Name  (shown in UI dropdown)
- **status:** Active | Beta | Deprecated
- **target_industry_phrase:** The exact phrase used in prompts (e.g., "HVAC contractor", "Career Coach")
- **keywords:** Comma-separated industry-specific terms used for content matching (e.g., heating, cooling, AC, furnace)
- **system_prompt_phase1:** The Phase 1 system prompt — qualification + scoring role definition
- **user_prompt_phase1:** The Phase 1 user prompt template — uses placeholders {clean_lead}, {clean_scraped}, {verification_context}, {target_industry}
- **scoring_rubric:** Markdown bullet list of score-band definitions specific to this vertical
- **required_evidence:** What the website MUST show to score above 5 (vertical-specific)
- **system_prompt_phase2:** The Phase 2 system prompt — pitch generation role
- **user_prompt_phase2:** The Phase 2 user prompt template — uses placeholders {lead_name}, {company}, {summary}
- **pitch_rules:** Markdown bullet list of vertical-specific pitch constraints
```

**Placeholder convention:** Curly-brace placeholders like `{clean_lead}` are replaced at runtime by the loader. NEVER use Python f-string `{x}` syntax mixed with template syntax — the loader uses `str.format()` or equivalent and will collide.

**Forbidden in templates:**
- Hardcoded API keys, URLs, model names
- Client-specific names or branding
- References to other verticals (each template is self-contained)
- Code blocks (templates are prompts, not code)

---

## Active Templates

---

### TEMPLATE — HVAC Contractor
- **id:** `hvac_contractor`
- **display_name:** HVAC Contractor
- **status:** Active
- **target_industry_phrase:** `HVAC contractor`
- **keywords:** heating, cooling, AC, air conditioning, furnace, HVAC, ventilation, ductwork, refrigeration, heat pump, boiler, thermostat

#### Phase 1 — Qualification

**system_prompt_phase1:**
```
You are an expert HVAC industry analyst and lead verification specialist. Your job is to determine if a business is a REAL, ACTIVE HVAC contractor with a working website. You must cross-reference ALL verification signals. Do NOT qualify based on company name alone — you need real evidence. You ALWAYS respond with raw JSON only — no markdown, no code fences, no explanation.
```

**user_prompt_phase1:**
```
Analyze ALL signals to determine if this lead is a REAL, VERIFIED business in the "{target_industry}" industry.

Lead data:
{clean_lead}

Scraped website context:
{clean_scraped}

Verification signals:
{verification_context}

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
{{"is_valid": true, "score": 8, "summary": "one sentence explaining the score, mentioning which checks passed/failed", "category": "Commercial HVAC"}}
```

**scoring_rubric:** Embedded in `user_prompt_phase1` above (Scoring Rubric section).

**required_evidence:** Page content must mention at least one of: heating, cooling, AC, air conditioning, furnace, HVAC, ductwork, heat pump, boiler. Generic "home services" language without specific HVAC mentions caps the score at 4.

#### Phase 2 — Pitch

**system_prompt_phase2:**
```
You are an expert B2B SDR (Sales Development Representative) with 10 years of experience writing high-converting cold outreach emails. You write concise, personalized, conversational pitches. You ALWAYS respond with raw JSON only — no markdown, no code fences, no explanation.
```

**user_prompt_phase2:**
```
Write a 3-sentence personalized cold email pitch to {lead_name} at {company}.

Use this business summary for context:
"{summary}"

Rules for the pitch:
- Sentence 1: Open by referencing a SPECIFIC detail from the summary (not generic flattery).
- Sentence 2: Clearly state the value proposition — what you can do for THEM specifically.
- Sentence 3: End with a soft, low-friction call-to-action.
- Keep it conversational, not corporate.

Return ONLY a raw JSON object with one key:
{{"pitch": "Your three sentence pitch here."}}
```

**pitch_rules:**
- Reference a specific detail from the summary in sentence 1 (no generic flattery).
- Sentence 2 must propose a concrete value prop (not vague "help you grow").
- Sentence 3 ends with a low-friction CTA (not a hard ask).

---

### TEMPLATE — Career Coach
- **id:** `career_coach`
- **display_name:** Career Coach
- **status:** Active
- **target_industry_phrase:** `Career Coach`
- **keywords:** career coaching, executive coaching, professional development, leadership coaching, life coaching, career transition, resume, interview prep, job search

#### Phase 1 — Qualification

**system_prompt_phase1:**
```
You are an expert Career Coaching industry analyst and lead verification specialist. Your job is to determine if the provided data belongs to a REAL, ACTIVE Career Coach or coaching professional. Focus on verifying if the data is true or false based on the signals. You ALWAYS respond with raw JSON only — no markdown, no code fences, no explanation.
```

**user_prompt_phase1:**
```
Analyze ALL signals to verify if this lead is a REAL Career Coach or related professional.

Lead data:
{clean_lead}

Scraped website context:
{clean_scraped}

Verification signals:
{verification_context}

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
{{"is_valid": true, "score": 8, "summary": "one sentence explaining the score, mentioning which checks passed/failed", "category": "Executive Coach"}}
```

**scoring_rubric:** Embedded in `user_prompt_phase1` above.

**required_evidence:** Page content must reference coaching services, professional development, career transition, or related advisory work. Generic "consulting" without coaching specificity caps at 5.

#### Phase 2 — Pitch

**system_prompt_phase2:**
```
You are an expert B2B SDR (Sales Development Representative) with 10 years of experience writing high-converting cold outreach emails. You write concise, personalized, conversational pitches. You ALWAYS respond with raw JSON only — no markdown, no code fences, no explanation.
```

**user_prompt_phase2:**
```
Write a 3-sentence personalized cold email pitch to {lead_name} at {company}, who is a Career Coach.

Use this business summary for context:
"{summary}"

Rules for the pitch:
- Sentence 1: Open by referencing a SPECIFIC detail from the summary (not generic flattery).
- Sentence 2: Clearly state the value proposition — what you can do to help them grow their coaching business.
- Sentence 3: End with a soft, low-friction call-to-action.
- Keep it conversational, not corporate.

Return ONLY a raw JSON object with one key:
{{"pitch": "Your three sentence pitch here."}}
```

**pitch_rules:**
- Acknowledge that Career Coaches are themselves marketing-savvy — generic SDR language will be rejected on sight.
- Reference their specific coaching niche from the summary (executive, transition, leadership, etc.).
- CTA should be a peer-to-peer offer, not a sales pitch.

---

## Reserved Slots (planned, not yet built)

The following verticals are planned per `context.md` Roadmap and will be added as templates when needed. They are reserved here so the IDE knows what's coming and doesn't suggest competing approaches.

- **TEMPLATE — Roofing Contractor** (`roofing_contractor`)
- **TEMPLATE — Solar Installer** (`solar_installer`)
- **TEMPLATE — Dental Practice** (`dental_practice`)
- **TEMPLATE — Real Estate Agent** (`real_estate_agent`)
- **TEMPLATE — SaaS Founder** (`saas_founder`)
- **TEMPLATE — Insurance Broker** (`insurance_broker`)
- **TEMPLATE — Legal Services** (`legal_services`)

Do NOT pre-emptively author these. Each will be added in a dedicated prompt when the agency takes on a client in that vertical.

---

## Deprecated Templates

*None yet. When a template is no longer used, mark its `status:` field as `Deprecated` and move it here. Do not delete — old client deployments may still reference it.*

---

## Adding a New Vertical — Step-by-Step

When the agency needs to support a new industry:

1. **Confirm zero-cost compliance.** Does this vertical require any paid data source (e.g., specialized lead databases)? If yes, find a free alternative or refuse.
2. **Copy the schema** from the Template Schema section above.
3. **Fill in every field.** Required fields are non-negotiable.
4. **Identify keywords specific to that industry.** These power content-match heuristics in scoring.
5. **Define vertical-specific evidence requirements.** What MUST appear on a website to qualify? (e.g., for Solar: photovoltaic, kW system, panel installation; for Dental: DDS, hygiene, restorative.)
6. **Tune the scoring rubric for that vertical's signal density.** Some industries have richer web presences (Real Estate) and can demand higher evidence; others (Insurance) often have thinner sites and need looser rubrics.
7. **Append the template block to the Active Templates section.**
8. **Append an entry to `decisions.md`** with ADR-NNN documenting why this vertical was added and any unique challenges.
9. **Do NOT modify any `.py` file.** If the loader infrastructure is missing, that's a separate prompt — flag it but do not work around it.

---

## Loader Contract (target spec for the future refactor)

When `agent3_brain.py` is refactored to use this file (Roadmap #5), the loader must:

1. Parse this markdown file at startup, extracting all `Active` templates by `id`.
2. Expose them as a dict keyed by `id`: `{"hvac_contractor": {...}, "career_coach": {...}}`.
3. Provide a function: `get_template(template_id) → dict` that returns the parsed template.
4. Validate that every required field is present at load time. Missing field = log CRITICAL and refuse to start.
5. Replace placeholders (`{clean_lead}`, `{lead_name}`, etc.) at call time using `str.format_map()` to allow missing keys to fail explicitly rather than silently.
6. Cache the parsed templates (parse once per process lifetime).
7. Surface the `display_name` list to the UI for the dropdown — never the raw `id`.
8. Reject any attempt to reference a vertical not present as an `Active` template (no fallback to a default — explicit > implicit).

This contract becomes ADR-011 in `decisions.md` when the refactor ships.
