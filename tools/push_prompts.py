"""
Push all prompts in app/prompts/ to LangSmith Hub.

Run once after changing a prompt YAML:
    python tools/push_prompts.py

Each prompt is versioned automatically by LangSmith (commit hash returned).

NOTE: If you see SSL errors on Windows (corporate network / SSL proxy),
run this from WSL, GitHub Actions, or any Linux/server environment where
the cert chain is clean. The local YAML fallback always works for dev.
"""

import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# python-certifi-win32 patches certifi to include Windows trusted root CAs.
# This fixes SSL failures on machines with corporate/self-signed certs.
# Install once: pip install python-certifi-win32
try:
    import certifi_win32 as _cw32  # type: ignore[import-untyped]  # side-effect: patches certifi with Windows CAs
    _ = _cw32
except ImportError:
    pass


def main() -> None:
    api_key = os.getenv("LANGSMITH_API_KEY")
    if not api_key:
        print("ERROR: LANGSMITH_API_KEY not set in environment")
        sys.exit(1)

    try:
        from langsmith import Client
        from langchain_core.prompts import PromptTemplate
    except ImportError as e:
        print(f"ERROR: missing dependency — {e}")
        sys.exit(1)

    import requests, urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    session = requests.Session()
    session.verify = False
    client = Client(session=session)
    prompts_dir = ROOT / "app" / "prompts"
    yaml_files = sorted(prompts_dir.rglob("*.yaml"))

    if not yaml_files:
        print("No YAML files found in app/prompts/")
        sys.exit(0)

    print(f"Pushing {len(yaml_files)} prompts to LangSmith Hub...\n")

    for path in yaml_files:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        identifier  = data["name"]
        template    = data["template"]
        description = data.get("description", "")
        input_vars  = data.get("input_variables", [])

        # LangChain PromptTemplate uses f-string format: literal { must be {{
        # Our YAML uses {variable} for vars and { for JSON examples — escape JSON braces first
        lc_template = template
        for var in input_vars:
            lc_template = lc_template.replace("{" + var + "}", f"__VAR_{var}__")
        lc_template = lc_template.replace("{", "{{").replace("}", "}}")
        for var in input_vars:
            lc_template = lc_template.replace(f"__VAR_{var}__", "{" + var + "}")

        prompt_obj = PromptTemplate(
            template=lc_template,
            input_variables=input_vars if input_vars else ["__unused__"],
        )

        try:
            commit_url = client.push_prompt(
                identifier,
                object=prompt_obj,
                description=description.strip() if description else None,
                is_public=False,
            )
            print(f"  OK  {identifier}")
            print(f"      {commit_url}")
        except Exception as e:
            print(f"  FAIL {identifier} — {e}")

    print("\nDone.")


if __name__ == "__main__":
    # Load .env so LANGSMITH_API_KEY is available
    env_path = ROOT / ".env"
    if env_path.exists():
        with open(env_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())

    main()
