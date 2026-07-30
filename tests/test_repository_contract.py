"""Contract checks for the Climate-FCV country evidence bank scaffold."""

import json
import subprocess
from pathlib import Path

import jsonschema
import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATHS = (
    "schemas/source.schema.json",
    "schemas/evidence.schema.json",
    "schemas/pathway.schema.json",
    "schemas/review.schema.json",
    "schemas/runtime-release.schema.json",
)
IGNORED_PATHS = (
    "source_documents/example.pdf",
    "outside.pdf",
    ".env",
    ".env.production",
    "credentials.json",
    "private.pem",
    "certificate.p12",
    "certificate.pfx",
    "client_secret.json",
    "secrets.json",
)


def test_required_scaffold_paths_exist() -> None:
    """The public repository exposes its initial contract surfaces."""
    required_paths = (
        "README.md",
        "CLAUDE.md",
        "requirements-dev.txt",
        "pyproject.toml",
        *SCHEMA_PATHS,
        "climate_bank/__init__.py",
        "climate_bank/validation.py",
        "climate_bank/release.py",
        "climate_bank/dossier.py",
        "scripts/__init__.py",
    )

    missing_paths = [
        relative_path
        for relative_path in required_paths
        if not (REPOSITORY_ROOT / relative_path).is_file()
    ]

    assert not missing_paths, f"Missing required scaffold paths: {missing_paths}"


@pytest.mark.parametrize(
    ("relative_path", "expected_type"),
    [
        ("schemas/source.schema.json", "array"),
        ("schemas/evidence.schema.json", "array"),
        ("schemas/pathway.schema.json", "array"),
        ("schemas/review.schema.json", "object"),
        ("schemas/runtime-release.schema.json", "object"),
    ],
)
def test_schema_is_a_valid_draft_2020_12_contract(relative_path: str, expected_type: str) -> None:
    """Each schema is a valid Draft 2020-12 contract of its governed shape."""
    schema = json.loads((REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8"))

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["type"] == expected_type
    jsonschema.Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize("relative_path", IGNORED_PATHS)
def test_gitignore_actually_ignores_protected_content(relative_path: str) -> None:
    """Git's own ignore engine excludes protected public-repository content."""
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", "--", relative_path],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"Expected {relative_path!r} to be ignored; stderr: {result.stderr.strip()}"
    )


def test_readme_uses_portable_test_command() -> None:
    """Public setup instructions do not assume a local machine path."""
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")

    assert "C:/WBG/" not in readme
    assert "python -m pytest" in readme
