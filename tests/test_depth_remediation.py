"""Reproducible remediation preserves draft review state and source snapshots."""

import hashlib
import json
import shutil
from copy import deepcopy
from pathlib import Path

import pytest

from climate_bank.validation import validate_country_directory
from scripts.remediate_depth_candidates import (
    _compare_published_files, remediate_country,
)


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "countries/BFA/candidates/2026.10.26.deep"
VERSION = "2026.10.27.remediated"
UNVERIFIED_SUFFIX = (
    "Not independently reverified in the 27 October 2026 remediation; "
    "check the cited passage before relying on this claim."
)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def test_published_outputs_must_match_rebuilt_hashes(tmp_path):
    staged, published = tmp_path / "staged.json", tmp_path / "published.json"
    staged.write_text('{"same":true}\n', encoding="utf-8")
    published.write_text('{"same":true}\n', encoding="utf-8")
    _compare_published_files({"candidate.json": (staged, published)})

    published.write_text('{"same":false}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="mismatched=.*candidate.json"):
        _compare_published_files({"candidate.json": (staged, published)})


def test_country_remediation_is_draft_only_reproducible_and_keeps_prior_files(tmp_path):
    source_hashes = {name: file_hash(BASE / name) for name in BASE.iterdir() if name.is_file()}
    original_review = read_json(BASE / "review.json")
    original_evidence = read_json(BASE / "evidence.json")
    target = tmp_path / "BFA" / "candidates" / VERSION
    patch = {
        "evidence_updates": {
            "BFA-E-001": {
                "statement": "The source reports the full, carefully scoped claim.",
                "compact_statement": "Short but stale summary.",
            },
            "BFA-E-102": {
                "statement": "The revised outlook wording keeps the claim's source context visible."
            },
        },
        "add_evidence": [],
        "add_gaps": [
            "This draft does not establish a national causal estimate.",
            "The bank contains no completed mediated climate-FCV pathway; this is an evidence gap, not evidence of absence.",
        ],
        "decisions": [
            {
                "record_ids": ["BFA-E-001", "BFA-E-102"],
                "reason": "Keep full wording, projection context and source limits visible.",
                "source_url": "https://example.org/source",
                "locator": "specified section",
                "verification_method": "read full text",
                "accessed_on": "2026-10-27",
            }
        ],
    }
    added_evidence = deepcopy(next(row for row in original_evidence
                                   if row["evidence_id"] == "BFA-E-001"))
    added_evidence.update({
        "evidence_id": "BFA-E-999",
        "review_due": next(row["review_due"] for row in original_evidence
                            if row["evidence_id"] == "BFA-E-001"),
        "statement": "A synthetic added claim exercises coverage synchronization.",
        "compact_statement": "A synthetic added claim exercises coverage synchronization.",
    })
    patch["add_evidence"].append(added_evidence)
    audit = {
        "iso3": "BFA",
        "disposition": "unresolved-limited",
        "human_approval": "pending",
        "evidence": [
            {"record_id": row["evidence_id"], "claim_verification": "unresolved"}
            for row in original_evidence
        ],
        "pathways": [
            {"record_id": row["pathway_id"], "claim_verification": "unresolved"}
            for row in read_json(BASE / "pathways.json")
        ],
    }
    rules = {
        "apply_full_statement_to_compact": True,
        "append_projected_scenario": True,
        "unverified_uncertainty_suffix": UNVERIFIED_SUFFIX,
        "verified_record_ids": ["BFA-E-102", "TCD-E-101"],
    }

    result = remediate_country(
        BASE, target, iso3="BFA", version=VERSION, patch=patch, audit=audit, rules=rules
    )

    evidence = read_json(target / "evidence.json")
    by_id = {row["evidence_id"]: row for row in evidence}
    assert by_id["BFA-E-001"]["compact_statement"] == by_id["BFA-E-001"]["statement"]
    assert UNVERIFIED_SUFFIX in by_id["BFA-E-001"]["uncertainty"]
    assert "Scenario:" in by_id["BFA-E-102"]["compact_statement"]
    assert by_id["BFA-E-001"]["review_due"] == next(
        row["review_due"] for row in original_evidence if row["evidence_id"] == "BFA-E-001"
    )
    assert UNVERIFIED_SUFFIX in by_id["BFA-E-999"]["uncertainty"]
    assert "Not independently reverified" not in by_id["BFA-E-102"]["uncertainty"]
    review = read_json(target / "review.json")
    assert review["status"] == "draft"
    assert review["reviewer"] is None and review["reviewed_on"] is None
    assert review["review_due"] == original_review["review_due"]
    assert review["evidence_ids"] == [row["evidence_id"] for row in evidence]
    profile = read_json(target / "profile.json")
    assert any(gap["text"] == patch["add_gaps"][0] for gap in profile["known_gaps"])
    assert not any("no completed mediated climate-FCV pathway" in gap["text"]
                    for gap in profile["known_gaps"])
    climate_coverage = next(row for row in profile["coverage"]
                            if row["dimension"] == "evidence-class"
                            and row["value"] == "climate-pressure")
    assert "BFA-E-999" in climate_coverage["record_ids"]
    assert "The revised outlook wording" in next(
        row["text"] for row in profile["geographic_notes"]
        if row["evidence_ids"] == ["BFA-E-102"]
    )
    audit_gap = next(gap for gap in profile["known_gaps"] if "machine-screening" in gap["text"])
    assert "not independent source verification" in audit_gap["text"]
    assert "BFA-E-001" in audit_gap["evidence_ids"]
    assert "BFA-P-001" in audit_gap["pathway_ids"]
    assert not validate_country_directory(target, require_profile=True, schema_version="1.1.0")
    assert (target / "dossier.md").read_text(encoding="utf-8")
    assert result["audit_disposition"] == "unresolved-limited"
    assert result["candidate_file_hashes"]["evidence.json"] == file_hash(target / "evidence.json")
    assert "BFA-E-001" in result["applied_transformations"]["uncertainty_qualified"]
    assert "BFA-E-102" not in result["applied_transformations"]["uncertainty_qualified"]
    assert result["applied_transformations"]["stale_pathway_gap_removed"] is True
    assert "BFA-E-102" in result["applied_transformations"]["geographic_notes_synchronized"]
    assert result["applied_transformations"]["verified_record_ids"] == ["BFA-E-102"]
    assert source_hashes == {name: file_hash(BASE / name) for name in source_hashes}

    second = tmp_path / "second" / "BFA" / "candidates" / VERSION
    second_base = tmp_path / "second_base"
    shutil.copytree(BASE, second_base)
    second_result = remediate_country(
        second_base, second, iso3="BFA", version=VERSION, patch=patch, audit=audit,
        rules=rules,
    )
    assert second_result["candidate_file_hashes"] == result["candidate_file_hashes"]
    assert (second / "dossier.md").read_bytes() == (target / "dossier.md").read_bytes()
