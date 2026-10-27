"""Contract tests for the qualified 146-country activation."""

from copy import deepcopy
from datetime import date
import json
from pathlib import Path

import pytest
import scripts.activate_global_release as activation
from climate_bank.dossier import build_dossier
from climate_bank.validation import validate_country_directory
from scripts.activate_global_release import (
    APPROVAL_MANIFEST,
    APPROVED_ON,
    APPROVED_VERSION,
    CONTENT_VERSION,
    CURRENT,
    build_activation,
    prepare_approved_country,
)


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_VERSION = "2026.10.27.remediated"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_approved_copy_preserves_claims_and_deadlines_with_only_qualified_metadata(
    tmp_path: Path,
) -> None:
    iso3 = "AFG"
    candidate = ROOT / "countries" / iso3 / "candidates" / CANDIDATE_VERSION
    approved = tmp_path / "countries" / iso3 / "approved" / APPROVED_VERSION
    before = {
        name: read_json(candidate / name)
        for name in ("sources.json", "evidence.json", "pathways.json", "profile.json", "review.json")
    }

    transformation = prepare_approved_country(candidate, approved, iso3=iso3)

    after = {
        name: read_json(approved / name)
        for name in ("sources.json", "evidence.json", "pathways.json", "profile.json", "review.json")
    }
    assert after["sources.json"] == before["sources.json"]
    for filename, id_field in (("evidence.json", "evidence_id"), ("pathways.json", "pathway_id")):
        expected = deepcopy(before[filename])
        for record in expected:
            record.update(review_status="approved", review_date=APPROVED_ON)
        assert after[filename] == expected
        assert {r[id_field]: r.get("review_due") for r in after[filename]} == {
            r[id_field]: r.get("review_due") for r in before[filename]
        }

    expected_profile = deepcopy(before["profile.json"])
    first_old = "Automated machine-screening is not independent source verification or human approval."
    first_new = (
        "Automated machine-screening is not independent source verification. "
        "Routine/default app-use approval does not certify claims or sources."
    )
    second_old = "Draft extension: human source review and approval remain pending."
    second_new = (
        "Routine/default app-use approval granted by Lindsey Jones on 2026-10-27; "
        "independent source verification remains incomplete."
    )
    first_rows = [row for row in expected_profile["known_gaps"] if row["text"].startswith(first_old)]
    second_rows = [row for row in expected_profile["known_gaps"] if row["text"].startswith(second_old)]
    assert len(first_rows) == len(second_rows) == 1
    first_rows[0]["text"] = first_new + first_rows[0]["text"][len(first_old):]
    second_rows[0]["text"] = second_new + second_rows[0]["text"][len(second_old):]
    expected_profile.update(review_status="approved", review_date=APPROVED_ON)
    assert after["profile.json"] == expected_profile

    structural = [r["review_due"] for r in before["evidence.json"] if r["refresh_tier"] == "structural"]
    assert structural
    assert after["review.json"]["review_due"] == min(structural)
    expected_review = deepcopy(before["review.json"])
    expected_review.update(
        status="approved",
        reviewer="Lindsey Jones",
        reviewed_on=APPROVED_ON,
        review_due=min(structural),
        dossier_path=f"countries/{iso3}/approved/{APPROVED_VERSION}/dossier.md",
    )
    assert all(after["review.json"][key] == value for key, value in expected_review.items() if key != "decision_notes")
    assert "qualified routine/default Climate-FCV application use" in after["review.json"]["decision_notes"]
    assert after["review.json"]["decision_notes"].startswith(before["review.json"]["decision_notes"])
    assert transformation["profile_notice_transformations"]
    assert transformation["country_review_due"] == min(structural)
    assert (approved / "dossier.md").read_text(encoding="utf-8") == build_dossier(approved)
    assert validate_country_directory(approved, require_profile=True, schema_version="1.1.0", as_of=date.fromisoformat(APPROVED_ON)) == []


def test_published_activation_check_rebuilds_runtime_identity_and_scope() -> None:
    manifest_path = ROOT / APPROVAL_MANIFEST
    assert manifest_path.is_file(), "approved activation manifest is missing"

    manifest = build_activation(check=True)
    assert manifest_path.read_text(encoding="utf-8") == json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    runtime = read_json(ROOT / CURRENT)
    assert manifest["reviewer"] == "Lindsey Jones"
    assert manifest["approved_on"] == APPROVED_ON
    assert "qualified routine/default Climate-FCV application use" in manifest["approval_scope"]
    assert "not independent source certification" in manifest["approval_scope"]
    assert runtime["content_version"] == CONTENT_VERSION
    assert runtime["schema_version"] == "1.1.0"
    assert runtime["candidate"] is False
    assert manifest["counts"] == {
        "countries": 146,
        "sources": 1045,
        "evidence": 2643,
        "pathways": 241,
    }
    assert len(manifest["candidate_files"]) == 146 * 6
    assert len(manifest["approved_files"]) == 146 * 6
    assert set(runtime["country_profiles"]) == set(runtime["countries"])
    assert len(runtime["countries"]) == 146

    for iso3 in sorted(runtime["countries"]):
        approved = ROOT / "countries" / iso3 / "approved" / APPROVED_VERSION
        profile = read_json(approved / "profile.json")
        assert runtime["country_profiles"][iso3] == {
            "coverage": profile["coverage"],
            "known_gaps": profile["known_gaps"],
        }
        assert any(
            row["text"].startswith(
                "Routine/default app-use approval granted by Lindsey Jones on 2026-10-27; "
                "independent source verification remains incomplete."
            )
            for row in profile["known_gaps"]
        ), iso3


def test_install_outputs_preflights_later_conflict_before_writing_earlier_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    stage = tmp_path / "stage"
    monkeypatch.setattr(activation, "ROOT", repository)

    (stage / "first.txt").parent.mkdir(parents=True)
    (stage / "first.txt").write_text("new first", encoding="utf-8")
    (stage / "later.txt").write_text("new later", encoding="utf-8")
    (repository / "later.txt").parent.mkdir(parents=True)
    (repository / "later.txt").write_text("existing later", encoding="utf-8")

    with pytest.raises(ValueError, match="Existing immutable output differs: later.txt"):
        activation._install_outputs(stage, ["first.txt", "later.txt"], check=False)

    assert not (repository / "first.txt").exists()
    assert (repository / "later.txt").read_text(encoding="utf-8") == "existing later"
