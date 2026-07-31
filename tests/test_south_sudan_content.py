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
