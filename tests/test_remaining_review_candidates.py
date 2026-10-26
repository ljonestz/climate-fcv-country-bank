"""Check the remaining-country review decisions against their actual artifacts."""

import hashlib
import json
from pathlib import Path
import re

import pytest

from climate_bank.dossier import build_dossier
from climate_bank.release import promote_release
from climate_bank.validation import validate_country_directory


ROOT = Path(__file__).resolve().parents[1]
COUNTRIES = ("AFG", "CAF", "CMR", "COD", "ETH", "IRN", "IRQ", "LBN", "LBY",
             "MLI", "MMR", "MOZ", "NER", "NGA", "PSE", "SDN", "SOM", "SYR")
VERSION = "2026.10.26"


def read_json(path):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            assert key not in result, (str(path), "duplicate JSON key", key)
            result[key] = value
        return result

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)


@pytest.mark.parametrize("iso3", COUNTRIES)
def test_country_review_matches_the_corrected_draft(iso3, tmp_path):
    original = ROOT / "countries" / iso3 / "candidates" / "2026.08"
    candidate = original.parent / VERSION
    review_text = (ROOT / "reviews" /
                   f"20261026_source-review-{iso3}.md").read_text(encoding="utf-8")
    assert not re.search(r"turn\d+(?:view|search|fetch)\d+", review_text), iso3
    rows = re.findall(
        r"^\|\s*`?([A-Z]{3}-[EP]-\d{3})`?\s*\|\s*`?(RETAIN|REVISE|DEFER)`?\s*\|",
        review_text, re.M,
    )
    decisions = dict(rows)
    assert len(rows) == len(decisions)
    old_records = {}
    new_records = {}
    for filename, key in (("evidence.json", "evidence_id"),
                          ("pathways.json", "pathway_id")):
        old_records.update({r[key]: r for r in read_json(original / filename)})
        new_records.update({r[key]: r for r in read_json(candidate / filename)})
    assert set(decisions) == set(old_records)
    assert set(new_records) == {rid for rid, d in decisions.items() if d != "DEFER"}
    for rid, record in new_records.items():
        ignored = {"review_status", "review_date"}
        changed = ({k: v for k, v in record.items() if k not in ignored}
                   != {k: v for k, v in old_records[rid].items() if k not in ignored})
        assert changed == (decisions[rid] == "REVISE"), rid
        assert record["review_status"] == "draft" and record["review_date"] is None
        if "review_due" in old_records[rid]:
            assert record["review_due"] == old_records[rid]["review_due"]
    assert validate_country_directory(
        candidate, require_profile=True, schema_version="1.1.0"
    ) == []
    read_json(candidate / "sources.json")  # Also reject duplicate source keys.
    profile = read_json(candidate / "profile.json")
    assert profile["profile_version"] == VERSION
    assert profile["review_status"] == "draft" and profile["review_date"] is None
    # An access-gap note may legitimately have no surviving evidence to cite.
    # Positive synthesis must still point to the records that support it.
    for section in ("executive_assessment", "geographic_notes", "sector_notes"):
        for note in profile[section]:
            assert note["evidence_ids"] or note["pathway_ids"], (iso3, section, note)
    review = read_json(candidate / "review.json")
    assert review["status"] == "draft"
    assert review["reviewer"] is None and review["reviewed_on"] is None
    assert review["review_due"] == read_json(original / "review.json")["review_due"]
    assert (candidate / "dossier.md").read_text(encoding="utf-8") == build_dossier(candidate)
    with pytest.raises(ValueError, match="draft"):
        promote_release([candidate], generated_at="2026-10-26T00:00:00Z",
                        content_version=VERSION, current_dir=tmp_path / "current")
    assert not (tmp_path / "current").exists()


def test_original_candidates_and_accepted_six_are_preserved():
    freeze = read_json(ROOT / "reviews" / "20261026_remaining-country-review-freeze.json")
    assert set(freeze["countries_to_review"]) == set(COUNTRIES)
    assert len(freeze["preserved_files"]) == 182
    for name, digest in freeze["preserved_files"].items():
        payload = (ROOT / name).read_text(encoding="utf-8").encode("utf-8")
        assert hashlib.sha256(payload).hexdigest() == digest, name


def test_remaining_review_manifest_identifies_the_delivered_files():
    manifest = read_json(ROOT / "reviews" / "20261026_remaining-country-review-manifest.json")
    assert manifest["human_approval"] == "pending"
    assert set(manifest["countries"]) == set(COUNTRIES)
    assert len(manifest["candidate_files"]) == 108
    assert len(manifest["review_files"]) == 18
    for group in ("candidate_files", "review_files"):
        for name, digest in manifest[group].items():
            payload = (ROOT / name).read_text(encoding="utf-8").encode("utf-8")
            assert hashlib.sha256(payload).hexdigest() == digest, name
