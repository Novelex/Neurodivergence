# Gold answer — reference case

Working spec §13.1: "Before writing pipeline code, answer the reference question by hand... The failure mode that kills projects like this is building a pipeline before knowing what a good output looks like, then optimising it for the wrong thing."

This file is that exercise, done. It is a permanent test fixture, not a draft — once the real pipeline exists, its output for this question gets compared against this file, not the other way around.

---

## The reference question

From working spec §1.1:

> A 34-year-old, self-identified as possibly ADHD, waiting on an assessment with a multi-year queue. She has found a private clinic offering a brain scan that claims to diagnose ADHD objectively, for £1,200. She wants to know whether it is real before she pays.

---

## The gold answer

No brain-scan or EEG-based test has been shown to reliably diagnose ADHD on its own, in adults or children, and the one such device the FDA has ever cleared makes that limitation explicit in its own label.

The device most private "objective ADHD scan" clinics trace their credibility to is the **NEBA System** (FDA De Novo clearance K112711, 2013) — it measures a single EEG ratio (theta/beta ratio, or TBR) and is indicated only "as confirmatory support for a completed clinical evaluation," explicitly **not** as a stand-alone diagnostic tool, and only for ages 6–17. An adult being offered a "brain scan diagnosis" is already outside what any cleared device claims to do.

The underlying biomarker doesn't hold up on its own merits either. TBR looked like a real, robust marker in the original 2013 meta-analysis of then-available (mostly single-site, smaller) studies. Since then, larger multi-cohort work has directly contradicted it: a 2024 meta-analytic study combining three independent cohorts (N=417) concluded TBR "has no diagnostic value for ADHD" at the group level. A 2026 multiverse analysis (N=1,499, with an independent N=381 validation sample) found that the positive TBR findings in the older literature were highly sensitive to which of hundreds of plausible analysis choices a given study happened to make — suggesting much of the original signal was an artifact of researcher degrees of freedom, not a stable biological marker. And specifically for adults — the population the reference case is about — a separate study found TBR does *not* work as a neuromarker at all, even though broader EEG spectral power measures showed some signal.

A known confound compounds this: children (and likely adults) with ADHD tend to move more during EEG recording, and TBR studies have often excluded the comorbid conditions present in 60–80% of real-world ADHD cases — meaning even the original positive studies were measuring a narrower, cleaner population than any real clinic's patients.

So: the £1,200 test isn't measuring a validated marker, isn't cleared for the population being sold to, and even the device that *is* cleared explicitly refuses to be used the way this clinic is using it.

---

## Sources

| # | Source | What it contributes |
|---|---|---|
| 1 | [FDA De Novo Summary K112711 — NEBA System](https://www.accessdata.fda.gov/cdrh_docs/reviews/k112711.pdf) | The regulatory record: what's actually cleared, for whom, and with what stated limitation |
| 2 | [A decade of EEG Theta/Beta Ratio Research in ADHD: a meta-analysis (2013)](https://pubmed.ncbi.nlm.nih.gov/23086616/) | The original claim — TBR as an apparently robust marker, based on then-available studies |
| 3 | [Challenging the Diagnostic Value of Theta/Beta Ratio (2024)](https://pubmed.ncbi.nlm.nih.gov/38858282/) | Multi-cohort (N=417, 3 independent cohorts) refutation: "no diagnostic value for ADHD" |
| 4 | [Theta-Beta Ratio in ADHD: A Multiverse Analysis (2026, preprint)](https://www.medrxiv.org/content/10.64898/2026.01.08.26343676v2.full) | Shows the original effect is highly sensitive to analytic choices (N=1,499 + N=381 validation) — **not yet peer-reviewed**, flagged below |
| 5 | [EEG spectral power, but not theta/beta ratio, is a neuromarker for adult ADHD](https://www.biorxiv.org/content/10.1101/700005.full.pdf) | Adult-specific: directly addresses the reference case's population, not just pediatric data |

**5 sources, not the ~15 the working spec estimated as a ceiling** — the actual number needed for a complete, honest answer to this specific question.

---

## What this exercise revealed (§13.1's actual payoff)

**The ranking rule, confirmed and clarified.** Cohort count and sample size beat recency as the sorting principle, exactly as working spec §3.1 argues — sources 3 and 4 win not because they're newer than source 2, but because they're multi-cohort (source 3) and specifically designed to test robustness across analytic choices (source 4). The wrinkle worth flagging: in this particular case, newer *also happens to be* more reliable, which could look like it contradicts §3.1's "recency is anti-correlated with reliability" framing at a glance. It doesn't — the rule was never "old beats new," it was "multi-cohort/large-N beats single-site," and that's what actually did the sorting here. Keep this case as the concrete illustration of *why* the rule is phrased by cohort count, not by date.

**A quality field the current auditor list is missing.** Motion artifacts during EEG (a real, cited confound in this literature) and comorbidity-exclusion in study samples (present in 60–80% of real-world ADHD cases, routinely excluded from the studies) both mattered more to this answer than several fields already on the imaging auditor's list (§5.3). "Comorbidity exclusion reported" isn't currently one of the 12 imaging-auditor fields in `docs/agents.md` — worth adding.

**Publication status matters, and the schema needs to carry it.** Source 4 is a medRxiv preprint, not yet peer-reviewed. Source 3 is published and peer-reviewed. Treating them identically in the gold answer above is a simplification for readability — a real ingestion run must distinguish these via `papers` metadata (peer-reviewed vs. preprint), not just quality-check verdicts, since §5.4's absence semantics are about what a paper reports, not about whether the paper itself has cleared peer review at all. This is a gap the current schema doesn't explicitly track and should.

**Confirms the two-axis point from §9.1, negatively.** Unlike the burnout/masking example, there's no meaningful "community corroboration" axis here — this is a purely formal-evidence question (is a specific medical claim true), not one where lived experience and formal literature diverge. Useful confirmation that the two-axis design is scoped correctly: it should only fire for constructs like burnout/masking, not for every question.
