"""Consolidated prompts for a fast, grounded pipeline.

Design goals:
  * Few calls (extract + analyze run in parallel; then tailor; then skills+summary)
    instead of ~14 sequential steps.
  * REPHRASE the candidate's real bullets to fit the JD — never invent new
    achievements. Select the strongest, cut the irrelevant. Leave contact +
    education untouched (verbatim).
"""

# 1) EXTRACT — system context = master résumé only (so it caches well).
EXTRACT_CONTENT = """INSTRUCTIONS: Extract the candidate's real content from the master résumé above, exactly as written. Do not invent, merge, split, or duplicate anything. Most-recent first.

Return EACH work experience and project WITH its original bullet points verbatim — these will be rephrased later, not rewritten from scratch.

OUTPUT STRICT JSON:
{"contact": {"name": "...", "phone": "...", "email": "...", "linkedin": "...", "location": "..."},
 "education": [{"degree": "Full degree, major", "school": "University", "dates": "Aug 2024 - May 2026", "gpa": "3.6/4.0"}],
 "certifications": [{"name": "...", "issuer": "...", "url": ""}],
 "skills": ["every skill the candidate actually lists"],
 "experiences": [{"title": "...", "company": "...", "duration": "...", "location": "...", "bullets": ["original bullet verbatim", "..."]}],
 "projects": [{"title": "...", "bullets": ["original bullet verbatim", "..."]}]}

Only real entries. If the résumé has 2 jobs, return exactly 2. Preserve all dates, GPAs, and numbers exactly. Use "" for anything genuinely absent.
"""

# 2) ANALYZE — system context = résumé + JD.
ANALYZE_JD = """INSTRUCTIONS: Analyze the job description above in the context of this candidate.

OUTPUT STRICT JSON:
{"problem_statement": "2-3 sentences on the real business problem behind this hire. Refer to 'the team' or 'this role' — NEVER name the hiring company.",
 "job_title": "the candidate's best-fit DEFENSIBLE title — match the JD's title only when the candidate's real experience supports that role and level; otherwise use their true functional title and never inflate seniority or a specialization they lack (e.g. an analyst-level candidate applying to a 'Quantitative Strategist' role -> 'Quantitative Analyst', not 'Strategist')",
 "tone": "formal | technical | startup | mission-driven",
 "required": ["exact must-have keyword/phrase from the JD, verbatim"],
 "preferred": ["nice-to-have keyword, verbatim"],
 "priority_keywords": ["the 12-18 most important JD terms, ordered by importance"],
 "hard_skills": ["EVERY named hard skill in the JD, verbatim — tools, technologies, languages, frameworks, platforms, databases, cloud services, methodologies, certifications, and named techniques. Include items mentioned only ONCE. This is the ATS keyword target set — be exhaustive (typically 15-35), not a top-N. Exclude soft skills like teamwork/communication."],
 "reframeable": [{"candidate_skill": "what the candidate has", "jd_skill": "the JD's term for it"}],
 "bridge": "one sentence connecting the candidate's strongest real experience to the JD's core problem"}

Extract keywords VERBATIM from the JD — do not paraphrase. priority order matters. For hard_skills, list each named technology/tool individually — never group as "various tools" or "AWS services".
"""

# 3b) ALIGN — raise EXACT-keyword coverage truthfully by rephrasing existing content.
# Runs after TAILOR + the first ATS score. Converts near-misses (concept present,
# different words) and Moderate adjacents (e.g. MySQL↔PostgreSQL) into the JD's exact
# phrase. Never inserts a skill with no candidate basis.
ALIGN_KEYWORDS = """INSTRUCTIONS: Raise EXACT-keyword ATS coverage WITHOUT fabricating anything.

You get the candidate's current bullets and skills, plus TARGET PHRASES — JD keywords not yet present as exact phrases. For each target, decide if the candidate has a REAL basis:
- The concept already appears in a bullet or skill, just worded differently (e.g. "validated data" vs "data validation"), OR
- A clearly adjacent tool/skill is present (e.g. has MySQL and the JD wants PostgreSQL; has scikit-learn and the JD wants machine learning; has Power BI and the JD wants data visualization).
If yes: MINIMALLY edit ONE existing bullet, or add the phrase to the skills list, so the JD's EXACT phrase appears verbatim. If there is NO real basis: SKIP it — never insert a skill the candidate cannot defend in an interview.

RULES:
- Truthful first. Never invent tools, employers, responsibilities, or metrics. Preserve every number EXACTLY — no rounding or inflating.
- Minimal edits only. Mirror the JD's exact wording; keep each bullet ONE sentence, 15-30 words, action verb first, ending in a real metric or named artifact.
- Use the JD's exact phrase verbatim. If the JD uses both acronym and full form, include both.
- Do NOT add or remove bullets — return the SAME number of bullets per experience, in the SAME order.
- No AI-tell words (delve, spearheaded, synergy, orchestrated, leverage, harness, foster, cutting-edge, tapestry). No special symbols (# ; _ ---).

OUTPUT STRICT JSON (same shape as the input, edited in place):
{"experiences": [{"bullets": ["...", "..."]}], "skills": [{"name": "...", "skills": ["...", "..."]}]}
"""

# 3) TAILOR — rephrase + select + cut the real bullets. Context = résumé + JD; the
# user message carries the extracted entries + analysis + per-entry target counts.
TAILOR = """INSTRUCTIONS: Tailor the candidate's REAL experience to this job.

FRAME AS A PROBLEM SOLVER: every kept bullet should make the hiring manager think
"this person has already dealt with exactly what we are dealing with." Lead each role
with the bullet that most directly proves solving THIS job's problem.

CRITICAL — this is rephrasing, not rewriting:
- REPHRASE each kept bullet to mirror the JD's exact nouns, verbs, and keywords.
- Do NOT invent achievements, employers, responsibilities, or metrics — the WHAT happened
  and the NUMBERS must already be true for the candidate. (Surfacing a REAL tool/method the
  candidate genuinely has — see REFRAME below — is allowed and encouraged, not invention.)
- PRESERVE every source metric EXACTLY — never round, inflate, deflate, or invent a
  number, percentage, count, or timeframe. If the original has no metric, do not add one.
- REFRAME WITH REAL TOOLS (truthful facet-surfacing — this is how a strong human tailors the
  same history to different jobs): the candidate's full real skill inventory is provided below.
  When a kept bullet describes work where the candidate GENUINELY used a JD-required tool,
  method, or framework they actually have, name it in the JD's exact words. Example: one risk
  model the candidate built reads "using regression analysis and SQL" for a quant JD, or "using
  SAS Data Step and Proc SQL" for a SAS JD — same work, same 18% metric, the TRUE facet each JD
  asks for. This is Bucket-2 reframing (a real analogue in the JD's language), NOT invention.
  NEVER attach a tool to a bullet where the candidate did not actually use it; if unsure it
  applies to that specific work, leave it out.
- SELECT the most JD-relevant bullets per entry, up to the target count below, and
  CUT the rest. Fewer strong bullets beat many weak ones — never pad to hit a number.
- ORDER bullets strongest-proof-first (quantified impact that matches the JD leads).
- STRUCTURE each bullet as action + what you did + how (1-2 real skills/tools) +
  measurable outcome (XYZ / STAR). One sentence, 15-30 words, ending in a period.
- ANTI-PARROTING: do NOT copy noun-lists or skill phrases straight from the JD. Prove a
  skill by naming ONE concrete artifact you actually built or used with it (a pipeline, a
  dashboard, a model, a report), woven in naturally — not by listing the keyword.
- Each kept bullet: action verb first, ending in the bullet's real metric OR a concrete
  named artifact. No slashes, no # ; _ ---.
- ACTION VERBS MUST ALL BE UNIQUE across the ENTIRE résumé — never reuse a verb
  (no two bullets starting with "Developed"). Draw from: Built, Engineered, Designed,
  Implemented, Analyzed, Automated, Deployed, Optimized, Delivered, Streamlined, Led,
  Architected, Reduced, Accelerated, Standardized, Drove, Established,
  Produced, Modeled, Validated, Consolidated, Translated, Partnered, Directed.
- BANNED weak openers — never start a bullet with any of: "Responsible for", "Worked on",
  "Helped with", "Assisted", "Duties included", "Tasked with". Lead with a real action verb.
- BANNED AI-tell words — never use any of: delve, spearheaded, synergy, synergized,
  orchestrated, tapestry, unwavering, foster, harness, testament, paramount, visionary,
  cultivated, leverage, leveraging, cutting-edge. Write like a competent human, not a bot.
- NO REPEATED PHRASES across bullets — vary wording. Do not reuse multi-word stock
  phrases like "gathering, cleaning, and preparing" or "to support business planning".
- Bridge line per role: ONE short line, max 16 words, in the candidate's own voice
  (implied first person). It connects this role to the TYPE of challenge the job
  describes. STRICT: never write the target company's name, never write the
  candidate's name, never use third person, no em-dash meta-commentary. Refer to
  the challenge generically. Good: "Risk analytics work maps directly to large-scale
  loan-portfolio exposure modeling." Bad: "Ascensus needs a BA who… Praneeth did…".
  If no specific, natural connection exists for a role, return "" (empty) — do not force one.
- Projects: keep only those relevant to the JD and rephrase their bullets; drop the rest.
{star_clause}{lp_clause}

TARGET BULLET COUNTS (keep UP TO this many per entry, in order; fewer is fine):
{plan}

OUTPUT STRICT JSON (experiences in the SAME order as given):
{{"experiences": [{{"bridge_line": "...", "bullets": ["rephrased bullet", "..."]}}],
  "projects": [{{"title": "exact project title", "bullets": ["rephrased bullet", "..."]}}]}}
"""

# 4) SKILLS + SUMMARY — one call. Context = résumé + JD + the tailored bullets.
SKILLS_SUMMARY = """INSTRUCTIONS: Using the JD and the candidate's tailored experience above, produce the skills section and the summary together.

SKILLS: 3-4 categories, 18-24 skills TOTAL (not per category), ordered by JD priority. Category names use the JD's domain language. Include the candidate's real skills that match the JD plus key JD hard skills. Each skill is a CONCISE keyword (e.g. "Python", "Tableau", "Snowflake"). DO NOT add descriptions or explanations in parentheses (NEVER "Tableau (interactive dashboard development)", "Python (statistical modeling)") and DO NOT add proficiency qualifiers (no "- advanced"). The ONLY allowed parenthetical is the full form of a genuine ACRONYM where it aids ATS matching, e.g. "SQL (Structured Query Language)", "ETL (Extract, Transform, Load)" — nothing else. Every listed skill should appear in at least one bullet. Keep it categorized — never a comma-run wall of text.

SUMMARY (written last): a natural, impersonal summary that describes what THIS candidate has ACTUALLY done, phrased in the JD's language — the way a strong human-written summary reads, NOT a keyword template.
HARD RULES — breaking any makes it invalid:
- TITLE: open with the candidate's best-fit, DEFENSIBLE title — the role their real experience supports. Use "{job_title}" as the anchor, but mould it to the candidate: never inflate seniority or claim a level the résumé does not show (an analyst-level candidate applying to a "Strategist" role opens as "Analyst", not "Strategist").
- DOMAIN — TRUTHFUL: name a domain or specialization (e.g. "network deployment", "fraud detection", "wealth management") ONLY if the candidate's real bullets above demonstrate it. If they genuinely have it, name it in the JD's exact words — it is a strong match. If they do NOT, do not claim it: lead with the title and describe their actual, transferable experience instead. Never imply experience in a field the résumé does not show.
- GROUNDED: every clause must trace to the candidate's real experience above. Include at least ONE concrete real achievement with its EXACT metric (e.g. "reduced monitoring time by 75%"). No generic filler, no invented numbers.
- NEVER the hiring company's name (no "Sallie Mae needs…"). NEVER the candidate's name or "he/she/they" — impersonal, describe the role not a person. No "I", "my", "our". No "X needs someone who…".
- Third-person neutral. EXACTLY 4 sentences. AT MOST 75 words total. AT MOST 20 words per sentence. End on impact or value, not a bare skill name.
- Natural human voice — sound like a person describing their own work, not a template. No AI-tell words (delve, spearheaded, synergy, orchestrated, leverage, harness, foster, cutting-edge, tapestry, unwavering).
- Tone: {tone}. No special symbols (# ; _ ---).

OUTPUT STRICT JSON:
{{"skills": [{{"name": "...", "skills": ["...", "..."]}}, {{...}}, {{...}}, {{...}}], "summary": "..."}}
"""

# 5) QUALIFY — standalone "Am I qualified?" pre-check. Context = résumé + JD.
# Honest, decision-useful. Distinguishes gaps optimization CAN fix from gaps it CANNOT.
QUALIFY = """INSTRUCTIONS: Assess whether THIS candidate is genuinely qualified for THIS job, using only the résumé and job description above. Be honest and decision-useful — a real person decides whether to apply based on this. Do NOT inflate. Do NOT credit qualifications the résumé does not actually show.

Judge on the basis real recruiters and ATS systems gate on:
1. HARD REQUIREMENTS (knockout filters that auto-reject before any keyword scoring): years of experience required vs. what the candidate demonstrably has; required degree level/field; required certifications or licenses; explicitly must-have skills.
2. MUST-HAVE SKILL COVERAGE: of the JD's required hard skills, how many does the candidate genuinely have — directly, or via a close and DEFENSIBLE adjacent (e.g. MySQL for PostgreSQL)?
3. NICE-TO-HAVE COVERAGE: preferred skills.
4. SENIORITY ALIGNMENT: is the candidate's level a match, under-qualified, or over-qualified for the role's scope?
5. DOMAIN RELEVANCE: relevant industry/domain exposure.

For each hard requirement: mark met / partial / missing, citing the résumé evidence (or noting its absence). A missing hard requirement is a BLOCKER. For every gap, decide honestly whether résumé OPTIMIZATION can fix it (wording, exact-keyword phrasing, surfacing buried-but-real experience) or CANNOT (genuinely missing years, degree, or core skills — no amount of rewording creates them).

VERDICT TIERS:
- strong_fit (80-100): meets all hard requirements and most must-have skills. Apply with confidence.
- qualified (60-79): meets hard requirements, covers the majority of must-haves; minor gaps. Solid to apply.
- stretch (40-59): misses some requirements but has defensible adjacents; possible with strong positioning, realistic odds.
- not_a_match (0-39): misses multiple hard blockers with no honest reframe; optimization will not bridge the gap.

OUTPUT STRICT JSON:
{"verdict": "strong_fit | qualified | stretch | not_a_match",
 "fit_score": 0,
 "headline": "one honest sentence the candidate reads first",
 "experience_years": {"required": "5+ or empty if unstated", "candidate": "best estimate from résumé", "meets": true},
 "education": {"required": "JD requirement or empty", "candidate": "highest relevant degree", "meets": true},
 "hard_requirements": [{"requirement": "verbatim JD must-have", "status": "met | partial | missing", "evidence": "résumé proof, or what is absent", "blocker": true}],
 "must_have_skills": {"matched": ["..."], "missing": ["..."], "coverage_pct": 0},
 "nice_to_have_skills": {"matched": ["..."], "missing": ["..."]},
 "strengths": ["concrete, résumé-grounded reasons this candidate fits"],
 "gaps": [{"gap": "...", "severity": "blocker | major | minor", "fixable_by_optimization": false}],
 "recommendation": "Plain guidance: should they apply, and would résumé optimization meaningfully help? Name explicitly what optimization can and cannot fix here."}
"""

# 7) EXTRACT_TOOLS — for the Confirm-Your-Tools step. Pulls flat tool lists from
# both sides so the taxonomy resolver can map coverage. Context = résumé + JD.
EXTRACT_TOOLS = """INSTRUCTIONS: From the résumé and job description above, extract two flat lists of TOOLS / TECHNOLOGIES / FRAMEWORKS / PLATFORMS — named software, languages, databases, libraries, cloud services, methodologies, certifications. EXCLUDE soft skills (teamwork, communication).

OUTPUT STRICT JSON:
{"candidate_tools": ["every named tool the candidate actually lists or describes using, verbatim"],
 "jd_tools": ["every named tool the job asks for, verbatim"]}

Be exhaustive on both sides. Names only (e.g. "Power BI", "SAS", "Snowflake"), no descriptions.
"""

# 6) COVER_LETTER — narrative, recruiter-facing. Context = résumé + JD. Names the
# company (unlike the résumé). Grounded only in real experience. Heavy tier.
COVER_LETTER = """INSTRUCTIONS: Write a tailored cover letter for this candidate and this job, grounded ONLY in the candidate's real experience above. Never invent achievements, employers, responsibilities, or metrics.

STRUCTURE (3-4 short paragraphs, 250-350 words total):
1. Opening: name the role and the company; lead with the company's core need or problem and signal the candidate solves exactly that. No "I am writing to apply for…" filler.
2. Proof: 1-2 of the candidate's strongest, most relevant REAL achievements with their exact metrics, mapped to the JD's priorities — show "I have already done this."
3. Fit: why this candidate specifically — connect their background to the role's challenges and, if evident, the company's mission or domain.
4. Close: brief, confident, forward-looking; invite a conversation.

VOICE:
- First person, warm but professional; match the JD's tone.
- Human voice — NO AI-tell words (delve, spearheaded, synergy, orchestrated, leverage, harness, foster, cutting-edge, tapestry, unwavering, paramount). No clichés ("excited to apply", "perfect fit", "team player", "hit the ground running", "proven track record").
- Preserve every metric exactly. No special symbols (# ; _ ---). No em-dash meta-commentary.

The DETAILS below give the company, role, candidate name, tone, and who to address it to.

OUTPUT STRICT JSON:
{"greeting": "Dear Hiring Team,", "paragraphs": ["...", "...", "..."], "closing": "Sincerely,", "signature": "Candidate Name"}
"""
