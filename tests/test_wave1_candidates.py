"""Shared content contract for FY2027 Public FCV Wave 1 candidates."""

from collections import Counter
import json
from pathlib import Path

import pytest

from climate_bank.validation import validate_country_directory


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
VERSION = "2026.08"
REVIEWED_ON = "2026-08-10"
REVIEW_DUE = "2026-09-10"
REVIEWER = "Codex evidence pass; Lindsey Jones approval pending"
EVIDENCE_CLASSES = {
    "climate-pressure",
    "exposure",
    "sensitivity",
    "coping-capacity",
    "adaptive-capacity",
    "institutional-capacity",
    "response-performance",
    "direct-climate-fcv",
    "resilience-peace-capacity",
}
COUNTRIES = {
    "BFA": {
        "name": "Burkina Faso",
        "aliases": [],
    },
}


def _candidate_dir(iso3: str) -> Path:
    return REPOSITORY_ROOT / "countries" / iso3 / "candidates" / VERSION


def _load(country_dir: Path, filename: str):
    return json.loads((country_dir / filename).read_text(encoding="utf-8"))


@pytest.mark.parametrize("iso3", sorted(COUNTRIES))
def test_wave1_candidate_is_reviewable_not_approved(iso3: str) -> None:
    metadata = COUNTRIES[iso3]
    country_dir = _candidate_dir(iso3)
    required = {
        "sources.json",
        "evidence.json",
        "pathways.json",
        "profile.json",
        "review.json",
        "dossier.md",
    }
    assert country_dir.is_dir(), country_dir
    assert required <= {path.name for path in country_dir.iterdir()}
    assert validate_country_directory(
        country_dir,
        require_profile=True,
        schema_version="1.1.0",
    ) == []

    sources = _load(country_dir, "sources.json")
    evidence = _load(country_dir, "evidence.json")
    pathways = _load(country_dir, "pathways.json")
    profile = _load(country_dir, "profile.json")
    review = _load(country_dir, "review.json")

    assert 10 <= len(sources) <= 18
    assert 15 <= len(evidence) <= 30
    assert 6 <= len(pathways) <= 10
    assert [row["source_id"] for row in sources] == [
        f"{iso3}-SRC-{number:03d}"
        for number in range(1, len(sources) + 1)
    ]
    assert [row["evidence_id"] for row in evidence] == [
        f"{iso3}-E-{number:03d}"
        for number in range(1, len(evidence) + 1)
    ]
    assert [row["pathway_id"] for row in pathways] == [
        f"{iso3}-P-{number:03d}"
        for number in range(1, len(pathways) + 1)
    ]

    roles = Counter(row["analytical_role"] for row in evidence)
    assert set(roles) <= {
        "direct-climate-fcv",
        "vulnerability-capacity",
        "physical-baseline",
    }
    assert roles["vulnerability-capacity"]
    assert roles["physical-baseline"]
    assert roles["direct-climate-fcv"] + roles["vulnerability-capacity"] >= (
        3 * roles["physical-baseline"]
    )
    assert {row["evidence_class"] for row in evidence} <= EVIDENCE_CLASSES

    source_ids = {row["source_id"] for row in sources}
    assert all(iso3 in row["country_codes"] for row in sources)
    assert all(row["url"].startswith("https://") for row in sources)
    assert all(row["repository_file"] is None for row in sources)
    assert all(row["checksum"] is None for row in sources)
    assert all(
        ref["source_id"] in source_ids and ref["locator"].strip()
        for row in evidence
        for ref in row["source_refs"]
    )

    directions = {row["interaction_direction"] for row in pathways}
    assert directions & {"climate-to-fcv", "bidirectional"}
    assert all(row["review_status"] == "reviewed" for row in evidence)
    assert all(row["review_date"] == REVIEWED_ON for row in evidence)
    assert all(row["review_status"] == "reviewed" for row in pathways)
    assert all(row["review_date"] == REVIEWED_ON for row in pathways)

    coverage = {
        (row["dimension"], row["value"]): row
        for row in profile["coverage"]
    }
    assert len(coverage) == len(profile["coverage"])
    assert {
        value for dimension, value in coverage
        if dimension == "evidence_class"
    } == EVIDENCE_CLASSES
    assert profile["iso3"] == iso3
    assert profile["profile_version"] == VERSION
    assert profile["review_status"] == "reviewed"
    assert profile["review_date"] == REVIEWED_ON
    assert profile["known_gaps"]
    if not directions & {"fcv-to-climate", "bidirectional"}:
        gaps = " ".join(row["text"] for row in profile["known_gaps"]).casefold()
        assert "fcv-to-climate" in gaps or "reverse pathway" in gaps

    assert review["iso3"] == iso3
    assert review["country_name"] == metadata["name"]
    assert review["country_aliases"] == metadata["aliases"]
    assert review["status"] == "reviewed"
    assert review["reviewer"] == REVIEWER
    assert review["reviewed_on"] == REVIEWED_ON
    assert review["review_due"] == REVIEW_DUE
    assert review["dossier_path"] == (
        f"countries/{iso3}/candidates/{VERSION}/dossier.md"
    )
    assert "not approved for production" in review["decision_notes"].casefold()
    assert review["evidence_ids"] == [row["evidence_id"] for row in evidence]
    assert review["pathway_ids"] == [row["pathway_id"] for row in pathways]
