#!/usr/bin/env python3
"""
frontend_drift_detector.py — Scans frontend source files for architectural violations.

Mirrors drift_detector.py (backend). Run before every commit.

Usage:
    python frontend_drift_detector.py           # full scan, exit 1 on errors
    python frontend_drift_detector.py --warn    # full scan, exit 0 always
"""

import re
import sys
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# Force UTF-8 + ANSI on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.platform == "win32":
    os.system("")

# ── Config ────────────────────────────────────────────────────────────────────

FRONTEND_DIR = Path(__file__).parent / "frontend"
SCAN_DIRS    = ["app", "components"]

# Files intentionally exempt from hex-colour check (hardcoded dark brand panels)
HEX_EXEMPT_COMMENT = "intentionally hardcoded"   # look for this comment in the same file

# Pages that are placeholder (< 20 lines) — skip some checks
PLACEHOLDER_MARKER = "return null;"

# Required pages (route → min lines to be considered "built")
REQUIRED_PAGES = {
    "app/login/page.tsx":                   30,
    "app/signup/page.tsx":                  30,
    "app/page.tsx":                         30,
    "app/procurement/upload/page.tsx":      30,
    "app/[runId]/confirm/page.tsx":         30,
    "app/[runId]/progress/page.tsx":        30,
    "app/[runId]/results/page.tsx":         30,
    "app/[runId]/approve/page.tsx":         30,
    "app/[runId]/compare/page.tsx":         30,
    "app/[runId]/override/page.tsx":        30,
    "app/admin/settings/page.tsx":          30,
}

# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class Violation:
    category: str
    severity: str          # ERROR | WARNING | INFO
    file:     str
    line:     int
    message:  str

@dataclass
class ScanResult:
    violations: list[Violation] = field(default_factory=list)

    def add(self, category: str, severity: str, file: str, line: int, msg: str):
        self.violations.append(Violation(category, severity, file, line, msg))

    @property
    def errors(self):   return [v for v in self.violations if v.severity == "ERROR"]
    @property
    def warnings(self): return [v for v in self.violations if v.severity == "WARNING"]

# ── Helpers ───────────────────────────────────────────────────────────────────

def collect_tsx_files() -> list[Path]:
    files = []
    for d in SCAN_DIRS:
        target = FRONTEND_DIR / d
        if target.exists():
            files.extend(target.rglob("*.tsx"))
            files.extend(target.rglob("*.ts"))
    return files

def is_placeholder(content: str) -> bool:
    lines = [l.strip() for l in content.splitlines() if l.strip()]
    return len(lines) < 10 or PLACEHOLDER_MARKER in content

def file_has_hex_exception(content: str) -> bool:
    return HEX_EXEMPT_COMMENT in content

# ── Check functions ───────────────────────────────────────────────────────────

RAW_HEX_RE = re.compile(r'(?<!["\w])#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-fA-F"\w])')
TAILWIND_PALETTE_RE = re.compile(
    r'\b(blue|indigo|purple|pink|red|orange|yellow|green|teal|cyan|slate|gray|zinc|neutral|stone|emerald|violet|fuchsia|rose|sky|lime|amber)-\d{2,3}\b'
)
RAW_FONT_RE  = re.compile(r"""['"](?:Inter|Georgia|Times|system-ui|IBM Plex|Roboto|Arial|Helvetica)[^'"]*['"]""")
TRANSITION_ALL_RE = re.compile(r'transition[:\s]+["\']?all\b|transition-all')
DANGEROUS_HTML_RE = re.compile(r'dangerouslySetInnerHTML')
CONSOLE_SECRET_RE = re.compile(r'console\.log\([^)]*(?:token|password|secret|key|auth)[^)]*\)', re.IGNORECASE)
HARDCODED_URL_RE  = re.compile(r'''["']https?://(?!fonts\.googleapis)[\w.-]+/api/v\d''')
USE_OLD_THEME_RE  = re.compile(r'\buseTheme\(\)')
NO_SUPPRESS_HYDRATION = re.compile(r'type=["\']password["\'](?!.*suppressHydrationWarning)', re.DOTALL)


def check_theme_violations(result: ScanResult, path: Path, content: str, rel: str):
    if is_placeholder(content):
        return

    # Raw hex — skip if file explicitly marks intentional hardcoding
    if not file_has_hex_exception(content):
        for i, line in enumerate(content.splitlines(), 1):
            if RAW_HEX_RE.search(line) and "// #" not in line:
                result.add("THEME", "ERROR", rel, i,
                    f"Raw hex colour detected — use var(--color-*) instead: {line.strip()[:80]}")

    for i, line in enumerate(content.splitlines(), 1):
        if TAILWIND_PALETTE_RE.search(line):
            result.add("THEME", "ERROR", rel, i,
                f"Tailwind palette name detected — use var(--color-*): {line.strip()[:80]}")
        if RAW_FONT_RE.search(line):
            result.add("THEME", "WARNING", rel, i,
                f"Raw font string detected — use FONT/DISPLAY/MONO from @/lib/theme: {line.strip()[:80]}")
        if TRANSITION_ALL_RE.search(line):
            result.add("THEME", "ERROR", rel, i,
                f"transition:all detected — animate only transform/opacity: {line.strip()[:80]}")


def check_responsive_violations(result: ScanResult, path: Path, content: str, rel: str):
    if is_placeholder(content):
        return
    if "page.tsx" not in str(path):
        return

    if "useBreakpoint" not in content:
        result.add("RESPONSIVE", "WARNING", rel, 0,
            "Page does not import useBreakpoint — add from @/lib/hooks")


def check_security_violations(result: ScanResult, path: Path, content: str, rel: str):
    if is_placeholder(content):
        return

    for i, line in enumerate(content.splitlines(), 1):
        if DANGEROUS_HTML_RE.search(line):
            result.add("SECURITY", "ERROR", rel, i,
                f"dangerouslySetInnerHTML detected — XSS risk: {line.strip()[:80]}")
        if CONSOLE_SECRET_RE.search(line):
            result.add("SECURITY", "ERROR", rel, i,
                f"console.log with sensitive keyword: {line.strip()[:80]}")
        if HARDCODED_URL_RE.search(line):
            result.add("SECURITY", "ERROR", rel, i,
                f"Hardcoded API URL detected — use /api/v1/ proxy: {line.strip()[:80]}")
        if USE_OLD_THEME_RE.search(line):
            result.add("ARCHITECTURE", "ERROR", rel, i,
                f"Deprecated useTheme() — use useThemeContext() from @/components/ThemeProvider")


def check_accessibility_violations(result: ScanResult, path: Path, content: str, rel: str):
    if is_placeholder(content):
        return
    if "page.tsx" not in str(path):
        return

    # Check for inputs without labels — simple heuristic
    input_count  = len(re.findall(r'<input\b', content))
    label_count  = len(re.findall(r'<label\b|htmlFor=', content))
    if input_count > 0 and label_count == 0:
        result.add("A11Y", "ERROR", rel, 0,
            f"Found {input_count} <input> element(s) but no <label>/htmlFor — all inputs must have labels")

    # Check role="alert" on error divs
    if 'setError(' in content and 'role="alert"' not in content and "role={'alert'}" not in content:
        result.add("A11Y", "WARNING", rel, 0,
            "Component uses setError() but no role=\"alert\" found — screen readers won't announce errors")

    # Check outline:none without focus replacement
    for i, line in enumerate(content.splitlines(), 1):
        if 'outline: "none"' in line or "outline: 'none'" in line:
            context = "\n".join(content.splitlines()[max(0,i-5):i+5])
            if "focusedField" not in context and ":focus-visible" not in context:
                result.add("A11Y", "WARNING", rel, i,
                    f"outline:none without visible focus replacement on line {i}")


def check_route_completeness(result: ScanResult):
    for rel_path, min_lines in REQUIRED_PAGES.items():
        full_path = FRONTEND_DIR / rel_path
        if not full_path.exists():
            result.add("ROUTES", "ERROR", rel_path, 0,
                f"Required page missing: {rel_path}")
            continue
        content = full_path.read_text(encoding="utf-8", errors="ignore")
        line_count = len([l for l in content.splitlines() if l.strip()])
        if line_count < min_lines:
            result.add("ROUTES", "WARNING", rel_path, 0,
                f"Page appears to be a placeholder ({line_count} non-empty lines, expected ≥ {min_lines}): {rel_path}")


def check_architecture_violations(result: ScanResult, path: Path, content: str, rel: str):
    if is_placeholder(content):
        return

    # Protected pages must have auth guard (redirect to /login)
    protected_pages = ["page.tsx", "procurement", "runId", "admin"]
    is_protected = any(p in str(path) for p in protected_pages)
    is_auth_page = any(p in str(path) for p in ["login", "signup"])

    if is_protected and not is_auth_page and "page.tsx" in str(path):
        if "access_token" not in content and "/login" not in content:
            result.add("AUTH", "WARNING", rel, 0,
                "Protected page may be missing auth guard — should redirect to /login if no token")


# ── Main scan ─────────────────────────────────────────────────────────────────

def run_scan() -> ScanResult:
    result = ScanResult()
    files  = collect_tsx_files()

    for path in files:
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            result.add("IO", "WARNING", str(path), 0, f"Could not read file: {e}")
            continue

        rel = str(path.relative_to(FRONTEND_DIR)).replace("\\", "/")
        check_theme_violations(result, path, content, rel)
        check_responsive_violations(result, path, content, rel)
        check_security_violations(result, path, content, rel)
        check_accessibility_violations(result, path, content, rel)
        check_architecture_violations(result, path, content, rel)

    check_route_completeness(result)
    return result


def print_report(result: ScanResult):
    COLOURS = {"ERROR": "\033[91m", "WARNING": "\033[93m", "INFO": "\033[94m", "RESET": "\033[0m"}

    by_cat: dict[str, list[Violation]] = {}
    for v in result.violations:
        by_cat.setdefault(v.category, []).append(v)

    if not result.violations:
        print("\033[92m✓ Frontend drift detector: no violations found\033[0m")
        return

    print("\n── Frontend Drift Detector ──────────────────────────────────────")
    for cat, viols in sorted(by_cat.items()):
        print(f"\n  [{cat}]")
        for v in viols:
            colour  = COLOURS.get(v.severity, "")
            loc     = f"{v.file}:{v.line}" if v.line else v.file
            print(f"  {colour}{v.severity:8}{COLOURS['RESET']} {loc}")
            print(f"           {v.message}")

    errors   = len(result.errors)
    warnings = len(result.warnings)
    print(f"\n── Summary: {errors} error(s), {warnings} warning(s) ──────────────────────\n")


if __name__ == "__main__":
    warn_only = "--warn" in sys.argv
    result    = run_scan()
    print_report(result)

    if result.errors and not warn_only:
        sys.exit(1)
    sys.exit(0)
