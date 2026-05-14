"""
Fails CI if forbidden hardcoded values appear in app/ code.

Every behavioural value must live in:
  .env / platform.yaml / product.yaml / org_settings.

Add a `# audit:allow` comment to a line to exempt it (rare; use only
for legitimate constants like dict keys or schema field names).

Usage:
  python scripts/audit_hardcoded_values.py             # default rules
  python scripts/audit_hardcoded_values.py --strict    # also flag soft patterns
"""
import re
import sys
from pathlib import Path

# (regex_pattern, description, severity)
RULES = [
    # Confidence thresholds — must come from settings
    (r'\b0\.75\b',  'confidence_retry_threshold value — use settings',         'hard'),
    (r'\b0\.85\b',  'confidence_retry_threshold value — use settings',         'hard'),
    (r'\b0\.60\b',  'confidence_retry_threshold value — use settings',         'hard'),
    (r'\b0\.15\b',  'score_variance_threshold value — use settings',           'hard'),

    # Retrieval magic numbers
    (r'top_k\s*=\s*5\b',     'top_k literal — use settings or org_settings',   'hard'),
    (r'top_k\s*=\s*10\b',    'top_k literal — use settings or org_settings',   'hard'),
    (r'top_n\s*=\s*3\b',     'rerank top_n literal — use settings',            'hard'),
    (r'top_n\s*=\s*5\b',     'rerank top_n literal — use settings',            'hard'),
    (r'n_candidates\s*=\s*20\b','candidate count — use platform.retrieval',    'hard'),

    # Model names
    (r'"gpt-4o"',            'model name — use settings.platform.llm',         'hard'),
    (r'"gpt-4o-mini"',       'model name — use settings.platform.llm',         'hard'),
    (r'"text-embedding-3',   'embedding model — use settings.platform.retrieval','hard'),
    (r'"rerank-english',     'rerank model — use settings.platform.retrieval', 'hard'),
    (r'BAAI/bge-reranker',   'rerank model — use settings.platform.retrieval', 'hard'),
    (r'colbertv2\.0',        'rerank model — use settings.platform.retrieval', 'hard'),

    # Chunking
    (r'chunk_size\s*=\s*500',   'chunk_size literal — use platform.ingestion', 'hard'),
    (r'chunk_overlap\s*=\s*50', 'chunk_overlap literal — use platform.ingestion','hard'),

    # Timing
    (r'timeout\s*=\s*120',   'timeout literal — use platform.llm',             'hard'),
    (r'max_retries\s*=\s*5', 'retries literal — use platform.infrastructure',  'hard'),

    # Audit retention
    (r'retain.*7\s*$',       'retention literal — use product.audit',          'soft'),
]

# Paths exempt from auditing
IGNORE = [
    'app/config/',          # the config layer itself stores these
    'app\\config\\',        # Windows path separator
    'tests/',
    'test_',
    '__pycache__',
]


def audit(strict: bool = False) -> int:
    violations = []
    for path in sorted(Path('app').rglob('*.py')):
        spath = str(path)
        if any(seg in spath for seg in IGNORE):
            continue
        for lineno, line in enumerate(path.read_text(encoding='utf-8', errors='ignore').splitlines(), 1):
            if '# audit:allow' in line:
                continue
            if line.strip().startswith('#'):
                continue
            for pattern, why, severity in RULES:
                if severity == 'soft' and not strict:
                    continue
                if re.search(pattern, line):
                    violations.append((path, lineno, line.strip(), pattern, why))

    if violations:
        print(f"audit_hardcoded_values: {len(violations)} violation(s)\n")
        for path, lineno, line, pattern, why in violations:
            print(f"  {path}:{lineno}")
            print(f"    pattern: {pattern}")
            print(f"    found:   {line[:120]}")
            print(f"    fix:     {why}")
            print()
        return 1
    print("audit_hardcoded_values: 0 violations")
    return 0


if __name__ == "__main__":
    strict = "--strict" in sys.argv
    sys.exit(audit(strict=strict))
