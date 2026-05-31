"""Synthetic document generation for the E3 benchmark.

`pdf_builder` is a thin, reusable reportlab wrapper; `build_scenarios` defines
the scenario content (single source for both the PDF text and the golden file)
and emits the committed fixtures. Run once via:

    python -m benchmark.generation.build_scenarios
"""
