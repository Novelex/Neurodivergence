"""Compares the real pipeline's output against docs/gold-answer.md. Working spec §13.1.

docs/gold-answer.md is the test fixture, not a draft — once the real pipeline exists,
its output for the reference question gets compared against that file, not the other
way around. This test is the mechanical form of that comparison.

TODO: implement once neurodiversity/query/pipeline.py exists. At minimum, assert the
same regulatory record (FDA K112711 / NEBA System) and the same core finding (theta/beta
ratio has no diagnostic value per the 2024 multi-cohort meta-analysis) surface in the
pipeline's answer to the reference question.
"""
