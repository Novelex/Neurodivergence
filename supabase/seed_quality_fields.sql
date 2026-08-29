-- NeuroEvidence — quality_fields seed data
-- Run once, after schema.sql. Pulled from the auditor field lists in docs/agents.md
-- and neuroevidence-working-spec.md §5.3. 45 unique fields across 5 auditors —
-- 2 fields (preregistration, data_availability) are shared between the imaging and
-- observational_cohort auditors, per §6's applies_to array design, so they're a single
-- row each rather than duplicated. Uses on conflict (id) do nothing throughout, so it's
-- safe to re-run after adding new fields below — already-seeded rows are left untouched.

-- ============================================================================
-- 2a. Imaging auditor (12 fields, 2 shared with 2e below)
-- ============================================================================

insert into quality_fields (id, auditor, name, rationale, applies_to, display_order) values
('multiple_comparisons_correction', 'imaging', 'Multiple comparisons correction',
 'Brain-wide association studies test thousands of voxels or connections at once; without correction, some findings are guaranteed to look significant by chance alone.',
 ARRAY['imaging_case_control']::design_type[], 1),

('motion_correction_reported', 'imaging', 'Motion correction reported',
 'Head motion during scanning is a well-documented confound in neuroimaging that can produce spurious group differences if not corrected for.',
 ARRAY['imaging_case_control']::design_type[], 2),

('preprocessing_pipeline_specified', 'imaging', 'Preprocessing pipeline specified',
 'Different preprocessing choices measurably change results in the same raw data; an unspecified pipeline means the finding cannot be independently checked or reproduced.',
 ARRAY['imaging_case_control']::design_type[], 3),

('sample_size_relative_to_effect', 'imaging', 'Sample size relative to claimed effect',
 'Reproducible brain-behaviour correlations need samples in the thousands; the field''s historical median has been in the tens, which is why this is checked explicitly rather than assumed.',
 ARRAY['imaging_case_control']::design_type[], 4),

('site_count', 'imaging', 'Site count',
 'Single-site findings collapse at a documented, high rate when tested across multiple sites; site count is a direct proxy for how much that risk applies to this specific finding.',
 ARRAY['imaging_case_control']::design_type[], 5),

('scanner_harmonisation', 'imaging', 'Scanner or system harmonisation',
 'Multi-site data pooled without harmonisation can produce differences driven by scanner hardware rather than by the population being studied.',
 ARRAY['imaging_case_control']::design_type[], 6),

('medication_status_controlled', 'imaging', 'Medication status controlled',
 'Psychoactive medication changes the neural signal being measured; an uncontrolled mix of medicated and unmedicated participants confounds the group comparison itself.',
 ARRAY['imaging_case_control']::design_type[], 7),

('iq_matched_controls', 'imaging', 'IQ-matched controls',
 'Unmatched cognitive ability between groups is a common alternative explanation for a group difference that gets attributed to the condition being studied instead.',
 ARRAY['imaging_case_control']::design_type[], 8),

('preregistration', 'imaging', 'Preregistration',
 'A preregistered analysis plan distinguishes a confirmed hypothesis from one selected after seeing the data, which inflates the apparent strength of a finding.',
 ARRAY['imaging_case_control', 'observational_cohort']::design_type[], 9),

('independent_replication', 'imaging', 'Independent replication',
 'A finding that only one research group has ever produced carries a different evidential weight than one multiple independent teams have reproduced.',
 ARRAY['imaging_case_control']::design_type[], 10),

('external_validation', 'imaging', 'External validation',
 'A model or biomarker validated only on the data it was built from typically performs worse on new, independent data — external validation is what tests whether it generalises at all.',
 ARRAY['imaging_case_control']::design_type[], 11),

('data_availability', 'imaging', 'Data availability',
 'Whether the underlying data can be independently re-examined is itself a marker of how checkable a finding is, separate from what the finding claims.',
 ARRAY['imaging_case_control', 'observational_cohort']::design_type[], 12)
on conflict (id) do nothing;

-- ============================================================================
-- 2b. Trial auditor (9 fields)
-- ============================================================================

insert into quality_fields (id, auditor, name, rationale, applies_to, display_order) values
('randomisation_method', 'trial', 'Randomisation method',
 'How allocation was actually randomised distinguishes genuine randomisation from a process vulnerable to selection bias in who ends up in which arm.',
 ARRAY['trial']::design_type[], 20),

('allocation_concealment', 'trial', 'Allocation concealment',
 'If the person enrolling participants can predict the next assignment, that knowledge can consciously or unconsciously bias who gets enrolled and when.',
 ARRAY['trial']::design_type[], 21),

('blinding', 'trial', 'Blinding of participants and assessors',
 'Knowing who received the real intervention measurably changes both participant-reported outcomes and assessor scoring, independent of any true treatment effect.',
 ARRAY['trial']::design_type[], 22),

('attrition_handling', 'trial', 'Attrition and handling',
 'Who drops out of a trial is rarely random, and how missing data is handled can shift results toward or away from an effect depending on the choice made.',
 ARRAY['trial']::design_type[], 23),

('intention_to_treat', 'trial', 'Intention-to-treat analysis',
 'Analysing only participants who completed treatment as assigned discards exactly the dropouts most likely to be systematically different, biasing the result.',
 ARRAY['trial']::design_type[], 24),

('primary_outcome_prespecified', 'trial', 'Primary outcome prespecified',
 'Choosing which outcome to report as primary after seeing which one came out significant is a well-documented route to a false positive.',
 ARRAY['trial']::design_type[], 25),

('trial_registration', 'trial', 'Trial registration',
 'A registry entry from before the trial ran lets you check whether the reported outcomes match what was originally planned, or were changed afterward.',
 ARRAY['trial']::design_type[], 26),

('power_analysis', 'trial', 'Power analysis',
 'An underpowered trial that finds a null result cannot distinguish "no effect" from "too few participants to detect the effect that exists."',
 ARRAY['trial']::design_type[], 27),

('effect_size_with_ci', 'trial', 'Effect size with confidence interval',
 'A p-value alone says nothing about how large or clinically meaningful an effect is; the confidence interval shows the actual range of plausible effect sizes.',
 ARRAY['trial']::design_type[], 28)
on conflict (id) do nothing;

-- ============================================================================
-- 2c. Qualitative auditor (7 fields)
-- ============================================================================

insert into quality_fields (id, auditor, name, rationale, applies_to, display_order) values
('sampling_strategy_rationale', 'qualitative', 'Sampling strategy and rationale',
 'Who was recruited and why shapes which perspectives the findings can actually speak to, and an unstated strategy hides that scope from the reader.',
 ARRAY['qualitative']::design_type[], 40),

('participant_characteristics_reported', 'qualitative', 'Participant characteristics reported',
 'Findings from a narrow, unreported demographic are easy to mistake for findings about the condition generally.',
 ARRAY['qualitative']::design_type[], 41),

('data_saturation_addressed', 'qualitative', 'Data saturation addressed',
 'Whether the researchers kept finding genuinely new themes or had already reached the point of diminishing returns affects how complete the resulting account is.',
 ARRAY['qualitative']::design_type[], 42),

('analytic_method_specified', 'qualitative', 'Analytic method specified',
 'Different qualitative analysis methods (thematic analysis, grounded theory, IPA) carry different assumptions about what counts as a valid finding; an unspecified method can''t be evaluated against its own standards.',
 ARRAY['qualitative']::design_type[], 43),

('researcher_reflexivity', 'qualitative', 'Researcher reflexivity',
 'Qualitative interpretation is shaped by the researcher''s own position; stating that position is how a reader can judge its likely influence on the findings.',
 ARRAY['qualitative']::design_type[], 44),

('member_checking', 'qualitative', 'Member checking',
 'Checking interpretations back with participants is a direct way to catch a researcher misreading what was actually meant.',
 ARRAY['qualitative']::design_type[], 45),

('community_involvement_in_design', 'qualitative', 'Neurodivergent community involvement in design',
 'A field where much of the formal literature was produced without asking the population it describes treats community involvement as a methodological quality, not a political gesture (working spec §5.3).',
 ARRAY['qualitative']::design_type[], 46)
on conflict (id) do nothing;

-- ============================================================================
-- 2d. Psychometric validation auditor (9 fields)
-- ============================================================================

insert into quality_fields (id, auditor, name, rationale, applies_to, display_order) values
('sample_size_relative_to_items', 'psychometric_validation', 'Sample size relative to number of items/factors',
 'Factor analysis and reliability estimates become unstable below commonly-cited sample-to-item ratios, regardless of how clean the resulting factor structure looks.',
 ARRAY['psychometric_validation']::design_type[], 50),

('internal_consistency_reported', 'psychometric_validation', 'Internal consistency reported',
 'A scale whose items don''t reliably measure the same underlying thing produces noisy, hard-to-interpret scores no matter how it''s used downstream.',
 ARRAY['psychometric_validation']::design_type[], 51),

('test_retest_reliability', 'psychometric_validation', 'Test-retest reliability reported',
 'A measure that gives a substantially different score on a second administration, with no real change in the person, cannot be trusted for tracking change over time.',
 ARRAY['psychometric_validation']::design_type[], 52),

('construct_validity_assessed', 'psychometric_validation', 'Construct validity assessed',
 'Without evidence the instrument correlates with related constructs and diverges from unrelated ones, there''s no basis for believing it measures what it claims to.',
 ARRAY['psychometric_validation']::design_type[], 53),

('criterion_validity_assessed', 'psychometric_validation', 'Criterion validity assessed against a reference measure',
 'Comparing a new instrument against an established reference measure is the direct test of whether it actually tracks the thing it''s meant to replace or supplement.',
 ARRAY['psychometric_validation']::design_type[], 54),

('factor_structure_reported', 'psychometric_validation', 'Factor structure reported',
 'The number and structure of underlying factors determines what a total or subscale score is actually supposed to mean.',
 ARRAY['psychometric_validation']::design_type[], 55),

('normative_sample_described', 'psychometric_validation', 'Normative/reference sample described',
 'A score is only interpretable relative to the population it was normed on; an undescribed normative sample makes any individual score uninterpretable outside that study.',
 ARRAY['psychometric_validation']::design_type[], 56),

('cross_population_validation', 'psychometric_validation', 'Cross-population or cross-cultural validation addressed',
 'An instrument validated on one population does not automatically measure the same construct the same way in a different population, age group, or culture.',
 ARRAY['psychometric_validation']::design_type[], 57),

('item_development_process_described', 'psychometric_validation', 'Item development process described',
 'How items were generated and selected — including whether the population being measured was involved — shapes what the instrument can and cannot capture.',
 ARRAY['psychometric_validation']::design_type[], 58)
on conflict (id) do nothing;

-- ============================================================================
-- 2e. Observational cohort auditor (9 fields, 2 shared with 2a above)
-- ============================================================================

insert into quality_fields (id, auditor, name, rationale, applies_to, display_order) values
('baseline_confounders_adjusted', 'observational_cohort', 'Baseline confounders measured and adjusted for',
 'With no randomisation, group differences that exist before any exposure can masquerade as effects of the exposure itself unless explicitly adjusted for.',
 ARRAY['observational_cohort']::design_type[], 60),

('loss_to_follow_up_reported', 'observational_cohort', 'Attrition/loss-to-follow-up reported',
 'Who is lost to follow-up in a cohort study is rarely random, and unreported attrition hides how much the remaining sample has drifted from the original cohort.',
 ARRAY['observational_cohort']::design_type[], 61),

('follow_up_duration_adequate', 'observational_cohort', 'Follow-up duration adequate for the outcome studied',
 'An outcome that develops over years cannot be meaningfully assessed by a study that only follows participants for months.',
 ARRAY['observational_cohort']::design_type[], 62),

('exposure_outcome_validated_method', 'observational_cohort', 'Exposure and outcome measured with a validated method',
 'Unvalidated self-report measures of exposure or outcome introduce measurement error that can create or mask real associations.',
 ARRAY['observational_cohort']::design_type[], 63),

('temporality_established', 'observational_cohort', 'Temporality established (exposure precedes outcome)',
 'An association is not evidence of a causal direction unless the exposure is shown to have actually preceded the outcome, not just co-occurred with it.',
 ARRAY['observational_cohort']::design_type[], 64),

('comparison_group_appropriateness', 'observational_cohort', 'Comparison/reference group appropriateness',
 'An exposed group compared against a systematically different reference group can produce an apparent association driven by that difference rather than the exposure.',
 ARRAY['observational_cohort']::design_type[], 65),

('selection_bias_addressed', 'observational_cohort', 'Selection bias addressed',
 'How a cohort was recruited determines whether it represents the population the finding is being generalised to, or a systematically different subset of it.',
 ARRAY['observational_cohort']::design_type[], 66)
on conflict (id) do nothing;

-- preregistration and data_availability already inserted above (shared with imaging, §6)

-- ============================================================================
-- Added after the gold-answer exercise (docs/gold-answer.md, §13.1)
-- ============================================================================

insert into quality_fields (id, auditor, name, rationale, applies_to, display_order) values
('comorbidity_exclusion_reported', 'imaging', 'Comorbidity exclusion reported',
 'ADHD studies routinely exclude the comorbid conditions present in 60-80% of real-world cases; a "positive" finding measured on that narrower, cleaner population may not generalise to the patients the finding gets applied to.',
 ARRAY['imaging_case_control']::design_type[], 13)
on conflict (id) do nothing;
