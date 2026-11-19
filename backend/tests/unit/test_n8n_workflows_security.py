"""Test that n8n workflow files contain zero hardcoded secrets or sensitive credentials."""

import json
import re
from pathlib import Path

WORKFLOWS_DIR = Path(__file__).resolve().parents[3] / "n8n" / "workflows"

SECRET_PATTERNS = [
    re.compile(
        r"""(password|secret|token|api[_-]?key)\s*["' :=]+\s*["\']([a-zA-Z0-9_\-]{16,})["\']""",
        re.I,
    ),
    re.compile(r"""BEGIN (RSA|EC|OPENSSH) PRIVATE KEY"""),
    re.compile(r"""bearer\s+[a-zA-Z0-9_\-\.]{16,}""", re.I),
]


def test_n8n_workflows_directory_exists():
    assert WORKFLOWS_DIR.exists(), f"{WORKFLOWS_DIR} does not exist"


def test_all_workflow_files_are_valid_json():
    files = list(WORKFLOWS_DIR.glob("*.json"))
    assert len(files) >= 3, f"Expected at least 3 workflows, found {len(files)}"
    for f in files:
        with open(f, "r", encoding="utf-8") as fp:
            data = json.load(fp)
            assert isinstance(data, dict), f"{f.name} is not a JSON object"
            assert "name" in data or "nodes" in data, f"{f.name} missing standard workflow keys"


def test_no_hardcoded_secrets_in_workflow_json():
    files = list(WORKFLOWS_DIR.glob("*.json"))
    violations = []
    allowed_tokens = ("$env.", "N8N_", "SERVICE_", "X-Signature")

    for f in files:
        content = f.read_text(encoding="utf-8")
        for pattern in SECRET_PATTERNS:
            for match in pattern.finditer(content):
                matched = match.group(0)
                # Allow environment lookups and header variable names
                if any(allowed in matched for allowed in allowed_tokens):
                    continue
                violations.append(f"{f.name}: {matched}")

    details = "\n".join(violations)
    assert not violations, f"Potential hardcoded secrets found in n8n workflows:\n{details}"
