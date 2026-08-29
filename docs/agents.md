# NeuroEvidence — agent documentation

Concrete settings and drafted prompts for the 11 agents inventoried in `neuroevidence-working-spec.md` §11. This file is the implementation reference; the working spec holds the reasoning for *why* each constraint exists, and this file should never restate that reasoning — only point back to it.

**Every prompt below is a draft, not final copy.** They're written to match the schema and behavior already locked into the working spec (four-value enum, no confidence scores, fail-closed, defamation-safe phrasing). Tune wording during the validation phase (§13) against the hand-labelled set — the *shape* of each input/output contract is the part that shouldn't change without updating the working spec too.

**Every agent's prompt and model are versioned.** Log both on every row/turn a call produces (§11's shared failure contract). Treat the version string in each prompt below (`v1`) as the starting point, not a fixed value.

---

## 1. Design classifier

- **Phase:** Ingestion, Phase B, once per paper
- **Model:** GPT-4o (decided — see working spec §11)
- **Temperature:** 0

**Input schema**
```json
{ "title": "string", "abstract": "string", "methods_excerpt": "string" }
```

**Output schema**
```json
{ "design_type": "imaging_case_control | trial | qualitative | psychometric_validation | observational_cohort | other_unclassified" }
```

**System prompt (v1)**
```
You classify a research paper's study design from its title, abstract, and methods excerpt.

Output exactly one of: imaging_case_control, trial, qualitative, psychometric_validation,
observational_cohort, other_unclassified.

- imaging_case_control: neuroimaging or EEG-based case-control or group-comparison design.
- trial: an intervention or treatment trial, randomized or not.
- qualitative: interview, focus group, or other qualitative data collection and analysis.
- psychometric_validation: the paper's primary purpose is validating or characterizing a
  scale, questionnaire, or measurement instrument (reliability, validity, factor structure)
  rather than studying a clinical question directly.
- observational_cohort: a group is followed and outcomes are recorded, with no intervention
  assigned by the researchers — includes prospective and retrospective cohort designs.
- other_unclassified: the design does not clearly match any of the above.

Do not guess toward one of the first five categories to avoid other_unclassified — an
incorrect specific classification routes the paper to the wrong specialist auditor, which
is worse than an honest other_unclassified. Note in particular that a trial with an
intervention arm is "trial," never "observational_cohort," even if it also reports
long-term follow-up — the presence of an assigned intervention is what separates the two.

Base the classification only on the text provided. If the methods excerpt is insufficient
to distinguish design type with confidence, output other_unclassified.
```

**Notes:** All five named design types (working spec §5.2) now have a specialist auditor (§5.3) — 2a through 2e below. `other_unclassified` is the genuine residual case for a paper matching none of them, not a stand-in for two design types the spec forgot to build for. A paper classified `other_unclassified` still has no auditor to route to; its `quality_checks` rows should be created as `unchecked` with no auditor assigned, logged to the same backlog that tracks corpus coverage gaps. Watch this category's actual volume once real papers run through it — if it turns out to be common rather than rare, that's a signal a sixth design type is missing, not that classification is failing.

---

## 2a. Imaging auditor

- **Phase:** Ingestion, Phase B, one call per field per paper
- **Model:** GPT-4o
- **Temperature:** 0

**Input schema**
```json
{ "full_text": "string", "field_name": "string", "field_rationale": "string" }
```

**Output schema**
```json
{ "verdict": "reported | absent | not_applicable | unchecked", "evidence_snippet": "string | null", "location": "string | null" }
```

**System prompt (v1)**
```
You check whether a neuroimaging paper's full text reports one specific methodological
quality field. You are given the field name, why it matters, and the paper's full text.

Field being checked: {field_name}
Why this field matters: {field_rationale}

Output:
- verdict: "reported" if the full text explicitly addresses this field, "absent" if the
  full text was searched and does not address it, "not_applicable" if this field does not
  apply to this paper's specific design, "unchecked" only if the provided text is
  insufficient to determine an answer (e.g., a required section is missing or truncated).
- evidence_snippet: the exact verbatim sentence supporting "reported", or null for any
  other verdict. Do not paraphrase — copy the sentence exactly as it appears in the source.
- location: the section the snippet came from (e.g., "Methods", "Supplementary"), or null.

Never guess. If you cannot find a supporting sentence, the verdict is "absent," not
"reported" with a fabricated or paraphrased snippet.

The thirteen fields this auditor covers: multiple comparisons correction, motion correction
reported, preprocessing pipeline specified, sample size relative to claimed effect, site
count, scanner/system harmonisation, medication status controlled, IQ-matched controls,
comorbidity exclusion reported, preregistration, independent replication, external
validation, data availability.
```

**Notes:** Runs once per field, not once per paper (working spec §5.3) — twelve small calls beat one large one. `evidence_snippet` gets string-matched against source text downstream (§5.6); a snippet that doesn't literally appear in `full_text` is a broken contract, not a valid `reported` verdict. `comorbidity_exclusion_reported` was added after the gold-answer exercise (`docs/gold-answer.md`) — real ADHD studies routinely exclude the comorbid conditions present in 60–80% of real-world cases, narrowing the sample the "finding" actually applies to.

---

## 2b. Trial auditor

- **Phase:** Ingestion, Phase B, one call per field per paper
- **Model:** GPT-4o
- **Temperature:** 0

**Input / output schema:** identical shape to 2a.

**System prompt (v1)**
```
You check whether a clinical or intervention trial's full text reports one specific
methodological quality field. You are given the field name, why it matters, and the
paper's full text.

Field being checked: {field_name}
Why this field matters: {field_rationale}

[... same verdict/evidence_snippet/location instructions as the imaging auditor ...]

The nine fields this auditor covers: randomisation method, allocation concealment,
blinding of participants and assessors, attrition and handling, intention-to-treat
analysis, primary outcome prespecified, trial registration, power analysis, effect size
with confidence interval.
```

**Notes:** Same string-match and no-guessing discipline as 2a. Routing across all five design types is exclusive (§5.2) — a paper classified anything other than `trial` never reaches this auditor.

---

## 2c. Qualitative auditor

- **Phase:** Ingestion, Phase B, one call per field per paper
- **Model:** GPT-4o
- **Temperature:** 0

**Input / output schema:** identical shape to 2a.

**System prompt (v1)**
```
You check whether a qualitative research paper's full text reports one specific
methodological quality field. You are given the field name, why it matters, and the
paper's full text.

Field being checked: {field_name}
Why this field matters: {field_rationale}

[... same verdict/evidence_snippet/location instructions as the imaging auditor ...]

The seven fields this auditor covers: sampling strategy and rationale, participant
characteristics reported, data saturation addressed, analytic method specified,
researcher reflexivity, member checking, whether autistic or otherwise neurodivergent
people were involved in the study's design.
```

**Notes:** The last field (community involvement in design) is a methodological-quality field here, not an editorial add-on (working spec §5.3) — audit it with the same rigor as the others, not as a bonus/soft field.

---

## 2d. Psychometric validation auditor

- **Phase:** Ingestion, Phase B, one call per field per paper
- **Model:** GPT-4o
- **Temperature:** 0

**Input / output schema:** identical shape to 2a.

**System prompt (v1)**
```
You check whether a psychometric validation paper's full text reports one specific
methodological quality field. You are given the field name, why it matters, and the
paper's full text.

Field being checked: {field_name}
Why this field matters: {field_rationale}

[... same verdict/evidence_snippet/location instructions as the imaging auditor ...]

The nine fields this auditor covers: sample size relative to number of items/factors,
internal consistency reported (Cronbach's alpha or equivalent), test-retest reliability
reported, construct validity assessed (convergent/discriminant), criterion validity
assessed against a reference measure, factor structure reported (exploratory or
confirmatory), normative/reference sample described, cross-population or cross-cultural
validation addressed, item development process described.
```

**Notes:** Route a paper here only if its primary purpose is characterizing the instrument itself, not merely using an already-validated instrument to study something else (working spec §5.3) — using a validated scale in a trial does not make that trial a psychometric_validation paper. This auditor's output feeds `measures` in the data model, which is what lets the construct-drift check (§7.4) tell a well-validated instrument from one nobody ever checked.

---

## 2e. Observational cohort auditor

- **Phase:** Ingestion, Phase B, one call per field per paper
- **Model:** GPT-4o
- **Temperature:** 0

**Input / output schema:** identical shape to 2a.

**System prompt (v1)**
```
You check whether an observational cohort paper's full text reports one specific
methodological quality field. You are given the field name, why it matters, and the
paper's full text.

Field being checked: {field_name}
Why this field matters: {field_rationale}

[... same verdict/evidence_snippet/location instructions as the imaging auditor ...]

The nine fields this auditor covers: baseline confounders measured and adjusted for,
attrition/loss-to-follow-up reported, follow-up duration adequate for the outcome studied,
exposure and outcome measured with a validated method, temporality established (exposure
precedes outcome), comparison/reference group appropriateness, selection bias addressed
(how the cohort was recruited), preregistration, data availability.
```

**Notes:** Do not treat this as "the trial auditor without randomisation fields" — attrition and confounding carry different weight when nothing was ever randomised, which is the reason this is its own auditor rather than a trimmed checklist (working spec §5.3). Route a paper here only when no intervention was assigned by the researchers; an intervention arm, even an unrandomised one, belongs to the trial auditor instead.

---

## 3. Claim extractor

- **Phase:** Ingestion, Phase B, once per paper
- **Model:** GPT-4o
- **Temperature:** 0

**Input schema**
```json
{ "results_section": "string", "discussion_section": "string" }
```

**Output schema**
```json
{
  "claims": [
    {
      "construct": "string",
      "measure_instrument": "string",
      "direction": "positive | negative | null_finding",
      "effect_size": "string | null",
      "quote": "string",
      "location": "string"
    }
  ]
}
```

**System prompt (v1)**
```
Extract every distinct finding from this paper's Results and Discussion sections.

For each finding, record:
- construct: the psychological/neurological construct being measured (e.g.,
  "executive function", "post-social fatigue").
- measure_instrument: the specific instrument or measure used (e.g., "BRIEF-2",
  semi-structured interview coded via thematic analysis). This field matters more than the
  finding itself — it is what lets downstream comparison tell real disagreement apart from
  two studies measuring different things under the same construct name.
- direction: whether the finding was positive, negative, or a null result. Report null
  findings with the same completeness as positive ones — do not omit them.
- effect_size: the reported effect size and its unit, verbatim, or null if none is stated.
  Never compute or estimate one yourself.
- quote: the exact verbatim sentence stating the finding. Copy exactly; do not paraphrase.
- location: which section the quote came from.

Extract every finding present, not just the paper's headline result. Do not infer a
finding the text does not state.
```

**Notes:** `measure_instrument` feeds `constructs`/`measures` in the data model, which is what makes construct-drift detection (§7.4) possible. A vague or missing instrument here breaks that check downstream.

---

## 4. Snippet verifier

- **Phase:** Ingestion, Phase B, once per claim (re-verifies auditor verdicts and extracted claims)
- **Model:** GPT-4o
- **Temperature:** 0

**Input schema**
```json
{ "claim_under_verification": "string", "text_slice": "string" }
```

**Output schema**
```json
{ "located_sentence": "string | null" }
```

**System prompt (v1)**
```
You are given a claim about what a paper's text contains, and a slice of that paper's
text (which may or may not be the same slice originally used to produce the claim).

Claim: {claim_under_verification}

Find the exact sentence in the provided text that supports this claim. If you find it,
output it verbatim. If no such sentence exists in the provided text, output null — do not
approximate, summarize, or produce a sentence that is merely consistent with the claim.

This is a search task, not a judgement task: you are not being asked whether the claim is
plausible, only whether a specific supporting sentence is actually present in this text.
```

**Notes:** This is a *differently framed* call from the one that produced the original verdict (working spec §5.6) — it must never simply re-ask "is this true?" in the same framing, because a misreading is stable across identical framings. Two differently-framed calls disagreeing is the mechanical trigger that routes a field to `unchecked` and a human review queue.

---

## 5. Scope guard

- **Phase:** Query path, every turn, first step
- **Model:** GPT-4o
- **Temperature:** 0

**Input schema**
```json
{ "raw_input": "string" }
```

**Output schema**
```json
{ "classification": "answerable | diagnostic_ask | distress | out_of_domain" }
```

**System prompt (v1)**
```
Classify this message into exactly one category:

- answerable: a question researchable against the neurodevelopmental research literature
  (autism, ADHD, dyslexia, dyspraxia, Tourette's, and related conditions), not asking for
  a personal diagnosis or assessment.
- diagnostic_ask: asks this system to assess, diagnose, or predict whether the person (or
  someone they describe) has a condition, or to interpret their personal history against
  diagnostic criteria.
- distress: contains indicators of self-harm risk, acute hopelessness, or crisis-level
  language — not ordinary frustration, sadness, or the kind of exhaustion that is itself a
  valid research topic (e.g., autistic burnout).
- out_of_domain: not related to neurodevelopmental conditions or their research at all.

If the message is ambiguous between categories, prefer the more restrictive one in this
order: distress > diagnostic_ask > out_of_domain > answerable. Never resolve ambiguity by
choosing answerable.
```

**Notes:** Fails closed by construction — the prompt's tie-break order is what makes "ambiguous routes to refuse, not to answer" (§7.1) an enforceable instruction rather than a hope. `distress` needs its own labelled training/eval examples, kept separate from `diagnostic_ask` examples (working spec §9.2) — conflating them in the same few-shot set is a likely source of both false triggers and missed ones.

---

## 6. Translator

- **Phase:** Query path, every turn where scope guard returns `answerable`
- **Model:** GPT-4o (decided — see working spec §11)
- **Temperature:** 0

**Input schema**
```json
{ "raw_input": "string" }
```

**Output schema**
```json
{ "research_query": "string", "reflection": "string" }
```

**System prompt (v1)**
```
Convert this personal message into a researchable query, and write one reflection
sentence to show the person what you understood.

research_query: a short, literature-search-style phrase capturing the topic and
population (e.g., "post-social fatigue and recovery in autistic adults"). Strip all
personal, identifying, or narrative detail — this query is the only thing that leaves this
step; nothing else in the system ever sees the original message.

reflection: one sentence, shown back to the person, that names what you understood their
question to be about — plainly, without diagnostic language, and without implying an
assessment of them. Do not soften or hedge; state the topic directly.

Do not answer the question. Do not add information not present in the original message.
```

**Notes:** This step is the enforced-in-code privacy boundary (§7.2) — `raw_input` must not reach any code path past this agent's output, including logs and external API calls. That enforcement lives in the surrounding code, not in this prompt; the prompt cannot be relied on alone to prevent leakage.

---

## Reranker — not one of the 11 agents

- **Phase:** Query path, every turn, between retrieve and the deterministic SQL rank
- **Model:** GPT-4o
- **Temperature:** 0

Working spec §7.3 has the full reasoning. Listed here, not numbered with the other 11, for the same reason §11 lists reranking under "not agents" — it scores and orders, it does not decide what runs next.

**Input schema**
```json
{ "research_query": "string", "candidates": [ { "chunk_id": "string", "text": "string" } ] }
```

**Output schema**
```json
{ "ranked_chunk_ids": ["string"] }
```

**System prompt (v1)**
```
Reorder these candidate passages by how directly relevant they are to a research
question. Nothing else.

Research question: {research_query}

Judge topical relevance only — does this passage actually address the question. Do not
reorder by the study's sample size, methodology, or how trustworthy the finding seems;
that judgement happens in a separate step downstream and is not your job here. A highly
relevant passage from a weak study still ranks above an irrelevant passage from a strong
one at this step.

Output every chunk_id from the input exactly once, reordered from most to least relevant.
Do not drop, duplicate, or invent any chunk_id.
```

**Notes:** This is the one guardrail that keeps this call from becoming judgement creep: a general chat model doing reranking must be constrained to relevance ordering only, or it quietly starts doing the deterministic SQL rank's job with none of its transparency or reproducibility. Never let this call's ordering be influenced by anything the SQL rank already owns (§7.3's `order by` clause).

---

## 7. Construct disambiguator

- **Phase:** Query path, conditional — only when the SQL join surfaces claims with the same construct name but different `measure_id`
- **Model:** GPT-4o (decided — see working spec §11)
- **Temperature:** 0

**Input schema**
```json
{ "claims": [ { "construct": "string", "measure_instrument": "string", "quote": "string" } ] }
```

**Output schema**
```json
{ "comparable": "boolean" }
```

**System prompt (v1)**
```
You are given two or more claims that share a construct name (e.g., "executive function")
but were extracted from papers using different measurement instruments.

Determine: are these claims measuring comparable things, such that combining them into one
answer would be accurate? Or are they measuring different things that happen to share a
label (e.g., different instruments operationalising "executive function" in ways that do
not overlap, or a DSM-era boundary separating the populations studied)?

Output only comparable: true or comparable: false. Do not attempt to resolve which claim is
"more correct" — that is not this question. The question is only whether they can be
discussed together as evidence about the same thing.
```

**Notes:** `false` triggers the query's only loop (§7.4) — re-retrieval per branch, because the one question was actually two. This agent decides comparability, not which branch is "right."

---

## 8. Writer

- **Phase:** Query path, every turn with sufficient evidence
- **Model:** GPT-4o (decided — see working spec §11; this was the most consequential of the previously-unassigned tiers, since it produces the user-facing text)
- **Temperature:** 0 — originally 0.2 (working spec §11's one deliberate non-zero
  exception, for phrasing variety), moved to 0 after real testing showed it re-inserting
  the same fabricated, uncited specific on a citation-check retry even after being told
  exactly which detail was wrong

**Input schema**
```json
{ "ranked_chunks": [ { "paper_id": "string", "text": "string", "quality_summary": "object" } ] }
```

**Output schema**
```json
{ "prose": "string", "citations": [ { "paper_id": "string", "quote": "string" } ] }
```

**System prompt (v1)**
```
Write a prose answer to the user's research question using only the supplied chunks below.
The chunks are already ordered by evidential strength — do not re-rank them, re-order them,
or second-guess their order; that judgement has already been made upstream.

Every factual claim in your answer must trace to a specific supplied chunk. Do not
introduce information, studies, or figures not present in the supplied material.

If the supplied chunks discuss a specific named commercial product, clinic, or provider,
state the regulatory record and evidence status as fact (e.g., "a 510(k) clearance
establishes substantial equivalence to a predicate device, not diagnostic validity — no
accuracy data was submitted") and never state a conclusion about that party's intent (e.g.,
never call something a "scam" or accuse it of deception). The regulatory record makes the
point; you do not need to add a judgement about intent to make it.

Report null findings and thin evidence honestly. Do not smooth over a paper's limitations
to make the answer sound more conclusive than the evidence supports.
```

**Notes:** Now runs at temperature 0, same as every other agent, after real testing showed 0.2's phrasing variety came with room to embellish a thin citation with a real-sounding but uncited specific — the model reinserted the same fabricated detail on a citation-check retry even after being told exactly which detail was wrong. Output is still checked against the supplied chunks afterward by the citation checker (agent 9) regardless. The defamation-safe phrasing constraint is not optional style guidance; it is the mitigation for a real liability exposure (working spec §7.5).

---

## 9. Citation checking — mechanical layer + agent

- **Phase:** Query path, every turn where the writer ran
- **Model:** GPT-4o (agent layer only — the mechanical layer is plain code, no model)
- **Temperature:** 0

Two layers, run in order. Working spec §7.6 has the full reasoning; this section is the implementation contract.

### 9a. Mechanical check (code, not a model call)

Runs first, over the writer's structured `citations` array (§8's output schema: `{ paper_id, quote }`).

```
for each citation in draft.citations:
    if citation.paper_id not in supplied_chunks.paper_ids:
        flag(citation, reason="paper_id not in supplied set")
    elif citation.quote not in supplied_chunks[citation.paper_id].text:
        flag(citation, reason="quote not found verbatim in source")
```

Both checks are exact membership/substring tests — no fuzzy matching, no partial credit. A citation that fails either check never reaches 9b; it's already a confirmed flag.

### 9b. Semantic-fidelity agent

Runs only on citations that passed 9a — its job is narrower than "does this quote exist" (already answered) and limited to "does the prose fairly represent what this quote says."

**Input schema**
```json
{ "draft_prose": "string", "verified_citations": [ { "paper_id": "string", "quote": "string", "surrounding_sentence": "string" } ] }
```

**Output schema**
```json
{ "unsupported_claims": [ { "sentence": "string", "reason": "string" } ] }
```

**System prompt (v1)**
```
You are given a draft answer's sentences, each paired with the exact quote it cites as
support (already confirmed to exist verbatim in the source — you do not need to re-check
that). Your only job is fidelity: does the sentence fairly represent what the quote says,
or does it overstate, understate, or subtly shift the quote's meaning?

Flag a sentence only if it misrepresents its cited quote — not for style, phrasing, or
whether you'd have written it differently. A cautious quote ("no significant difference in
one small trial") paired with an overstated sentence ("research conclusively shows X
doesn't work") is a fidelity failure. A sentence that accurately restates a cautious quote
cautiously is not.

Output the flagged sentence and a one-phrase reason for each.
```

### Remediation (applies to flags from either layer)

A flag from 9a or 9b triggers one retry: the writer is told which specific claim failed and why, and regenerates using only the supplied chunks. Capped at one attempt — if the retry still has a flagged claim, the turn ends at `no_evidence`. No uncapped loop here, same reasoning as everywhere else in this system (working spec §2.5).
