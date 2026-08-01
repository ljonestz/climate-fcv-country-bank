"""Tests for approved-only deterministic runtime release construction."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from climate_bank.release import build_release, promote_release
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
    assert "candidate" not in first
    assert "selection_aliases" not in first["countries"]["SSD"]
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


def candidate_country(
    tmp_path: Path, name: str = "SSD", status: str = "reviewed"
) -> Path:
    country_dir = tmp_path / name
    shutil.copytree(FIXTURE_DIR, country_dir)
    shutil.copyfile(
        country_dir / "profile.valid.json",
        country_dir / "profile.json",
    )

    review = _read(country_dir / "review.json")
    review.update(
        {
            "status": status,
            "reviewer": "Pilot reviewer",
            "reviewed_on": "2026-08-01",
            "review_due": "2026-08-31",
        }
    )
    _write(country_dir / "review.json", review)

    evidence = _read(country_dir / "evidence.json")
    for record in evidence:
        record.update(
            {
                "evidence_class": (
                    "direct-climate-fcv"
                    if record["analytical_role"] == "direct-climate-fcv"
                    else "climate-pressure"
                ),
                "administrative_level": "county",
                "ecological_level": None,
                "refresh_tier": "current",
                "review_due": "2026-08-31",
                "review_status": status,
                "review_date": "2026-08-01",
            }
        )
    _write(country_dir / "evidence.json", evidence)

    pathways = _read(country_dir / "pathways.json")
    for record in pathways:
        record["review_status"] = status
        record["review_date"] = "2026-08-01"
    _write(country_dir / "pathways.json", pathways)

    profile = _read(country_dir / "profile.json")
    profile["review_status"] = status
    profile["review_date"] = "2026-08-01"
    _write(country_dir / "profile.json", profile)
    return country_dir


def _candidate_build(country_dir: Path, output_path: Path):
    return build_release(
        [country_dir],
        generated_at="2026-08-01T00:00:00Z",
        schema_version="1.1.0",
        content_version="2026.08.candidate-test",
        output_path=output_path,
    )


@pytest.mark.parametrize("status", ["reviewed", "approved"])
def test_candidate_build_writes_explicit_schema_1_1_preview(
    tmp_path: Path, status: str
) -> None:
    country_dir = candidate_country(tmp_path / "countries", status=status)
    output_path = tmp_path / "previews" / f"{status}.json"

    release = _candidate_build(country_dir, output_path)

    assert output_path.is_file()
    assert _read(output_path) == release
    assert release["schema_version"] == "1.1.0"
    assert release["content_version"] == "2026.08.candidate-test"
    assert release["candidate"] is True
    assert release["countries"]["SSD"]["status"] == status
    assert release["countries"]["SSD"]["selection_aliases"] == _read(
        country_dir / "profile.json"
    )["selection_aliases"]
    assert validate_runtime_release(release) == []


@pytest.mark.parametrize(
    ("kind", "status"),
    [
        ("country", "draft"), ("country", "stale"), ("country", "rejected"),
        ("profile", "draft"), ("profile", "stale"), ("profile", "rejected"),
        ("evidence", "draft"), ("evidence", "stale"), ("evidence", "rejected"),
        ("pathway", "draft"), ("pathway", "stale"), ("pathway", "rejected"),
    ],
)
def test_candidate_rejects_unreviewed_input_statuses(
    tmp_path: Path, kind: str, status: str
) -> None:
    country_dir = candidate_country(tmp_path / "countries")
    if kind == "country":
        filename, id_field = "review.json", None
    elif kind == "profile":
        filename, id_field = "profile.json", None
    elif kind == "evidence":
        filename, id_field = "evidence.json", "evidence_id"
    else:
        filename, id_field = "pathways.json", "pathway_id"
    value = _read(country_dir / filename)
    if id_field is None:
        value["status" if kind == "country" else "review_status"] = status
    else:
        value[0]["review_status"] = status
    _write(country_dir / filename, value)
    output_path = tmp_path / "preview.json"

    with pytest.raises(ValueError, match=rf"{kind}.*{status}"):
        _candidate_build(country_dir, output_path)

    assert not output_path.exists()


def test_candidate_build_refuses_normalized_current_runtime_tail(
    tmp_path: Path,
) -> None:
    country_dir = candidate_country(tmp_path / "countries")
    repository_runtime = (
        Path(__file__).resolve().parents[1]
        / "releases" / "current" / "runtime.json"
    )
    before = repository_runtime.read_bytes()
    current_dir = tmp_path / "releases" / "current"
    current_dir.mkdir(parents=True)
    unsafe_path = current_dir / "nested" / ".." / "runtime.json"

    with pytest.raises(ValueError, match=r"candidate.*releases/current/runtime\.json"):
        _candidate_build(country_dir, unsafe_path)

    assert repository_runtime.read_bytes() == before
    assert not (current_dir / "runtime.json").exists()


@pytest.mark.parametrize(
    "filename",
    [
        "sources.json",
        "evidence.json",
        "pathways.json",
        "review.json",
        "profile.json",
    ],
)
def test_candidate_build_refuses_output_colliding_with_release_input(
    tmp_path: Path, filename: str
) -> None:
    country_dir = candidate_country(tmp_path / "countries")
    input_paths = [
        country_dir / input_name
        for input_name in (
            "sources.json",
            "evidence.json",
            "pathways.json",
            "review.json",
            "profile.json",
        )
    ]
    before_bytes = {path: path.read_bytes() for path in input_paths}
    before_names = sorted(path.name for path in country_dir.iterdir())
    aliased_output = country_dir / "normalized-alias" / ".." / filename

    with pytest.raises(
        ValueError,
        match=rf"candidate output.*release input.*{filename}",
    ):
        _candidate_build(country_dir, aliased_output)

    assert {path: path.read_bytes() for path in input_paths} == before_bytes
    assert sorted(path.name for path in country_dir.iterdir()) == before_names


def test_candidate_release_is_deterministic_canonical_and_does_not_mutate_inputs(
    tmp_path: Path,
) -> None:
    country_dir = candidate_country(tmp_path / "countries")
    sources = _read(country_dir / "sources.json")
    extra = copy.deepcopy(sources[0])
    extra.update(
        {
            "source_id": "SSD-SRC-003",
            "title": "Unreferenced source",
            "url": "https://example.org/unreferenced",
        }
    )
    sources.append(extra)
    _write(country_dir / "sources.json", sources)
    before = {
        path.name: path.read_bytes()
        for path in country_dir.iterdir()
        if path.is_file()
    }

    first_path = tmp_path / "previews" / "first.json"
    second_path = tmp_path / "previews" / "second.json"
    first = _candidate_build(country_dir, first_path)
    second = _candidate_build(country_dir, second_path)

    assert first == second
    assert first_path.read_bytes() == second_path.read_bytes()
    assert first_path.read_bytes().endswith(b"\n")
    assert first_path.read_text(encoding="utf-8") == (
        json.dumps(first, ensure_ascii=False, indent=2) + "\n"
    )
    assert validate_runtime_release(first) == []
    assert [source["source_id"] for source in first["sources"]] == [
        "SSD-SRC-001",
        "SSD-SRC-002",
    ]
    assert {
        path.name: path.read_bytes()
        for path in country_dir.iterdir()
        if path.is_file()
    } == before


@pytest.mark.parametrize(
    ("kind", "record_id"),
    [
        ("country", "SSD"),
        ("profile", "SSD"),
        ("evidence", "SSD-E-001"),
        ("pathway", "SSD-P-001"),
    ],
)
def test_promotion_refuses_each_nonapproved_gate_without_writing(
    tmp_path: Path, kind: str, record_id: str
) -> None:
    country_dir = candidate_country(tmp_path / "countries", status="approved")
    if kind == "country":
        filename, value = "review.json", _read(country_dir / "review.json")
        value["status"] = "reviewed"
    elif kind == "profile":
        filename, value = "profile.json", _read(country_dir / "profile.json")
        value["review_status"] = "reviewed"
    elif kind == "evidence":
        filename, value = "evidence.json", _read(country_dir / "evidence.json")
        value[0]["review_status"] = "reviewed"
    else:
        filename, value = "pathways.json", _read(country_dir / "pathways.json")
        value[0]["review_status"] = "reviewed"
    _write(country_dir / filename, value)
    current_dir = tmp_path / "current"

    with pytest.raises(
        ValueError,
        match=rf"{kind} {record_id} status reviewed.*approved",
    ):
        promote_release(
            [country_dir],
            generated_at="2026-08-01T00:00:00Z",
            content_version="2026.08.promoted-test",
            current_dir=current_dir,
        )

    assert not current_dir.exists()


def test_successful_promotion_writes_approved_schema_1_1_runtime(
    tmp_path: Path,
) -> None:
    country_dir = candidate_country(tmp_path / "countries", status="approved")
    current_dir = tmp_path / "explicit-current"

    first = promote_release(
        [country_dir],
        generated_at="2026-08-01T00:00:00Z",
        content_version="2026.08.promoted-test",
        current_dir=current_dir,
    )
    first_bytes = (current_dir / "runtime.json").read_bytes()
    second = promote_release(
        [country_dir],
        generated_at="2026-08-01T00:00:00Z",
        content_version="2026.08.promoted-test",
        current_dir=current_dir,
    )

    assert first == second
    assert (current_dir / "runtime.json").read_bytes() == first_bytes
    assert first["schema_version"] == "1.1.0"
    assert first["candidate"] is False
    assert first["countries"]["SSD"]["status"] == "approved"
    assert {
        record["review_status"] for record in first["evidence_records"]
    } == {"approved"}
    assert {record["review_status"] for record in first["pathways"]} == {"approved"}
    assert first["countries"]["SSD"]["selection_aliases"] == _read(
        country_dir / "profile.json"
    )["selection_aliases"]
    assert validate_runtime_release(first) == []


@pytest.mark.parametrize("operation", ["candidate", "promotion"])
def test_failed_release_operation_preserves_existing_output(
    tmp_path: Path, operation: str
) -> None:
    country_dir = candidate_country(tmp_path / "countries", status="approved")
    evidence = _read(country_dir / "evidence.json")
    evidence[0]["review_status"] = "rejected"
    _write(country_dir / "evidence.json", evidence)
    output_dir = tmp_path / operation
    output_dir.mkdir()
    output_path = output_dir / "runtime.json"
    output_path.write_bytes(b"existing output\n")
    before_files = sorted(path.name for path in output_dir.iterdir())

    with pytest.raises(ValueError):
        if operation == "candidate":
            _candidate_build(country_dir, output_path)
        else:
            promote_release(
                [country_dir],
                generated_at="2026-08-01T00:00:00Z",
                content_version="2026.08.promoted-test",
                current_dir=output_dir,
            )

    assert output_path.read_bytes() == b"existing output\n"
    assert sorted(path.name for path in output_dir.iterdir()) == before_files


@pytest.mark.parametrize(
    "mutation",
    [
        lambda release: release.pop("candidate"),
        lambda release: release["countries"]["SSD"].pop("selection_aliases"),
        lambda release: release["evidence_records"][0].pop("evidence_class"),
        lambda release: release["evidence_records"][0].pop("administrative_level"),
        lambda release: release["evidence_records"][0].pop("ecological_level"),
        lambda release: release["evidence_records"][0].pop("refresh_tier"),
        lambda release: release["evidence_records"][0].pop("review_due"),
    ],
)
def test_runtime_schema_rejects_missing_schema_1_1_fields(
    tmp_path: Path, mutation
) -> None:
    country_dir = candidate_country(tmp_path / "countries")
    release = _candidate_build(country_dir, tmp_path / "preview.json")
    mutation(release)
    assert validate_runtime_release(release)


@pytest.mark.parametrize(
    ("candidate", "status"),
    [(True, "draft"), (True, "rejected"), (False, "reviewed")],
)
def test_runtime_schema_rejects_invalid_candidate_status_combinations(
    tmp_path: Path, candidate: bool, status: str
) -> None:
    country_dir = candidate_country(
        tmp_path / "countries", status="approved" if not candidate else "reviewed"
    )
    if candidate:
        release = _candidate_build(country_dir, tmp_path / "preview.json")
    else:
        release = promote_release(
            [country_dir],
            generated_at="2026-08-01T00:00:00Z",
            content_version="2026.08.promoted-test",
            current_dir=tmp_path / "current",
        )
    release["countries"]["SSD"]["status"] = status
    release["evidence_records"][0]["review_status"] = status
    release["pathways"][0]["review_status"] = status
    assert validate_runtime_release(release)


def test_candidate_cli_direct_script_supports_explicit_inputs(
    tmp_path: Path,
) -> None:
    country_dir = candidate_country(tmp_path / "countries")
    output_path = tmp_path / "previews" / "runtime.json"
    script = Path(__file__).resolve().parents[1] / "scripts" / "build_release.py"

    result = subprocess.run(
        [
            sys.executable, str(script), "--country-dir", str(country_dir),
            "--generated-at", "2026-08-01T00:00:00Z",
            "--schema-version", "1.1.0",
            "--content-version", "2026.08.cli-candidate",
            "--output", str(output_path),
        ],
        cwd=tmp_path, check=False, capture_output=True, text=True,
    )

    assert result.returncode == 0, result.stderr
    release = _read(output_path)
    assert release["candidate"] is True
    assert release["content_version"] == "2026.08.cli-candidate"


def test_promotion_cli_direct_script_supports_explicit_current_dir(
    tmp_path: Path,
) -> None:
    country_dir = candidate_country(tmp_path / "countries", status="approved")
    current_dir = tmp_path / "current"
    script = Path(__file__).resolve().parents[1] / "scripts" / "build_release.py"

    result = subprocess.run(
        [
            sys.executable, str(script), "--promote",
            "--country-dir", str(country_dir),
            "--generated-at", "2026-08-01T00:00:00Z",
            "--content-version", "2026.08.cli-promoted",
            "--current-dir", str(current_dir),
        ],
        cwd=tmp_path, check=False, capture_output=True, text=True,
    )

    assert result.returncode == 0, result.stderr
    release = _read(current_dir / "runtime.json")
    assert release["candidate"] is False
    assert release["content_version"] == "2026.08.cli-promoted"
