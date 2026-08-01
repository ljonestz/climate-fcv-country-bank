"""Release-lock tests for the reviewed South Sudan pilot content package."""

from collections import Counter
import json
from pathlib import Path

from climate_bank.dossier import SECTION_HEADINGS
from climate_bank.release import build_release
from climate_bank.validation import (
    validate_country_directory,
    validate_runtime_release,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
COUNTRY_DIR = REPOSITORY_ROOT / "countries" / "SSD"
SOURCE_IDS = {f"SSD-SRC-{number:03d}" for number in range(1, 13)}
REVIEWER = "Lindsey Jones"
REVIEW_DATE = "2026-07-31"
REVIEW_DUE = "2027-07-31"
RUNTIME_PATH = REPOSITORY_ROOT / "releases" / "current" / "runtime.json"


def _load(filename: str):
    return json.loads((COUNTRY_DIR / filename).read_text(encoding="utf-8"))


def test_approved_ledgers_have_required_balance_and_provenance() -> None:
    evidence = _load("evidence.json")
    pathways = _load("pathways.json")
    review = _load("review.json")

    assert 16 <= len(evidence) <= 24
    assert 6 <= len(pathways) <= 7
    assert [record["evidence_id"] for record in evidence] == [
        f"SSD-E-{number:03d}" for number in range(1, len(evidence) + 1)
    ]
    assert [record["pathway_id"] for record in pathways] == [
        f"SSD-P-{number:03d}" for number in range(1, len(pathways) + 1)
    ]

    role_counts = Counter(record["analytical_role"] for record in evidence)
    assert role_counts["physical-baseline"] == 3
    assert role_counts["direct-climate-fcv"] == 7
    assert role_counts["vulnerability-capacity"] == 9

    referenced_sources = {
        ref["source_id"]
        for record in evidence
        for ref in record["source_refs"]
    }
    assert referenced_sources == SOURCE_IDS
    assert all(
        ref["source_id"] != "general-knowledge"
        and ref["locator"].strip()
        and any(
            marker in ref["locator"].lower()
            for marker in ("page", "p.", "section", "heading", "panel", "bullet")
        )
        for record in evidence
        for ref in record["source_refs"]
    )

    assert {record["evidence_status"] for record in evidence} == {
        "observed",
        "projected",
        "inferred",
    }
    assert all(record["review_status"] == "approved" for record in evidence)
    assert all(record["review_date"] == REVIEW_DATE for record in evidence)
    assert all(record["review_status"] == "approved" for record in pathways)
    assert all(record["review_date"] == REVIEW_DATE for record in pathways)

    assert review["status"] == "approved"
    assert review["reviewer"] == REVIEWER
    assert review["reviewed_on"] == REVIEW_DATE
    assert review["review_due"] == REVIEW_DUE
    assert review["evidence_ids"] == [
        record["evidence_id"] for record in evidence
    ]
    assert review["pathway_ids"] == [
        record["pathway_id"] for record in pathways
    ]
    assert "Lindsey Jones approved the South Sudan pilot" in review["decision_notes"]


def test_pathways_are_traceable_bidirectional_and_cautiously_rated() -> None:
    evidence = _load("evidence.json")
    pathways = _load("pathways.json")
    evidence_ids = {record["evidence_id"] for record in evidence}
    strength_counts = Counter(pathway["evidence_strength"] for pathway in pathways)
    directions = {pathway["interaction_direction"] for pathway in pathways}

    assert strength_counts["direct"] >= 2
    assert strength_counts["triangulated"] >= 2
    assert strength_counts["analytical-inference"] <= 2
    assert "climate-to-fcv" in directions
    assert "fcv-to-climate" in directions

    for pathway in pathways:
        supporting = set(pathway["supporting_evidence_ids"])
        assert supporting
        assert supporting <= evidence_ids
        assert pathway["alternative_explanations"]
        assert pathway["resilience_factors"]
        assert pathway["uncertainty"].strip()
        for link_name in ("pressure", "impact", "mediator", "consequence"):
            linked = pathway["link_evidence"][link_name]
            assert linked
            assert set(linked) <= supporting


def test_dossier_is_generated_complete_traceable_and_causally_cautious() -> None:
    evidence = _load("evidence.json")
    pathways = _load("pathways.json")
    dossier_path = COUNTRY_DIR / "dossier.md"

    assert dossier_path.is_file()
    dossier = dossier_path.read_text(encoding="utf-8")
    words = dossier.split()
    assert 3200 <= len(words) <= 4800
    assert dossier.startswith("# South Sudan Climate-FCV Evidence Dossier\n")
    assert [line for line in dossier.splitlines() if line.startswith("## ")] == list(
        SECTION_HEADINGS
    )
    for record in evidence:
        assert record["evidence_id"] in dossier
        assert record["statement"] in dossier
        for ref in record["source_refs"]:
            assert ref["source_id"] in dossier
            assert ref["locator"] in dossier
    for pathway in pathways:
        assert pathway["pathway_id"] in dossier
        assert dossier.count(f"Pathway ID: {pathway['pathway_id']} |") == 1
    for source_id in sorted(SOURCE_IDS):
        assert source_id in dossier

    serialized = json.dumps(
        {"evidence": evidence, "pathways": pathways},
        ensure_ascii=False,
    ).lower()
    combined = f"{serialized}\n{dossier.lower()}"
    assert "general-knowledge" not in combined
    assert "as an ai" not in combined
    assert "language model" not in combined
    assert "climate change causes conflict" not in combined
    assert "climate causes conflict" not in combined
    assert not list(COUNTRY_DIR.rglob("*.pdf"))


def test_reviewed_statuses_and_pathway_strength_match_source_basis() -> None:
    evidence = _load("evidence.json")
    pathways = _load("pathways.json")
    evidence_by_id = {record["evidence_id"]: record for record in evidence}
    pathway_by_id = {record["pathway_id"]: record for record in pathways}

    forecasting = evidence_by_id["SSD-E-019"]
    assert forecasting["evidence_status"] == "observed"
    assert forecasting["scenario"] is None

    ccd_risk = evidence_by_id["SSD-E-003"]
    assert ccd_risk["evidence_status"] == "projected"
    assert "sorghum yields by 2050" in ccd_risk["statement"]
    assert ccd_risk["hazard_tags"] == ["extreme-heat"]
    assert ccd_risk["impact_tags"] == ["crop-yield-risk"]
    recommendation_terms = (
        "priorities include",
        "early warning",
        "preparedness",
        "resilient agriculture",
        "rehabilitation",
    )
    assert not any(
        term in f"{ccd_risk['statement']} {ccd_risk['compact_statement']}".lower()
        for term in recommendation_terms
    )

    mobility = pathway_by_id["SSD-P-002"]
    supporting = [evidence_by_id[item] for item in mobility["supporting_evidence_ids"]]
    assert mobility["evidence_strength"] == "triangulated"
    assert any(record["evidence_status"] == "inferred" for record in supporting)


def test_south_sudan_approved_package_passes_repository_validation() -> None:
    assert validate_country_directory(COUNTRY_DIR) == []


def test_current_runtime_release_matches_the_approved_south_sudan_ledgers() -> None:
    assert RUNTIME_PATH.is_file()
    release = json.loads(RUNTIME_PATH.read_text(encoding="utf-8"))

    assert validate_runtime_release(release) == []
    assert release == build_release(
        [COUNTRY_DIR], generated_at=release["generated_at"]
    )
    assert release["countries"]["SSD"]["status"] == "approved"
    assert release["countries"]["SSD"]["reviewer"] == REVIEWER
    assert len(release["sources"]) == 12
    assert len(release["evidence_records"]) == 19
    assert len(release["pathways"]) == 7

def test_quality_review_removes_duplicate_syntheses_and_preserves_traceability() -> None:
    evidence = _load("evidence.json")
    pathways = _load("pathways.json")
    evidence_by_id = {record["evidence_id"]: record for record in evidence}
    pathway_by_id = {record["pathway_id"]: record for record in pathways}

    assert list(evidence_by_id) == [
        f"SSD-E-{number:03d}" for number in range(1, 20)
    ]
    assert {"SSD-E-020", "SSD-E-021"}.isdisjoint(evidence_by_id)
    assert evidence_by_id["SSD-E-016"]["compact_statement"] == (
        "Screen whether conflict and institutional weakness are constraining "
        "climate adaptation capacity."
    )

    p001 = pathway_by_id["SSD-P-001"]
    assert "SSD-E-018" in p001["supporting_evidence_ids"]
    assert "SSD-E-018" not in p001["link_evidence"]["consequence"]

    assert "SSD-E-021" not in pathway_by_id["SSD-P-003"]["supporting_evidence_ids"]
    assert "SSD-E-020" not in pathway_by_id["SSD-P-005"]["supporting_evidence_ids"]

    for pathway in pathways:
        if pathway["evidence_strength"] != "triangulated":
            continue
        unique_source_ids = {
            source_ref["source_id"]
            for evidence_id in pathway["supporting_evidence_ids"]
            for source_ref in evidence_by_id[evidence_id]["source_refs"]
        }
        assert len(unique_source_ids) >= 2, pathway["pathway_id"]

CANDIDATE_DIR = COUNTRY_DIR / "candidates" / "2026.08"
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
PRIORITY_DOMAINS = (
    "CMIP6 temperature, precipitation, variability, and extreme-event projections",
    "Flood persistence, hydrology, and geographic exposure",
    "Drought, dry spells, rainfall variability, and dry-season water stress",
    "Agriculture, livestock, fisheries, forests, and the Sudd wetland system",
    "Roads, markets, water systems, health, education, and humanitarian access",
    "Displacement, return, land access, high-ground use, and host-community pressure",
    "Differentiated gender, age, disability, displacement, and livelihood vulnerability",
    "Household, community, and customary coping systems",
    "Formal and informal institutional mandates, delivery capacity, and coordination",
    "Early warning, climate services, disaster response, and anticipatory action",
    "Evaluated response effectiveness, delivery failure, and unintended effects",
    "Climate-to-FCV, bidirectional, and FCV-to-climate pathways",
)
PROTECTED_HASHES = {
    "countries/SSD/sources.json": "1ada9604c1eb68eefd77a22707592906cf605ab7bb21b4498c7484e4273b5f57",
    "countries/SSD/evidence.json": "953ab85a365881a3dc896d54a8243b6a5329c123a3a37f90bc4ff22f8f44b191",
    "countries/SSD/pathways.json": "31d46515ce2e1486335106cdd3c716586497b2137ae32f2be67a17f67d974ad0",
    "countries/SSD/review.json": "00c4e6efdfb4f5d8723f31548c3adc1013afc1717a8657bc0e0456d0935e8d0b",
    "releases/current/runtime.json": "59cf3dfa3450b1727c6b1897b2a77841adc2cb522816e2abe696ae3ed2fb252e",
}
MIGRATION_FIELDS = {
    "evidence_class",
    "administrative_level",
    "ecological_level",
    "refresh_tier",
    "review_due",
}


def _load_candidate(filename: str):
    return json.loads((CANDIDATE_DIR / filename).read_text(encoding="utf-8"))


def test_candidate_declares_every_evidence_class_and_priority_domain() -> None:
    profile = _load_candidate("profile.json")
    rows = {(row["dimension"], row["value"]): row for row in profile["coverage"]}

    assert len(rows) == len(profile["coverage"])
    assert {
        value for dimension, value in rows if dimension == "evidence_class"
    } == EVIDENCE_CLASSES
    assert tuple(
        row["value"]
        for row in profile["coverage"]
        if row["dimension"] == "priority_domain"
    ) == PRIORITY_DOMAINS


def test_candidate_coverage_is_honest_and_resolves_records() -> None:
    profile = _load_candidate("profile.json")
    evidence_ids = {
        record["evidence_id"] for record in _load_candidate("evidence.json")
    }
    pathway_ids = {
        record["pathway_id"] for record in _load_candidate("pathways.json")
    }
    known_ids = evidence_ids | pathway_ids

    for row in profile["coverage"]:
        if row["status"] in {"covered", "partial"}:
            assert row["record_ids"], row
            assert set(row["record_ids"]) <= known_ids, row
        else:
            assert row["status"] == "gap", row
            assert not row["record_ids"], row
            assert row["gap_note"] and row["gap_note"].strip(), row

    rendered = json.dumps(profile, ensure_ascii=False).casefold()
    assert "comprehensive national coverage" not in rendered


def test_candidate_preserves_canonical_ledgers_and_record_approval_provenance() -> None:
    canonical_sources = _load("sources.json")
    canonical_evidence = _load("evidence.json")
    canonical_pathways = _load("pathways.json")
    canonical_review = _load("review.json")
    candidate_sources = _load_candidate("sources.json")
    candidate_evidence = _load_candidate("evidence.json")
    candidate_pathways = _load_candidate("pathways.json")
    candidate_review = _load_candidate("review.json")

    assert candidate_sources == canonical_sources
    assert candidate_pathways == canonical_pathways
    assert [row["evidence_id"] for row in candidate_evidence] == [
        row["evidence_id"] for row in canonical_evidence
    ]
    candidate_legacy_shape = [
        {key: value for key, value in row.items() if key not in MIGRATION_FIELDS}
        for row in candidate_evidence
    ]
    assert candidate_legacy_shape == canonical_evidence
    assert all(row["review_status"] == "approved" for row in candidate_evidence)
    assert all(row["review_status"] == "approved" for row in candidate_pathways)

    assert candidate_review == {
        **canonical_review,
        "status": "reviewed",
        "review_due": None,
        "dossier_path": "countries/SSD/candidates/2026.08/dossier.md",
        "decision_notes": (
            "Candidate migration retains the approved provenance and review status "
            "of unchanged evidence and pathway records. The schema 1.1 metadata, "
            "coverage profile, and future dossier remain subject to human review; "
            "this reviewed candidate is not approved for production promotion."
        ),
    }


def test_candidate_evidence_metadata_is_specific_and_schema_1_1_valid() -> None:
    evidence = _load_candidate("evidence.json")
    evidence_by_id = {record["evidence_id"]: record for record in evidence}

    assert validate_country_directory(
        CANDIDATE_DIR,
        require_profile=True,
        schema_version="1.1.0",
    ) == []
    assert {record["evidence_class"] for record in evidence} == (
        EVIDENCE_CLASSES - {"adaptive-capacity"}
    )
    assert evidence_by_id["SSD-E-012"]["evidence_class"] == (
        "institutional-capacity"
    )
    assert all(record["review_due"] >= record["review_date"] for record in evidence)
    assert evidence_by_id["SSD-E-003"]["scenario"] == (
        "CCDR hotter-climate projection through 2050"
    )
    assert evidence_by_id["SSD-E-003"]["time_horizons"] == [
        "medium-term",
        "long-term",
    ]
    assert evidence_by_id["SSD-E-002"]["ecological_level"] == (
        "White Nile tributary floodplains"
    )
    assert evidence_by_id["SSD-E-005"]["administrative_level"] == "payam"
    assert evidence_by_id["SSD-E-006"]["administrative_level"] == "boma"
    assert evidence_by_id["SSD-E-010"]["administrative_level"] == "county"
    assert evidence_by_id["SSD-E-018"]["evidence_class"] == "response-performance"
    assert evidence_by_id["SSD-E-019"]["evidence_class"] == (
        "resilience-peace-capacity"
    )


def test_candidate_profile_links_and_aliases_are_internally_consistent() -> None:
    profile = _load_candidate("profile.json")
    evidence_ids = {
        record["evidence_id"] for record in _load_candidate("evidence.json")
    }
    pathway_ids = {
        record["pathway_id"] for record in _load_candidate("pathways.json")
    }

    for section in (
        "executive_assessment",
        "geographic_notes",
        "sector_notes",
        "known_gaps",
    ):
        for row in profile[section]:
            assert row["evidence_ids"] or row["pathway_ids"], (section, row)
            assert set(row["evidence_ids"]) <= evidence_ids
            assert set(row["pathway_ids"]) <= pathway_ids

    for category, alias_map in profile["selection_aliases"].items():
        normalized_keys = {key.casefold() for key in alias_map}
        assert len(normalized_keys) == len(alias_map), category
        normalized_aliases = [
            alias.casefold()
            for aliases in alias_map.values()
            for alias in aliases
        ]
        assert len(normalized_aliases) == len(set(normalized_aliases)), category
        assert normalized_keys.isdisjoint(normalized_aliases), category


def test_candidate_review_state_is_reviewed_not_approved() -> None:
    profile = _load_candidate("profile.json")
    review = _load_candidate("review.json")

    assert profile["review_status"] == "reviewed"
    assert profile["review_date"] == "2026-08-01"
    assert review["status"] == "reviewed"
    assert review["status"] != "approved"


def test_canonical_country_and_current_runtime_remain_byte_locked() -> None:
    import hashlib

    for relative_path, expected_hash in PROTECTED_HASHES.items():
        actual_hash = hashlib.sha256(
            (REPOSITORY_ROOT / relative_path).read_bytes()
        ).hexdigest()
        assert actual_hash == expected_hash, relative_path


def test_candidate_keeps_adaptive_capacity_and_cmip6_projection_gaps_explicit() -> None:
    profile = _load_candidate("profile.json")
    coverage = {
        (row["dimension"], row["value"]): row for row in profile["coverage"]
    }

    adaptive = coverage[("evidence_class", "adaptive-capacity")]
    assert adaptive["status"] == "gap"
    assert adaptive["record_ids"] == []
    assert "planned priorities" in adaptive["gap_note"].casefold()
    assert "adaptive capacity" in adaptive["gap_note"].casefold()

    cmip6 = coverage[
        (
            "priority_domain",
            "CMIP6 temperature, precipitation, variability, and extreme-event projections",
        )
    ]
    assert cmip6["status"] == "gap"
    assert cmip6["record_ids"] == []
    assert "cmip6" in cmip6["gap_note"].casefold()
    assert {"SSD-E-001", "SSD-E-002", "SSD-E-003"}.isdisjoint(
        cmip6["record_ids"]
    )
