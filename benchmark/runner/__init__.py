"""
Benchmark runner — the ONLY impure part of the suite.

`pipeline_adapter.run_scenario` runs the real pipeline for one scenario (DB,
Qdrant, LLM) and maps the result to an `ActualScenario` via the PURE
`state_to_actual`. `run_benchmark` is the CLI that loops scenarios, compares
against the golden files, and writes the committed results artifact.
"""
