"""
Pure metric functions for the E3 benchmark.

Every function here takes golden expectations + an `ActualVendor`/`ActualScenario`
(plain validated data) and returns numbers. NO database, NO LLM, NO file I/O,
NO pipeline imports — so the whole package is unit-tested in CI for free
(tests/test_benchmark_metrics.py). The impure work (running the pipeline) lives
only in benchmark/runner/.
"""
