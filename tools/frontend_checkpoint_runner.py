#!/usr/bin/env python3
"""
frontend_checkpoint_runner.py — Structured UI quality checkpoints.

Mirrors checkpoint_runner.py (backend). Run after each page is built.

Usage:
    python frontend_checkpoint_runner.py status     # show all checkpoint states
    python frontend_checkpoint_runner.py run        # run all checks
    python frontend_checkpoint_runner.py run BUILD  # run single category
"""

import re
import sys
import json
import subprocess
from pathlib import Path
from dataclasses import dataclass
import os

# Force UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Enable ANSI colors on Windows
if sys.platform == "win32":
    os.system("")  # enables VT100 in cmd/PowerShell

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

# ── Checkpoint result ─────────────────────────────────────────────────────────

@dataclass
class CP:
    id:      str
    label:   str
    passed:  bool
    detail:  str = ""

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
SKIP = "\033[93m–\033[0m"

# ── Helpers ───────────────────────────────────────────────────────────────────

def read_file(rel: str) -> str:
    p = FRONTEND_DIR / rel
    return p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""

def file_exists(rel: str) -> bool:
    return (FRONTEND_DIR / rel).exists()

def file_lines(rel: str) -> int:
    content = read_file(rel)
    return len([l for l in content.splitlines() if l.strip()])

def run_cmd(cmd: list[str], cwd: Path) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120)
        return r.returncode, (r.stdout + r.stderr)[:2000]
    except Exception as e:
        return 1, str(e)

# ── CP-BUILD ─────────────────────────────────────────────────────────────────

def cp_build() -> list[CP]:
    results = []

    # B1: next.config.ts has API rewrite
    config = read_file("next.config.ts")
    has_rewrite = "localhost:8000" in config or "rewrite" in config.lower()
    results.append(CP("B1", "next.config.ts has API proxy rewrite", has_rewrite,
        "" if has_rewrite else "Missing /api/* → http://localhost:8000/api/* rewrite"))

    # B2: package.json has correct Next.js version
    pkg = read_file("package.json")
    try:
        data = json.loads(pkg)
        next_ver = data.get("dependencies", {}).get("next", "")
        ok = "16" in next_ver or "15" in next_ver
        results.append(CP("B2", f"Next.js version is 15/16 (found: {next_ver})", ok,
            "" if ok else f"Unexpected Next.js version: {next_ver}"))
    except Exception:
        results.append(CP("B2", "package.json parseable", False, "Could not parse package.json"))

    # B3: TypeScript config exists
    has_tsconfig = file_exists("tsconfig.json")
    results.append(CP("B3", "tsconfig.json present", has_tsconfig))

    # B4: No node_modules missing (package-lock.json present)
    has_lock = file_exists("package-lock.json")
    results.append(CP("B4", "package-lock.json present (deps installed)", has_lock,
        "" if has_lock else "Run: cd frontend && npm install"))

    return results


# ── CP-ROUTES ─────────────────────────────────────────────────────────────────

REQUIRED_PAGES = [
    ("app/login/page.tsx",                  "Login page",           40),
    ("app/signup/page.tsx",                 "Signup page",          40),
    ("app/page.tsx",                        "Home/Dashboard page",  40),
    ("app/procurement/upload/page.tsx",     "Upload page",          30),
    ("app/[runId]/confirm/page.tsx",        "Confirm page",         30),
    ("app/[runId]/progress/page.tsx",       "Progress (SSE) page",  30),
    ("app/[runId]/results/page.tsx",        "Results page",         30),
    ("app/[runId]/approve/page.tsx",        "Approve page",         30),
    ("app/[runId]/compare/page.tsx",        "Compare page",         30),
    ("app/[runId]/override/page.tsx",       "Override page",        30),
    ("app/admin/settings/page.tsx",         "Admin Settings page",  30),
]

def cp_routes() -> list[CP]:
    results = []
    for rel, label, min_lines in REQUIRED_PAGES:
        if not file_exists(rel):
            results.append(CP(f"R-{rel[:8]}", f"{label} exists", False, f"Missing: frontend/{rel}"))
            continue
        lines = file_lines(rel)
        built = lines >= min_lines
        results.append(CP(f"R-{rel[:8]}", f"{label} built (≥{min_lines} lines, actual {lines})", built,
            f"Placeholder only ({lines} lines) — needs real implementation" if not built else ""))
    return results


# ── CP-THEME ──────────────────────────────────────────────────────────────────

def cp_theme() -> list[CP]:
    results = []

    # T1: lib/theme.ts exists and exports FONT/DISPLAY/MONO
    theme = read_file("lib/theme.ts")
    has_exports = all(x in theme for x in ["export const FONT", "export const DISPLAY", "export const MONO", "applyThemeVars"])
    results.append(CP("T1", "lib/theme.ts exports FONT, DISPLAY, MONO, applyThemeVars", has_exports))

    # T2: ThemeProvider wraps layout
    layout = read_file("app/layout.tsx")
    has_provider = "ThemeProvider" in layout
    results.append(CP("T2", "ThemeProvider wraps root layout", has_provider))

    # T3: globals.css has CSS vars
    css = read_file("app/globals.css")
    has_vars = "--color-accent" in css and "--font-sans" in css
    results.append(CP("T3", "globals.css defines required CSS vars", has_vars))

    # T4: drift detector passes (no raw hex errors)
    try:
        from frontend_drift_detector import run_scan
        scan = run_scan()
        theme_errors = [v for v in scan.errors if v.category == "THEME"]
        ok = len(theme_errors) == 0
        results.append(CP("T4", f"No raw hex/Tailwind palette violations ({len(theme_errors)} errors)", ok,
            "\n".join(f"  {v.file}:{v.line} — {v.message}" for v in theme_errors[:5]) if not ok else ""))
    except ImportError:
        results.append(CP("T4", "Drift detector importable", False, "frontend_drift_detector.py not found"))

    return results


# ── CP-RESPONSIVE ─────────────────────────────────────────────────────────────

def cp_responsive() -> list[CP]:
    results = []

    # RS1: hooks.ts exists with useBreakpoint
    hooks = read_file("lib/hooks.ts")
    has_hook = "useBreakpoint" in hooks and "mobile" in hooks and "tablet" in hooks
    results.append(CP("RS1", "lib/hooks.ts exports useBreakpoint with 3 breakpoints", has_hook))

    # RS2: each built page imports useBreakpoint
    missing = []
    for rel, label, min_lines in REQUIRED_PAGES:
        content = read_file(rel)
        if file_lines(rel) >= min_lines and "useBreakpoint" not in content:
            missing.append(rel)
    ok = len(missing) == 0
    results.append(CP("RS2", "All built pages import useBreakpoint", ok,
        "Missing useBreakpoint in: " + ", ".join(missing) if not ok else ""))

    # RS3: drift detector finds no responsive violations
    try:
        from frontend_drift_detector import run_scan
        scan = run_scan()
        resp_errors = [v for v in scan.violations if v.category == "RESPONSIVE"]
        ok2 = len(resp_errors) == 0
        results.append(CP("RS3", f"No responsive violations ({len(resp_errors)} warnings)", ok2,
            "\n".join(f"  {v.file} — {v.message}" for v in resp_errors[:5]) if not ok2 else ""))
    except ImportError:
        results.append(CP("RS3", "Drift detector importable", False, "frontend_drift_detector.py not found"))

    return results


# ── CP-AUTH ───────────────────────────────────────────────────────────────────

def cp_auth() -> list[CP]:
    results = []

    # A1: Login page hits correct endpoint
    login = read_file("app/login/page.tsx")
    has_token_endpoint = "/api/v1/auth/token" in login
    results.append(CP("A1", "Login POSTs to /api/v1/auth/token", has_token_endpoint))

    # A2: Token stored — any recognized auth storage pattern
    stores_token = (
        ("access_token" in login and "localStorage.setItem" in login) or
        "setUserInfo" in login or
        "setToken" in login
    )
    results.append(CP("A2", "Login stores session (cookie or localStorage)", stores_token))

    # A3: Home page has auth guard — any recognized guard pattern
    home = read_file("app/page.tsx")
    has_guard = (
        ("access_token" in home or "isLoggedIn" in home or "getToken" in home) and
        "/login" in home
    )
    results.append(CP("A3", "Home page redirects to /login when no session", has_guard))

    # A4: Signup hits correct endpoint
    signup = read_file("app/signup/page.tsx")
    has_signup = "/api/v1/auth/signup" in signup
    results.append(CP("A4", "Signup POSTs to /api/v1/auth/signup", has_signup))

    # A5: No hardcoded credentials
    all_content = " ".join(read_file(rel) for rel, _, _ in REQUIRED_PAGES)
    cred_patterns = [r'password\s*=\s*["\'][^"\']{3,}["\']', r'api[_-]?key\s*=\s*["\'][^"\']+["\']']
    found = any(re.search(p, all_content, re.IGNORECASE) for p in cred_patterns)
    results.append(CP("A5", "No hardcoded credentials in page files", not found,
        "Potential hardcoded credential detected — audit page files" if found else ""))

    return results


# ── CP-FORMS ──────────────────────────────────────────────────────────────────

def cp_forms() -> list[CP]:
    results = []

    login  = read_file("app/login/page.tsx")
    signup = read_file("app/signup/page.tsx")

    # F1: Login has email + password inputs
    has_email = 'type="email"' in login or "type='email'" in login
    has_pass  = 'type="password"' in login
    results.append(CP("F1", "Login has email + password inputs", has_email and has_pass))

    # F2: Login has error state
    has_error = "setError" in login and 'role="alert"' in login
    results.append(CP("F2", "Login shows accessible error messages (role=alert)", has_error))

    # F3: Signup has 2-step flow
    has_steps = "step" in signup.lower() and ("Step 1" in signup or "step === 1" in signup)
    results.append(CP("F3", "Signup has multi-step flow", has_steps))

    # F4: Signup validates password length
    has_pw_validation = "password.length" in signup or "min" in signup.lower()
    results.append(CP("F4", "Signup validates password minimum length", has_pw_validation))

    # F5: Signup validates password confirmation
    has_confirm = "confirmPassword" in signup or "confirm" in signup.lower()
    results.append(CP("F5", "Signup has password confirmation field", has_confirm))

    # F6: Upload page restricts file types (check when built)
    upload = read_file("app/procurement/upload/page.tsx")
    if file_lines("app/procurement/upload/page.tsx") >= 30:
        has_type_check = "pdf" in upload.lower() or "accept=" in upload
        results.append(CP("F6", "Upload page restricts to PDF/DOCX", has_type_check,
            "File type validation missing — add accept='.pdf,.docx' and client-side check" if not has_type_check else ""))

    # F7: Override requires reason (mirrors backend AuditOverride ≥ 20 chars)
    override = read_file("app/[runId]/override/page.tsx")
    if file_lines("app/[runId]/override/page.tsx") >= 30:
        has_reason_validation = "reason" in override.lower() and ("length" in override or "20" in override)
        results.append(CP("F7", "Override requires reason text (≥ 20 chars, mirrors backend)", has_reason_validation,
            "Override form must validate reason.length >= 20 to mirror AuditOverride backend rule" if not has_reason_validation else ""))

    return results


# ── CP-ACCESSIBILITY ──────────────────────────────────────────────────────────

def cp_a11y() -> list[CP]:
    results = []
    try:
        from frontend_drift_detector import run_scan
        scan = run_scan()
        a11y_issues = [v for v in scan.violations if v.category == "A11Y"]
        errors   = [v for v in a11y_issues if v.severity == "ERROR"]
        warnings = [v for v in a11y_issues if v.severity == "WARNING"]

        results.append(CP("AX1", f"No a11y errors ({len(errors)} found)", len(errors) == 0,
            "\n".join(f"  {v.file} — {v.message}" for v in errors[:5]) if errors else ""))
        results.append(CP("AX2", f"No a11y warnings ({len(warnings)} found)", len(warnings) == 0,
            "\n".join(f"  {v.file} — {v.message}" for v in warnings[:5]) if warnings else ""))
    except ImportError:
        results.append(CP("AX1", "A11y scan (drift detector importable)", False))

    return results


# ── CP-ENTERPRISE-DOMAIN ──────────────────────────────────────────────────────

def cp_domain() -> list[CP]:
    results = []

    # ED1: Results page shows citations/evidence (not raw scores only)
    results_page = read_file("app/[runId]/results/page.tsx")
    if file_lines("app/[runId]/results/page.tsx") >= 30:
        has_citations = any(w in results_page for w in ["audit", "citation", "evidence", "grounding", "source"])
        results.append(CP("ED1", "Results page displays audit trail / citations", has_citations,
            "Results must show evidence/citations for each vendor score — not raw numbers only" if not has_citations else ""))

    # ED2: Override page enforces reason text
    override_page = read_file("app/[runId]/override/page.tsx")
    if file_lines("app/[runId]/override/page.tsx") >= 30:
        has_reason = "reason" in override_page.lower()
        results.append(CP("ED2", "Override page captures reason for governance audit", has_reason,
            "Override must require a written reason — every override is audited" if not has_reason else ""))

    # ED3: Status colours are semantic (not raw red/green)
    all_pages = " ".join(read_file(rel) for rel, _, _ in REQUIRED_PAGES)
    uses_semantic = "var(--color-success)" in all_pages or "var(--color-error)" in all_pages
    uses_raw_color = bool(re.search(r'''["'](?:red|green|#e53|#2ecc|rgb\(255,0)['":]''', all_pages))
    results.append(CP("ED3", "Status colours use semantic vars (not raw red/green)", uses_semantic and not uses_raw_color))

    # ED4: Progress page mentions SSE / EventSource / stream
    progress = read_file("app/[runId]/progress/page.tsx")
    if file_lines("app/[runId]/progress/page.tsx") >= 30:
        has_sse = any(w in progress for w in ["EventSource", "stream", "SSE", "eventsource"])
        results.append(CP("ED4", "Progress page uses SSE / EventSource", has_sse,
            "Progress page must connect to /api/v1/evaluate/{runId}/stream via EventSource" if not has_sse else ""))

    return results


# ── CP-SECURITY ───────────────────────────────────────────────────────────────

def cp_security() -> list[CP]:
    results = []
    try:
        from frontend_drift_detector import run_scan
        scan = run_scan()
        sec_errors = [v for v in scan.errors if v.category == "SECURITY"]
        results.append(CP("SEC1", f"No security violations ({len(sec_errors)} found)", len(sec_errors) == 0,
            "\n".join(f"  {v.file}:{v.line} — {v.message}" for v in sec_errors[:5]) if sec_errors else ""))
    except ImportError:
        results.append(CP("SEC1", "Security scan (drift detector importable)", False))

    # SEC2: .env.local not committed
    env_local = Path(__file__).parent.parent / "frontend" / ".env.local"
    # Check git tracking
    code, out = run_cmd(["git", "ls-files", "--error-unmatch", "frontend/.env.local"],
                        Path(__file__).parent.parent)
    not_tracked = code != 0
    results.append(CP("SEC2", ".env.local not tracked by git", not_tracked,
        "frontend/.env.local is tracked by git — add to .gitignore" if not not_tracked else ""))

    return results


# ── CP-PERFORMANCE ────────────────────────────────────────────────────────────

def cp_perf() -> list[CP]:
    results = []

    # P1: No synchronous localStorage in render body
    # Heuristic: if localStorage is used but useEffect is absent, likely called at render time
    violations = []
    for rel, _, min_lines in REQUIRED_PAGES:
        content = read_file(rel)
        if file_lines(rel) < min_lines:
            continue
        if "localStorage" in content and "useEffect" not in content:
            violations.append(rel)

    results.append(CP("P1", "localStorage access is inside useEffect (SSR-safe)", len(violations) == 0,
        "localStorage used outside useEffect in: " + ", ".join(violations) if violations else ""))

    # P2: SSE EventSource cleanup (progress page)
    progress = read_file("app/[runId]/progress/page.tsx")
    if file_lines("app/[runId]/progress/page.tsx") >= 30:
        has_cleanup = "close()" in progress or "return () =>" in progress
        results.append(CP("P2", "SSE EventSource closed on component unmount", has_cleanup,
            "Progress page must call eventSource.close() in useEffect cleanup to prevent memory leaks" if not has_cleanup else ""))

    return results


# ── Runner ────────────────────────────────────────────────────────────────────

CATEGORIES = {
    "BUILD":    ("Build & Configuration",           cp_build),
    "ROUTES":   ("Page Route Completeness",          cp_routes),
    "THEME":    ("CSS Variable & Theme Compliance",  cp_theme),
    "RESPONSIVE":("Responsive Design",               cp_responsive),
    "AUTH":     ("Authentication & JWT",             cp_auth),
    "FORMS":    ("Form Validation",                  cp_forms),
    "A11Y":     ("Accessibility",                    cp_a11y),
    "DOMAIN":   ("Enterprise RFP Domain Rules",      cp_domain),
    "SECURITY": ("Security",                         cp_security),
    "PERF":     ("Performance",                      cp_perf),
}


def print_status():
    print("\n── Frontend Checkpoint Status ───────────────────────────────────\n")
    total_pass = total_fail = 0
    for key, (label, fn) in CATEGORIES.items():
        checks = fn()
        passed = sum(1 for c in checks if c.passed)
        total  = len(checks)
        total_pass += passed
        total_fail += (total - passed)
        icon = PASS if passed == total else FAIL
        print(f"  {icon} {key:12} {label}")
        print(f"      {passed}/{total} checks passed")
        for c in checks:
            mark = PASS if c.passed else FAIL
            print(f"        {mark} [{c.id}] {c.label}")
            if not c.passed and c.detail:
                for line in c.detail.splitlines():
                    print(f"              {line}")
    print(f"\n── Total: {total_pass} passed, {total_fail} failed ─────────────────────────────\n")
    return total_fail == 0


def print_status_summary():
    print("\n── Frontend Checkpoint Status (summary) ─────────────────────────\n")
    total_pass = total_fail = 0
    for key, (label, fn) in CATEGORIES.items():
        checks = fn()
        passed = sum(1 for c in checks if c.passed)
        total  = len(checks)
        total_pass += passed
        total_fail += (total - passed)
        icon = PASS if passed == total else FAIL
        print(f"  {icon} {key:12} {passed}/{total}  {label}")
    print(f"\n── Total: {total_pass} passed, {total_fail} failed ─────────────────────────────\n")
    return total_fail == 0


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args or args[0] == "status":
        ok = print_status_summary()
        sys.exit(0 if ok else 1)

    elif args[0] == "run":
        if len(args) > 1:
            # Support multiple categories: python frontend_checkpoint_runner.py run BUILD AUTH FORMS
            cats = {}
            for key in args[1:]:
                key = key.upper()
                if key not in CATEGORIES:
                    print(f"Unknown category: {key}. Choose from: {', '.join(CATEGORIES)}")
                    sys.exit(1)
                cats[key] = CATEGORIES[key]
        else:
            cats = CATEGORIES

        total_fail = 0
        for key, (label, fn) in cats.items():
            print(f"\n── {key}: {label} ──")
            checks = fn()
            for c in checks:
                mark = PASS if c.passed else FAIL
                print(f"  {mark} [{c.id}] {c.label}")
                if not c.passed and c.detail:
                    for line in c.detail.splitlines():
                        print(f"       {line}")
            failed = sum(1 for c in checks if not c.passed)
            total_fail += failed

        sys.exit(0 if total_fail == 0 else 1)

    else:
        print("Usage: python frontend_checkpoint_runner.py [status|run [CATEGORY]]")
        print(f"Categories: {', '.join(CATEGORIES)}")
        sys.exit(1)
