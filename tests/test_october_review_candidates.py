"""Bind the corrected review candidates to their pending approval packet."""

import hashlib
import json
from pathlib import Path

import pytest

from climate_bank.dossier import build_dossier
from climate_bank.release import promote_release
from climate_bank.validation import validate_country_directory


ROOT = Path(__file__).resolve().parents[1]
VERSION = "2026.10.26"
COUNTS = {"SSD": (27, 7), "BFA": (15, 5), "HTI": (15, 6),
          "PNG": (15, 6), "UKR": (16, 6), "YEM": (15, 5)}


@pytest.mark.parametrize("iso3", COUNTS)
def test_corrected_candidate_is_complete_and_cannot_be_promoted(iso3, tmp_path):
    country = ROOT / "countries" / iso3 / "candidates" / VERSION
    assert validate_country_directory(
        country, require_profile=True, schema_version="1.1.0"
    ) == []
    data = {name: json.loads((country / f"{name}.json").read_text(encoding="utf-8"))
            for name in ("evidence", "pathways", "profile", "review")}
    assert (len(data["evidence"]), len(data["pathways"])) == COUNTS[iso3]
    review = data["review"]
    assert review["status"] == "draft"
    assert review["reviewer"] is None and review["reviewed_on"] is None
    assert review["dossier_path"] == f"countries/{iso3}/candidates/{VERSION}/dossier.md"
    assert review["evidence_ids"] == [r["evidence_id"] for r in data["evidence"]]
    assert review["pathway_ids"] == [r["pathway_id"] for r in data["pathways"]]
    old = country.parent / "2026.08"
    old_review = json.loads((old / "review.json").read_text(encoding="utf-8"))
    assert review["review_due"] == old_review["review_due"]
    old_evidence = {r["evidence_id"]: r for r in json.loads(
        (old / "evidence.json").read_text(encoding="utf-8"))}
    for record in data["evidence"] + data["pathways"] + [data["profile"]]:
        assert record["review_status"] == "draft" and record["review_date"] is None
    for record in data["evidence"]:
        assert record["review_due"] == old_evidence[record["evidence_id"]]["review_due"]
    assert data["profile"]["profile_version"] == VERSION
    assert (country / "dossier.md").read_text(encoding="utf-8") == build_dossier(country)
    excluded = {"BFA-P-005", "YEM-E-009", "YEM-P-005"}
    for name in ("evidence", "pathways", "profile"):
        assert not any(record_id in json.dumps(data[name]) for record_id in excluded)
    with pytest.raises(ValueError, match="draft"):
        promote_release(
            [country], generated_at="2026-10-26T00:00:00Z",
            content_version=VERSION, current_dir=tmp_path / "current",
        )
    assert not (tmp_path / "current").exists()


def test_review_manifest_binds_candidates_and_preserved_artifacts():
    manifest = json.loads((ROOT / "reviews" /
        "20261026_six-country-candidate-manifest.json").read_text(encoding="utf-8"))
    assert manifest["candidate_version"] == VERSION
    assert manifest["hash_basis"] == "UTF-8 text with LF line endings"
    assert manifest["human_approval"] == "pending"
    assert manifest["excluded_ids"] == ["BFA-P-005", "YEM-E-009", "YEM-P-005"]
    assert len(manifest["candidate_files"]) == 36
    assert len(manifest["preserved_files"]) == 38
    for group in ("candidate_files", "preserved_files"):
        for relative_path, expected_hash in manifest[group].items():
            payload = (ROOT / relative_path).read_text(encoding="utf-8").encode("utf-8")
            assert hashlib.sha256(payload).hexdigest() == expected_hash
