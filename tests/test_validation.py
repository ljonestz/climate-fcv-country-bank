"""Tests for deterministic country-bank validation."""
import copy
import json
import shutil
from pathlib import Path

import pytest

from climate_bank import validation

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "valid_country"


@pytest.fixture
def country_dir(tmp_path):
    target = tmp_path / "SSD"
    shutil.copytree(FIXTURE_DIR, target)
    return target


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def mutate(directory, filename, change):
    path = directory / filename
    value = read(path)
    change(value)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def assert_error(errors, *parts):
    assert any(all(part in error for part in parts) for error in errors), errors


def test_valid_fixture(country_dir):
    assert validation.validate_country_directory(country_dir) == []


def test_general_knowledge_rejected(country_dir):
    mutate(country_dir, "sources.json", lambda x: x[0].__setitem__("source_id", "general-knowledge"))
    mutate(country_dir, "evidence.json", lambda x: x[0]["source_refs"][0].__setitem__("source_id", "general-knowledge"))
    assert_error(validation.validate_country_directory(country_dir), "general-knowledge")


@pytest.mark.parametrize("locator", ["", "   "])
def test_blank_locator_rejected(country_dir, locator):
    mutate(country_dir, "evidence.json", lambda x: x[0]["source_refs"][0].__setitem__("locator", locator))
    assert_error(validation.validate_country_directory(country_dir), "evidence.json", "locator")


def test_unknown_supporting_id_rejected(country_dir):
    mutate(country_dir, "pathways.json", lambda x: x[0]["supporting_evidence_ids"].append("SSD-E-999"))
    assert_error(validation.validate_country_directory(country_dir), "SSD-P-001", "supporting_evidence_ids", "SSD-E-999")


def test_unknown_link_id_rejected(country_dir):
    def change(records):
        records[0]["supporting_evidence_ids"].append("SSD-E-999")
        records[0]["link_evidence"]["pressure"].append("SSD-E-999")
    mutate(country_dir, "pathways.json", change)
    assert_error(validation.validate_country_directory(country_dir), "link_evidence.pressure", "SSD-E-999")


def test_link_id_must_be_supporting(country_dir):
    mutate(country_dir, "pathways.json", lambda x: x[0]["link_evidence"]["impact"].append("SSD-E-999"))
    assert_error(validation.validate_country_directory(country_dir), "link_evidence.impact", "SSD-E-999", "supporting_evidence_ids")


@pytest.mark.parametrize(("filename", "change", "message"), [
    ("sources.json", lambda x: x.append(copy.deepcopy(x[0])), "duplicate source_id SSD-SRC-001"),
    ("evidence.json", lambda x: x.append(copy.deepcopy(x[0])), "duplicate evidence_id SSD-E-001"),
    ("pathways.json", lambda x: x.append(copy.deepcopy(x[0])), "duplicate pathway_id SSD-P-001"),
    ("review.json", lambda x: x["evidence_ids"].append("SSD-E-001"), "duplicate evidence_id SSD-E-001"),
])
def test_duplicate_ids_rejected(country_dir, filename, change, message):
    mutate(country_dir, filename, change)
    assert_error(validation.validate_country_directory(country_dir), message)


@pytest.mark.parametrize(("filename", "change", "parts"), [
    ("evidence.json", lambda x: x[0].__setitem__("iso3", "KEN"), ("SSD-E-001", "iso3", "SSD")),
    ("evidence.json", lambda x: x[0].__setitem__("evidence_id", "KEN-E-001"), ("KEN-E-001", "prefix", "SSD")),
    ("pathways.json", lambda x: x[0].__setitem__("iso3", "KEN"), ("SSD-P-001", "iso3", "SSD")),
    ("pathways.json", lambda x: x[0].__setitem__("pathway_id", "KEN-P-001"), ("KEN-P-001", "prefix", "SSD")),
])
def test_iso3_prefix_mismatches(country_dir, filename, change, parts):
    mutate(country_dir, filename, change)
    assert_error(validation.validate_country_directory(country_dir), *parts)


@pytest.mark.parametrize(("filename", "field", "unsafe"), [
    ("sources.json", "repository_file", "../private/source.txt"),
    ("sources.json", "repository_file", "C:/private/source.txt"),
    ("sources.json", "repository_file", "source_documents/source.txt"),
    ("review.json", "dossier_path", "../SSD/dossier.md"),
    ("review.json", "dossier_path", "/countries/SSD/dossier.md"),
    ("review.json", "dossier_path", "source_documents/dossier.md"),
])
def test_unsafe_paths(country_dir, filename, field, unsafe):
    def change(value):
        target = value[0] if isinstance(value, list) else value
        target[field] = unsafe
        if field == "repository_file":
            target["checksum"] = "a" * 64
    mutate(country_dir, filename, change)
    assert_error(validation.validate_country_directory(country_dir), filename, field)


def test_missing_file_does_not_raise(country_dir):
    (country_dir / "evidence.json").unlink()
    assert_error(validation.validate_country_directory(country_dir), "evidence.json", "missing")


def test_invalid_json_does_not_raise(country_dir):
    (country_dir / "pathways.json").write_text("{broken", encoding="utf-8")
    assert_error(validation.validate_country_directory(country_dir), "pathways.json", "invalid JSON")


@pytest.mark.parametrize("status", ["reviewed", "approved"])
def test_review_status_requires_metadata(country_dir, status):
    mutate(country_dir, "review.json", lambda x: x.__setitem__("status", status))
    errors = validation.validate_country_directory(country_dir)
    for field in ("reviewer", "reviewed_on", "review_due"):
        assert_error(errors, "review.json", status, field)


@pytest.mark.parametrize("filename", ["evidence.json", "pathways.json"])
def test_approved_content_requires_review_date(country_dir, filename):
    mutate(country_dir, filename, lambda x: x[0].__setitem__("review_status", "approved"))
    assert_error(validation.validate_country_directory(country_dir), filename, "approved", "review_date")


def valid_release():
    sources = read(FIXTURE_DIR / "sources.json")
    evidence = read(FIXTURE_DIR / "evidence.json")
    pathways = read(FIXTURE_DIR / "pathways.json")
    for record in evidence + pathways:
        record["review_status"] = "approved"
        record["review_date"] = "2026-07-30"
    return {
        "schema_version": "1.0.0", "content_version": "2026.07.30",
        "generated_at": "2026-07-30T19:00:00Z",
        "countries": {"SSD": {"iso3": "SSD", "name": "Synthetic South Sudan Pilot",
            "aliases": ["Synthetic SSD"], "status": "approved", "reviewer": "Human Reviewer",
            "reviewed_on": "2026-07-30", "review_due": "2027-07-30",
            "dossier_path": "countries/SSD/dossier.md", "evidence_ids": ["SSD-E-001", "SSD-E-002"],
            "pathway_ids": ["SSD-P-001"], "decision_notes": "Synthetic approval."}},
        "sources": sources, "evidence_records": evidence, "pathways": pathways,
        "source_manifest_checksum": "b" * 64,
    }


def test_valid_runtime_release():
    assert validation.validate_runtime_release(valid_release()) == []


@pytest.mark.parametrize(("change", "fragment"), [
    (lambda x: x.__setitem__("schema_version", "2.0.0"), "schema_version"),
    (lambda x: x["evidence_records"][0].__setitem__("review_status", "draft"), "review_status"),
    (lambda x: x["countries"]["SSD"].__setitem__("status", "reviewed"), "status"),
    (lambda x: x.__setitem__("source_manifest_checksum", "bad"), "source_manifest_checksum"),
])
def test_invalid_runtime_release(change, fragment):
    release = valid_release()
    change(release)
    assert_error(validation.validate_runtime_release(release), fragment)


def test_errors_sorted_unique(country_dir):
    mutate(country_dir, "evidence.json", lambda x: x.append(copy.deepcopy(x[0])))
    errors = validation.validate_country_directory(country_dir)
    assert errors == sorted(set(errors))


@pytest.mark.parametrize(("filename", "change"), [
    ("sources.json", lambda x: x[0].__setitem__("source_id", [])),
    ("pathways.json", lambda x: x[0].__setitem__("supporting_evidence_ids", [[]])),
    ("review.json", lambda x: x.__setitem__("evidence_ids", [[]])),
])
def test_malformed_nested_json_returns_errors_without_raising(country_dir, filename, change):
    mutate(country_dir, filename, change)
    errors = validation.validate_country_directory(country_dir)
    assert errors
    assert errors == sorted(set(errors))


@pytest.mark.parametrize("field", ["evidence_records", "pathways"])
def test_malformed_runtime_nested_content_returns_errors_without_raising(field):
    release = valid_release()
    release[field] = 5
    errors = validation.validate_runtime_release(release)
    assert errors
    assert errors == sorted(set(errors))


@pytest.mark.parametrize(("ledger", "id_field"), [
    ("evidence_records", "evidence_id"),
    ("pathways", "pathway_id"),
])
def test_malformed_runtime_ids_return_errors_without_raising(ledger, id_field):
    release = valid_release()
    release[ledger][0][id_field] = []
    errors = validation.validate_runtime_release(release)
    assert errors


@pytest.mark.parametrize(("ledger", "id_field", "expected"), [
    ("sources", "source_id", "duplicate source_id SSD-SRC-001"),
    ("evidence_records", "evidence_id", "duplicate evidence_id SSD-E-001"),
    ("pathways", "pathway_id", "duplicate pathway_id SSD-P-001"),
])
def test_runtime_cross_validation_rejects_duplicate_ledger_ids(
    ledger, id_field, expected
):
    release = valid_release()
    release[ledger].append(copy.deepcopy(release[ledger][0]))
    assert release[ledger][0][id_field] == release[ledger][-1][id_field]
    assert_error(validation.validate_runtime_release(release), expected)


def test_runtime_cross_validation_rejects_evidence_for_absent_country():
    release = valid_release()
    record = release["evidence_records"][0]
    record["iso3"] = "KEN"
    record["evidence_id"] = "KEN-E-001"
    release["countries"]["SSD"]["evidence_ids"].remove("SSD-E-001")
    assert_error(
        validation.validate_runtime_release(release),
        "KEN-E-001",
        "absent country KEN",
    )


def test_runtime_cross_validation_rejects_evidence_id_prefix_mismatch():
    release = valid_release()
    release["evidence_records"][0]["evidence_id"] = "KEN-E-001"
    release["countries"]["SSD"]["evidence_ids"][0] = "KEN-E-001"
    assert_error(
        validation.validate_runtime_release(release),
        "KEN-E-001",
        "prefix",
        "SSD",
    )


def test_runtime_cross_validation_rejects_unknown_source_reference():
    release = valid_release()
    release["evidence_records"][0]["source_refs"][0]["source_id"] = "SSD-SRC-999"
    assert_error(
        validation.validate_runtime_release(release),
        "SSD-E-001",
        "unknown source_id SSD-SRC-999",
    )


def test_runtime_cross_validation_rejects_pathway_for_absent_country():
    release = valid_release()
    pathway = release["pathways"][0]
    pathway["iso3"] = "KEN"
    pathway["pathway_id"] = "KEN-P-001"
    release["countries"]["SSD"]["pathway_ids"] = []
    assert_error(
        validation.validate_runtime_release(release),
        "KEN-P-001",
        "absent country KEN",
    )


def test_runtime_cross_validation_rejects_unknown_supporting_evidence():
    release = valid_release()
    release["pathways"][0]["supporting_evidence_ids"].append("SSD-E-999")
    assert_error(
        validation.validate_runtime_release(release),
        "SSD-P-001",
        "supporting_evidence_ids",
        "SSD-E-999",
    )


def test_runtime_cross_validation_rejects_unknown_link_evidence():
    release = valid_release()
    pathway = release["pathways"][0]
    pathway["supporting_evidence_ids"].append("SSD-E-999")
    pathway["link_evidence"]["pressure"].append("SSD-E-999")
    assert_error(
        validation.validate_runtime_release(release),
        "SSD-P-001",
        "link_evidence.pressure",
        "unknown SSD-E-999",
    )


def test_runtime_cross_validation_requires_links_in_supporting_ids():
    release = valid_release()
    release["pathways"][0]["supporting_evidence_ids"].remove("SSD-E-002")
    assert_error(
        validation.validate_runtime_release(release),
        "SSD-P-001",
        "link_evidence.pressure",
        "SSD-E-002",
        "supporting_evidence_ids",
    )


def test_runtime_cross_validation_rejects_pathway_id_prefix_mismatch():
    release = valid_release()
    release["pathways"][0]["pathway_id"] = "KEN-P-001"
    release["countries"]["SSD"]["pathway_ids"][0] = "KEN-P-001"
    assert_error(
        validation.validate_runtime_release(release),
        "KEN-P-001",
        "prefix",
        "SSD",
    )


@pytest.mark.parametrize(("field", "duplicate", "expected"), [
    ("evidence_ids", "SSD-E-001", "duplicate evidence_id SSD-E-001"),
    ("pathway_ids", "SSD-P-001", "duplicate pathway_id SSD-P-001"),
])
def test_runtime_cross_validation_rejects_duplicate_country_summary_ids(
    field, duplicate, expected
):
    release = valid_release()
    release["countries"]["SSD"][field].append(duplicate)
    assert_error(validation.validate_runtime_release(release), expected)


@pytest.mark.parametrize(("field", "extra"), [
    ("evidence_ids", "SSD-E-999"),
    ("pathway_ids", "SSD-P-999"),
])
def test_runtime_country_summary_ids_exactly_match_released_records(field, extra):
    release = valid_release()
    release["countries"]["SSD"][field].append(extra)
    assert_error(
        validation.validate_runtime_release(release),
        f"countries.SSD.{field}",
        "exactly match",
        extra,
    )


def test_runtime_cross_validation_allows_unreferenced_curated_source():
    release = valid_release()
    source = copy.deepcopy(release["sources"][0])
    source["source_id"] = "SSD-SRC-003"
    source["url"] = "https://example.org/unreferenced-curated-source"
    release["sources"].append(source)
    assert validation.validate_runtime_release(release) == []


@pytest.mark.parametrize(("filename", "field", "unsafe"), [
    ("sources.json", "repository_file", "C:private/source.txt"),
    ("review.json", "dossier_path", "C:private/dossier.md"),
])
def test_country_validation_rejects_drive_relative_paths(
    country_dir, filename, field, unsafe
):
    def change(value):
        target = value[0] if isinstance(value, list) else value
        target[field] = unsafe
        if field == "repository_file":
            target["checksum"] = "a" * 64

    mutate(country_dir, filename, change)
    assert_error(validation.validate_country_directory(country_dir), filename, field)


@pytest.mark.parametrize(("schema_name", "filename", "field", "unsafe"), [
    ("source.schema.json", "sources.json", "repository_file", "C:private/source.txt"),
    ("review.schema.json", "review.json", "dossier_path", "C:private/dossier.md"),
])
def test_schemas_reject_drive_relative_paths(
    schema_name, filename, field, unsafe
):
    value = read(FIXTURE_DIR / filename)
    target = value[0] if isinstance(value, list) else value
    target[field] = unsafe
    if field == "repository_file":
        target["checksum"] = "a" * 64
    assert_error(validation._schema_errors(value, schema_name, filename), field)


def test_runtime_schema_rejects_drive_relative_dossier_path():
    release = valid_release()
    release["countries"]["SSD"]["dossier_path"] = "C:private/dossier.md"
    assert_error(
        validation.validate_runtime_release(release),
        "dossier_path",
    )


def two_country_release():
    release = valid_release()
    ken_source = copy.deepcopy(release["sources"][0])
    ken_source["source_id"] = "KEN-SRC-001"
    ken_source["url"] = "https://example.org/ken-synthetic-source"
    ken_source["country_codes"] = ["KEN"]
    release["sources"].append(ken_source)

    ken_evidence = copy.deepcopy(release["evidence_records"][0])
    ken_evidence["evidence_id"] = "KEN-E-001"
    ken_evidence["iso3"] = "KEN"
    ken_evidence["source_refs"][0]["source_id"] = "KEN-SRC-001"
    release["evidence_records"].append(ken_evidence)
    release["countries"]["KEN"] = {
        "iso3": "KEN",
        "name": "Synthetic Kenya Pilot",
        "aliases": ["Synthetic KEN"],
        "status": "approved",
        "reviewer": "Human Reviewer",
        "reviewed_on": "2026-07-30",
        "review_due": "2027-07-30",
        "dossier_path": "countries/KEN/dossier.md",
        "evidence_ids": ["KEN-E-001"],
        "pathway_ids": [],
        "decision_notes": "Synthetic approval.",
    }
    return release


def test_two_country_runtime_fixture_is_valid():
    assert validation.validate_runtime_release(two_country_release()) == []


def test_runtime_pathway_supporting_evidence_must_match_pathway_iso3():
    release = two_country_release()
    release["pathways"][0]["supporting_evidence_ids"].append("KEN-E-001")
    assert_error(
        validation.validate_runtime_release(release),
        "pathway SSD-P-001",
        "supporting_evidence_ids",
        "KEN-E-001",
        "belongs to KEN, not SSD",
    )


def test_runtime_pathway_link_evidence_must_match_pathway_iso3():
    release = two_country_release()
    pathway = release["pathways"][0]
    pathway["supporting_evidence_ids"].append("KEN-E-001")
    pathway["link_evidence"]["pressure"].append("KEN-E-001")
    assert_error(
        validation.validate_runtime_release(release),
        "pathway SSD-P-001",
        "link_evidence.pressure",
        "KEN-E-001",
        "belongs to KEN, not SSD",
    )


def test_country_pathway_evidence_must_match_pathway_iso3(country_dir):
    def add_ken_source(records):
        source = copy.deepcopy(records[0])
        source["source_id"] = "KEN-SRC-001"
        source["url"] = "https://example.org/ken-country-source"
        source["country_codes"] = ["KEN"]
        records.append(source)

    def add_ken_evidence(records):
        record = copy.deepcopy(records[0])
        record["evidence_id"] = "KEN-E-001"
        record["iso3"] = "KEN"
        record["source_refs"][0]["source_id"] = "KEN-SRC-001"
        records.append(record)

    mutate(country_dir, "sources.json", add_ken_source)
    mutate(country_dir, "evidence.json", add_ken_evidence)
    mutate(
        country_dir,
        "pathways.json",
        lambda records: (
            records[0]["supporting_evidence_ids"].append("KEN-E-001"),
            records[0]["link_evidence"]["pressure"].append("KEN-E-001"),
        ),
    )
    mutate(
        country_dir,
        "review.json",
        lambda review: review["evidence_ids"].append("KEN-E-001"),
    )
    errors = validation.validate_country_directory(country_dir)
    assert_error(
        errors,
        "pathways.json",
        "SSD-P-001",
        "supporting_evidence_ids",
        "KEN-E-001",
        "belongs to KEN, not SSD",
    )
    assert_error(
        errors,
        "pathways.json",
        "SSD-P-001",
        "link_evidence.pressure",
        "KEN-E-001",
        "belongs to KEN, not SSD",
    )


def test_country_source_scope_and_declared_geography_match_evidence(country_dir):
    mutate(
        country_dir,
        "sources.json",
        lambda records: (
            records[0].__setitem__("source_id", "KEN-SRC-001"),
            records[0].__setitem__("country_codes", ["KEN"]),
        ),
    )
    mutate(
        country_dir,
        "evidence.json",
        lambda records: records[1]["source_refs"][0].__setitem__(
            "source_id", "KEN-SRC-001"
        ),
    )
    errors = validation.validate_country_directory(country_dir)
    assert_error(errors, "sources.json", "KEN-SRC-001", "prefix", "SSD")
    assert_error(
        errors,
        "evidence.json",
        "SSD-E-002",
        "KEN-SRC-001",
        "country_codes",
        "SSD",
    )


def test_runtime_source_scope_and_declared_geography_match_evidence():
    release = two_country_release()
    release["evidence_records"][0]["source_refs"][0]["source_id"] = "KEN-SRC-001"
    errors = validation.validate_runtime_release(release)
    assert_error(
        errors,
        "evidence SSD-E-001",
        "source_id KEN-SRC-001",
        "prefix",
        "SSD",
    )
    assert_error(
        errors,
        "evidence SSD-E-001",
        "source KEN-SRC-001",
        "country_codes",
        "SSD",
    )


def test_country_review_due_cannot_precede_reviewed_on(country_dir):
    def set_review_dates(review):
        review["status"] = "reviewed"
        review["reviewer"] = "Human Reviewer"
        review["reviewed_on"] = "2026-07-30"
        review["review_due"] = "2026-07-29"

    mutate(country_dir, "review.json", set_review_dates)
    assert_error(
        validation.validate_country_directory(country_dir),
        "review.json",
        "review_due 2026-07-29",
        "before reviewed_on 2026-07-30",
    )


def test_runtime_review_due_cannot_precede_reviewed_on():
    release = valid_release()
    release["countries"]["SSD"]["review_due"] = "2026-07-29"
    assert_error(
        validation.validate_runtime_release(release),
        "countries.SSD",
        "review_due 2026-07-29",
        "before reviewed_on 2026-07-30",
    )


def test_schema_validator_cache_reuses_immutable_schema_without_input_leakage():
    first = validation._validator("source.schema.json")
    second = validation._validator("source.schema.json")
    assert first is second
    with pytest.raises(TypeError):
        first.schema["title"] = "mutated"

    invalid = read(FIXTURE_DIR / "sources.json")
    invalid[0]["source_id"] = "bad"
    assert validation._schema_errors(
        invalid, "source.schema.json", "sources.json"
    )
    valid = read(FIXTURE_DIR / "sources.json")
    assert validation._schema_errors(
        valid, "source.schema.json", "sources.json"
    ) == []


def test_malformed_country_source_reference_returns_errors_without_raising(
    country_dir,
):
    mutate(
        country_dir,
        "evidence.json",
        lambda records: records[0]["source_refs"][0].__setitem__("source_id", []),
    )
    errors = validation.validate_country_directory(country_dir)
    assert errors
    assert errors == sorted(set(errors))


def test_malformed_runtime_source_reference_returns_errors_without_raising():
    release = valid_release()
    release["evidence_records"][0]["source_refs"][0]["source_id"] = []
    errors = validation.validate_runtime_release(release)
    assert errors
    assert errors == sorted(set(errors))

@pytest.mark.parametrize(
    ("publication_date", "basis"),
    [
        ("2025-04-30", "publication"),
        ("2025-04", "publication"),
        ("2025", "version"),
        (None, "not-stated"),
        ("2021-09-21", "submission"),
        ("2022-06-27", "portal-publication"),
        ("2021-12-24", "document-version"),
    ],
)
def test_source_publication_date_precision_and_basis_are_accepted(
    publication_date, basis
):
    sources = read(FIXTURE_DIR / "sources.json")
    for source in sources:
        source["publication_date_basis"] = "publication"
    sources[0]["publication_date"] = publication_date
    sources[0]["publication_date_basis"] = basis

    assert validation._schema_errors(
        sources, "source.schema.json", "sources.json"
    ) == []


@pytest.mark.parametrize(
    "publication_date",
    ["2025-1", "2025-00", "2025-13", "2025-04-1", "2025-02-29", "2025/04/01", ""],
)
def test_malformed_source_publication_date_precision_is_rejected(publication_date):
    sources = read(FIXTURE_DIR / "sources.json")
    for source in sources:
        source["publication_date_basis"] = "publication"
    sources[0]["publication_date"] = publication_date

    assert validation._schema_errors(
        sources, "source.schema.json", "sources.json"
    )


def test_source_publication_date_basis_is_required_and_enumerated():
    sources = read(FIXTURE_DIR / "sources.json")
    for source in sources:
        source["publication_date_basis"] = "publication"
    del sources[0]["publication_date_basis"]
    missing_errors = validation._schema_errors(
        sources, "source.schema.json", "sources.json"
    )
    sources[0]["publication_date_basis"] = "invented-date"
    invalid_errors = validation._schema_errors(
        sources, "source.schema.json", "sources.json"
    )

    assert missing_errors
    assert invalid_errors


@pytest.mark.parametrize(
    ("publication_date", "basis", "is_valid"),
    [
        (None, "not-stated", True),
        ("2025", "publication", True),
        (None, "publication", False),
        ("2025", "not-stated", False),
    ],
)
def test_source_publication_date_and_basis_are_cross_field_consistent(
    publication_date, basis, is_valid
):
    sources = read(FIXTURE_DIR / "sources.json")
    sources[0]["publication_date"] = publication_date
    sources[0]["publication_date_basis"] = basis

    errors = validation._schema_errors(
        sources, "source.schema.json", "sources.json"
    )
    assert (errors == []) is is_valid
