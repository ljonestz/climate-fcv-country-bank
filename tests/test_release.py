"""Tests for approved-only deterministic runtime release construction."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from climate_bank.release import build_release
from climate_bank.validation import validate_runtime_release
from scripts import build_release as release_cli


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "valid_country"
GENERATED_AT = "2026-07-30T00:00:00Z"


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def approved_country(tmp_path: Path, name: str = "SSD") -> Path:
    country_dir = tmp_path / name
    shutil.copytree(FIXTURE_DIR, country_dir)

    review = _read(country_dir / "review.json")
    review.update(
        {
            "status": "approved",
            "reviewer": "Pilot reviewer",
            "reviewed_on": "2026-07-29",
            "review_due": "2026-07-30",
        }
    )
    _write(country_dir / "review.json", review)

    for filename in ("evidence.json", "pathways.json"):
        records = _read(country_dir / filename)
        for record in records:
            record["review_status"] = "approved"
            record["review_date"] = "2026-07-29"
        _write(country_dir / filename, records)
    return country_dir


def test_draft_only_input_raises_instead_of_emitting_empty_release() -> None:
    with pytest.raises(ValueError, match="no approved country content"):
        build_release([FIXTURE_DIR], generated_at=GENERATED_AT)


def test_approved_release_is_deterministic_valid_and_canonical(tmp_path: Path) -> None:
    country_dir = approved_country(tmp_path)

    first = build_release([country_dir], generated_at=GENERATED_AT)
    second = build_release([country_dir], generated_at=GENERATED_AT)

    assert first == second
    assert validate_runtime_release(first) == []
    assert first["schema_version"] == "1.0.0"
    assert first["content_version"] == "2026.07.south-sudan-pilot"
    assert first["generated_at"] == GENERATED_AT
    assert first["countries"] == {
        "SSD": {
            "iso3": "SSD",
            "name": "Synthetic South Sudan Pilot",
            "aliases": ["Synthetic SSD"],
            "status": "approved",
            "reviewer": "Pilot reviewer",
            "reviewed_on": "2026-07-29",
            "review_due": "2026-07-30",
            "dossier_path": "countries/SSD/dossier.md",
            "evidence_ids": ["SSD-E-001", "SSD-E-002"],
            "pathway_ids": ["SSD-P-001"],
            "decision_notes": (
                "Synthetic draft review record for deterministic validation tests."
            ),
        }
    }


def test_review_due_before_generation_date_is_rejected_but_equal_is_valid(
    tmp_path: Path,
) -> None:
    country_dir = approved_country(tmp_path)
    review = _read(country_dir / "review.json")
    review["review_due"] = "2026-07-29"
    _write(country_dir / "review.json", review)

    with pytest.raises(ValueError, match=r"review_due .* earlier than generated_at"):
        build_release([country_dir], generated_at=GENERATED_AT)

    review["review_due"] = "2026-07-30"
    _write(country_dir / "review.json", review)
    assert build_release([country_dir], generated_at=GENERATED_AT)["countries"]["SSD"]


@pytest.mark.parametrize(
    ("filename", "record_id"),
    [("evidence.json", "SSD-E-001"), ("pathways.json", "SSD-P-001")],
)
def test_approved_country_rejects_nonapproved_ledger_records(
    tmp_path: Path, filename: str, record_id: str
) -> None:
    country_dir = approved_country(tmp_path)
    records = _read(country_dir / filename)
    records[0]["review_status"] = "reviewed"
    _write(country_dir / filename, records)

    with pytest.raises(ValueError, match=rf"{record_id}.*must be approved"):
        build_release([country_dir], generated_at=GENERATED_AT)


def test_country_validation_errors_are_surfaced_with_country_path(
    tmp_path: Path,
) -> None:
    country_dir = tmp_path / "invalid"
    shutil.copytree(FIXTURE_DIR, country_dir)
    (country_dir / "review.json").unlink()

    with pytest.raises(ValueError) as exc_info:
        build_release([country_dir], generated_at=GENERATED_AT)

    message = str(exc_info.value)
    assert str(country_dir) in message
    assert "review.json: missing file" in message


def test_unreferenced_registered_source_is_excluded(tmp_path: Path) -> None:
    country_dir = approved_country(tmp_path)
    sources = _read(country_dir / "sources.json")
    extra = copy.deepcopy(sources[0])
    extra.update(
        {
            "source_id": "SSD-SRC-003",
            "title": "Valid but unreferenced source",
            "url": "https://example.org/unreferenced",
        }
    )
    sources.append(extra)
    _write(country_dir / "sources.json", sources)

    release = build_release([country_dir], generated_at=GENERATED_AT)

    assert [source["source_id"] for source in release["sources"]] == [
        "SSD-SRC-001",
        "SSD-SRC-002",
    ]


def test_checksum_and_sorting_are_canonical_without_mutating_inputs(
    tmp_path: Path,
) -> None:
    country_dir = approved_country(tmp_path)
    sources = list(reversed(_read(country_dir / "sources.json")))
    evidence = list(reversed(_read(country_dir / "evidence.json")))
    review = _read(country_dir / "review.json")
    review["country_aliases"] = ["Zulu alias", "Alpha alias"]
    review["evidence_ids"] = list(reversed(review["evidence_ids"]))
    _write(country_dir / "sources.json", sources)
    _write(country_dir / "evidence.json", evidence)
    _write(country_dir / "review.json", review)
    original_review_text = (country_dir / "review.json").read_text(encoding="utf-8")

    release = build_release([country_dir], generated_at=GENERATED_AT)
    manifest_sources = [
        {key: value for key, value in source.items() if key != "checksum"}
        for source in release["sources"]
    ]
    checksum_payload = json.dumps(
        manifest_sources,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    assert [item["source_id"] for item in release["sources"]] == [
        "SSD-SRC-001",
        "SSD-SRC-002",
    ]
    assert [item["evidence_id"] for item in release["evidence_records"]] == [
        "SSD-E-001",
        "SSD-E-002",
    ]
    assert release["countries"]["SSD"]["aliases"] == ["Alpha alias", "Zulu alias"]
    assert release["countries"]["SSD"]["evidence_ids"] == [
        "SSD-E-001",
        "SSD-E-002",
    ]
    assert release["source_manifest_checksum"] == hashlib.sha256(
        checksum_payload
    ).hexdigest()
    assert (
        country_dir / "review.json"
    ).read_text(encoding="utf-8") == original_review_text


def test_source_checksum_field_does_not_affect_manifest_but_content_does(
    tmp_path: Path,
) -> None:
    baseline_dir = approved_country(tmp_path, "baseline")
    checksum_dir = approved_country(tmp_path, "checksum-change")
    content_dir = approved_country(tmp_path, "content-change")

    checksum_sources = _read(checksum_dir / "sources.json")
    checksum_sources[1]["checksum"] = "b" * 64
    _write(checksum_dir / "sources.json", checksum_sources)

    content_sources = _read(content_dir / "sources.json")
    content_sources[1]["title"] = "Changed stored source title"
    _write(content_dir / "sources.json", content_sources)

    baseline_hash = build_release(
        [baseline_dir], generated_at=GENERATED_AT
    )["source_manifest_checksum"]
    checksum_hash = build_release(
        [checksum_dir], generated_at=GENERATED_AT
    )["source_manifest_checksum"]
    content_hash = build_release(
        [content_dir], generated_at=GENERATED_AT
    )["source_manifest_checksum"]

    assert checksum_hash == baseline_hash
    assert content_hash != baseline_hash


def test_country_scoped_source_ids_prevent_valid_cross_country_collision(
    tmp_path: Path,
) -> None:
    """The valid collision boundary is duplicate input for the same approved country."""
    country_dir = approved_country(tmp_path)

    with pytest.raises(ValueError, match=r"duplicate country ISO3 SSD"):
        build_release([country_dir, country_dir], generated_at=GENERATED_AT)


def test_runtime_structure_excludes_dossier_prose_and_general_knowledge(
    tmp_path: Path,
) -> None:
    country_dir = approved_country(tmp_path)
    (country_dir / "dossier.md").write_text(
        "SENTINEL DOSSIER NARRATIVE general knowledge\n", encoding="utf-8"
    )

    serialized = json.dumps(
        build_release([country_dir], generated_at=GENERATED_AT),
        ensure_ascii=False,
    )

    assert "SENTINEL DOSSIER NARRATIVE" not in serialized
    assert "general-knowledge" not in serialized


@pytest.mark.parametrize(
    "generated_at",
    ["not-a-date", "2026-07-30", "2026-07-30T25:00:00Z", ""],
)
def test_malformed_generated_at_is_rejected_clearly(
    tmp_path: Path, generated_at: str
) -> None:
    country_dir = approved_country(tmp_path)

    with pytest.raises(ValueError, match="generated_at.*ISO date-time"):
        build_release([country_dir], generated_at=generated_at)


def test_release_cli_writes_valid_output_and_reports_counts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    country_dir = approved_country(tmp_path / "countries")

    result = release_cli.main(
        ["--generated-at", GENERATED_AT],
        root=tmp_path,
    )

    output_path = tmp_path / "releases" / "current" / "runtime.json"
    assert result == 0
    assert output_path.is_file()
    assert validate_runtime_release(_read(output_path)) == []
    stdout = capsys.readouterr().out
    assert str(output_path) in stdout
    assert "2026.07.south-sudan-pilot" in stdout
    assert "countries=1" in stdout
    assert "evidence=2" in stdout
    assert "pathways=1" in stdout


def test_release_cli_failure_does_not_leave_invalid_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    countries = tmp_path / "countries"
    countries.mkdir()
    shutil.copytree(FIXTURE_DIR, countries / "SSD")

    result = release_cli.main(
        ["--generated-at", GENERATED_AT],
        root=tmp_path,
    )

    assert result != 0
    assert not (tmp_path / "releases" / "current" / "runtime.json").exists()
    assert "no approved country content" in capsys.readouterr().err
