"""Tests for deterministic, ledger-traceable dossier construction."""

from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from climate_bank.dossier import build_dossier
from scripts import build_dossier as dossier_cli


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "valid_country"
HEADINGS = [
    "## 1. Scope, sources, and limitations",
    "## 2. Climate baseline",
    "## 3. Vulnerability and capacity",
    "## 4. Institutions, services, sectors, and livelihoods",
    "## 5. Mediated Climate-FCV pathways",
    "## 6. Reverse pathways",
    "## 7. Resilience factors",
    "## 8. Uncertainties",
    "## 9. Project-screening implications",
    "## 10. Evidence table",
    "## 11. Bibliography",
]


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def copied_country(tmp_path: Path) -> Path:
    country_dir = tmp_path / "SSD"
    shutil.copytree(FIXTURE_DIR, country_dir)
    return country_dir


def test_dossier_has_exact_title_headings_order_and_ids() -> None:
    dossier = build_dossier(FIXTURE_DIR)

    assert dossier.startswith("# South Sudan Climate-FCV Evidence Dossier\n")
    positions = [dossier.index(heading) for heading in HEADINGS]
    assert positions == sorted(positions)
    assert "SSD-E-001" in dossier
    assert "SSD-E-002" in dossier
    assert "SSD-P-001" in dossier


def test_dossier_renders_stored_sentinels_verbatim(tmp_path: Path) -> None:
    country_dir = copied_country(tmp_path)
    evidence = _read(country_dir / "evidence.json")
    sources = _read(country_dir / "sources.json")
    pathways = _read(country_dir / "pathways.json")
    evidence[0]["statement"] = "SENTINEL STORED EVIDENCE STATEMENT."
    sources[0]["methodology"] = "SENTINEL STORED METHODOLOGY."
    sources[0]["limitations"] = "SENTINEL STORED LIMITATION."
    pathways[0]["uncertainty"] = "SENTINEL STORED PATHWAY UNCERTAINTY."
    _write(country_dir / "evidence.json", evidence)
    _write(country_dir / "sources.json", sources)
    _write(country_dir / "pathways.json", pathways)

    dossier = build_dossier(country_dir)

    for sentinel in (
        "SENTINEL STORED EVIDENCE STATEMENT.",
        "SENTINEL STORED METHODOLOGY.",
        "SENTINEL STORED LIMITATION.",
        "SENTINEL STORED PATHWAY UNCERTAINTY.",
    ):
        assert sentinel in dossier


def test_direct_evidence_without_section_metadata_renders_full_statement(
    tmp_path: Path,
) -> None:
    country_dir = copied_country(tmp_path)
    evidence = _read(country_dir / "evidence.json")
    direct = evidence[0]
    direct["statement"] = "SENTINEL DIRECT EVIDENCE WITHOUT SECTION METADATA."
    direct["institutions"] = []
    direct["sectors"] = []
    direct["systems_assets_resources"] = []
    _write(country_dir / "evidence.json", evidence)

    dossier = build_dossier(country_dir)
    expected = (
        "Evidence: SENTINEL DIRECT EVIDENCE WITHOUT SECTION METADATA. "
        "[SSD-E-001]"
    )
    section_four = dossier.split(HEADINGS[3], 1)[1].split(HEADINGS[4], 1)[0]

    assert expected in section_four
    assert dossier.count(expected) == 1

def test_pathway_paragraph_renders_every_stored_field() -> None:
    dossier = build_dossier(FIXTURE_DIR)
    pathway_line = next(
        line for line in dossier.splitlines() if line.startswith("Pathway:")
    )
    expected_labels = (
        "Pathway ID:",
        "ISO3:",
        "Climate pressure:",
        "Documented impact:",
        "FCV mediator:",
        "Possible consequence:",
        "Geographies:",
        "Affected groups:",
        "Sectors:",
        "Systems, assets, and resources:",
        "Institutions:",
        "Supporting evidence IDs:",
        "Link evidence:",
        "Evidence strength:",
        "Alternative explanations:",
        "Uncertainty:",
        "Resilience factors:",
        "Compact statement:",
        "Interaction direction:",
        "Review status:",
        "Review date:",
    )
    for label in expected_labels:
        assert label in pathway_line

    pathway = _read(FIXTURE_DIR / "pathways.json")[0]
    for field, value in pathway.items():
        if value is None:
            expected = "null"
        elif isinstance(value, (list, dict)):
            expected = json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        else:
            expected = str(value)
        assert expected in pathway_line, field


def test_screening_implications_use_only_compact_statements_and_ids() -> None:
    dossier = build_dossier(FIXTURE_DIR)
    section = dossier.split(HEADINGS[8], 1)[1].split(HEADINGS[9], 1)[0]
    evidence = _read(FIXTURE_DIR / "evidence.json")
    pathways = _read(FIXTURE_DIR / "pathways.json")

    assert section.strip().splitlines() == [
        f"Screening implication: {evidence[0]['compact_statement']} [SSD-E-001]",
        f"Screening implication: {evidence[1]['compact_statement']} [SSD-E-002]",
        (
            f"Screening implication: {pathways[0]['compact_statement']} "
            "[SSD-P-001; SSD-E-001, SSD-E-002]"
        ),
    ]
    for forbidden in (
        "Status:",
        "role:",
        "confidence:",
        "sectors:",
        "institutions:",
    ):
        assert forbidden not in section


def test_every_analytical_line_is_traceable_to_canonical_ids() -> None:
    dossier = build_dossier(FIXTURE_DIR)
    analytical_prefixes = (
        "Evidence:",
        "Pathway:",
        "Reverse pathway:",
        "Resilience factor:",
        "Uncertainty:",
        "Screening implication:",
    )

    analytical_lines = [
        line for line in dossier.splitlines() if line.startswith(analytical_prefixes)
    ]
    assert analytical_lines
    assert all(
        line.endswith(
            ("[SSD-E-001]", "[SSD-E-002]", "[SSD-P-001; SSD-E-001, SSD-E-002]")
        )
        for line in analytical_lines
    )


def test_dossier_contains_no_general_knowledge_or_model_self_citation() -> None:
    dossier = build_dossier(FIXTURE_DIR).lower()

    assert "general knowledge" not in dossier
    assert "general-knowledge" not in dossier
    assert "as an ai" not in dossier
    assert "language model" not in dossier


def test_dossier_is_deterministic_and_ends_one_newline() -> None:
    first = build_dossier(FIXTURE_DIR)
    second = build_dossier(FIXTURE_DIR)

    assert first == second
    assert first.endswith("\n")
    assert not first.endswith("\n\n")


def test_invalid_country_input_raises_with_validation_errors(tmp_path: Path) -> None:
    country_dir = copied_country(tmp_path)
    (country_dir / "sources.json").unlink()

    with pytest.raises(ValueError, match="sources.json: missing file"):
        build_dossier(country_dir)


def test_dossier_cli_writes_output_and_reports_word_count(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    countries = tmp_path / "countries"
    countries.mkdir()
    country_dir = countries / "SSD"
    shutil.copytree(FIXTURE_DIR, country_dir)

    result = dossier_cli.main(["--country", "SSD"], root=tmp_path)

    output_path = country_dir / "dossier.md"
    assert result == 0
    assert output_path.read_text(encoding="utf-8") == build_dossier(country_dir)
    stdout = capsys.readouterr().out
    assert str(output_path) in stdout
    assert "words=" in stdout


def test_dossier_cli_invalid_country_returns_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = dossier_cli.main(["--country", "SSD"], root=tmp_path)

    assert result != 0
    assert "missing file" in capsys.readouterr().err
