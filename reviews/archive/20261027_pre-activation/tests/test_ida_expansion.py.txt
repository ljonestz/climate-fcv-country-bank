"""Completeness and draft-only integrity for the FY27 IDA expansion."""

import hashlib
import json
from collections import defaultdict
from pathlib import Path

import pytest

from climate_bank.dossier import build_dossier
from climate_bank.release import promote_release
from climate_bank.validation import validate_country_directory


ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "research/20261026_ida_expansion"
ROSTER = json.loads((RESEARCH / "TARGET_COUNTRIES.json").read_text(encoding="utf-8"))
TARGETS = {row["iso3"] for row in ROSTER["new_countries"]}


def read_json(path):
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            assert key not in result, (path, key)
            result[key] = value
        return result

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_keys)


def test_ida_roster_is_complete_without_reclassifying_existing_banks():
    assert len(TARGETS) == len(ROSTER["new_countries"]) == 60
    assert len(ROSTER["existing_ida_codes"]) == 18
    assert not TARGETS.intersection(ROSTER["existing_ida_codes"])
    assert len(TARGETS | set(ROSTER["existing_ida_codes"])) == 78
    assert set(ROSTER["existing_non_ida_codes"]) == set("IRN IRQ LBN LBY PSE UKR".split())
    assert {r["iso3"] for r in ROSTER["new_countries"] if r["inactive"]} == {"ERI", "ZWE"}
    assert ROSTER["eligibility_is_not_fcv_classification"] is True


def test_extraction_batches_cover_exactly_the_target_countries():
    countries = [c for path in sorted((RESEARCH / "extractions").glob("*.json"))
                 for c in read_json(path)]
    assert len(countries) == len({c["iso3"] for c in countries}) == 60
    assert {c["iso3"] for c in countries} == TARGETS


def test_source_paraphrase_budgets_include_shared_urls_and_qualifiers():
    words = defaultdict(int)
    for path in (RESEARCH / "extractions").glob("*.json"):
        for country in read_json(path):
            for source in country["sources"]:
                texts = [source["methodology"], source["limitations"]]
                for claim in country["claims"]:
                    if claim["source_id"] == source["source_id"]:
                        texts.extend([claim["paraphrase"], claim["limitations"],
                                      claim["scenario"] or ""])
                words[source["url"]] += sum(len(text.split()) for text in texts)
    assert words and max(words.values()) <= 180, {
        url: count for url, count in words.items() if count > 180}


def test_existing_bank_and_releases_remain_frozen():
    manifest_path = ROOT / "reviews/20261026_ida-baseline-freeze.json"
    assert manifest_path.is_file(), "Baseline freeze is not recorded"
    manifest = read_json(manifest_path)
    assert manifest["base_commit"] == ROSTER["bank_base"]
    for name, digest in manifest["preserved_files"].items():
        payload = (ROOT / name).read_text(encoding="utf-8").encode("utf-8")
        assert hashlib.sha256(payload).hexdigest() == digest, name


def test_approval_manifest_binds_every_country_file_without_authorizing_release():
    manifest = read_json(ROOT / "reviews/20261026_ida-approval-manifest.json")
    assert manifest["approval_granted"] is False
    assert manifest["runtime_changed"] is False
    assert manifest["app_bank_pin"] == ROSTER["bank_base"]
    assert {row["iso3"] for row in manifest["countries"]} == TARGETS
    required = {f"countries/{iso3}/candidates/2026.10.26/{name}"
                for iso3 in TARGETS for name in (
                    "sources.json", "evidence.json", "pathways.json",
                    "profile.json", "review.json", "dossier.md")}
    assert required <= set(manifest["files"])
    for name, digest in manifest["files"].items():
        payload = (ROOT / name).read_text(encoding="utf-8").encode("utf-8")
        assert hashlib.sha256(payload).hexdigest() == digest, name


@pytest.mark.parametrize("iso3", sorted(TARGETS))
def test_ida_country_is_traceable_valid_and_not_approved(iso3, tmp_path):
    country = ROOT / "countries" / iso3 / "candidates/2026.10.26"
    assert country.is_dir(), f"New country bank is missing: {iso3}"
    assert validate_country_directory(country, require_profile=True, schema_version="1.1.0") == []
    evidence = read_json(country / "evidence.json")
    sources = read_json(country / "sources.json")
    pathways = read_json(country / "pathways.json")
    profile = read_json(country / "profile.json")
    review = read_json(country / "review.json")
    assert evidence, "An empty scaffold is not a country bank"
    batch = next(r["batch"] for r in ROSTER["new_countries"] if r["iso3"] == iso3)
    raw = next(c for c in read_json(RESEARCH / "extractions" / f"{batch}.json")
               if c["iso3"] == iso3)
    assert len(evidence) == len(raw["claims"])
    assert {s["source_id"]: s["url"] for s in sources} == {
        s["source_id"]: s["url"] for s in raw["sources"]}
    inspected = {(a["source_id"], a["url"]) for a in raw["access_audit"]
                 if a["access_method"] in {"full-text", "official-excerpt"}}
    assert all((s["source_id"], s["url"]) in inspected for s in sources)
    for record, claim in zip(evidence, raw["claims"], strict=True):
        assert record["statement"] == claim["paraphrase"]
        assert record["source_refs"] == [{"source_id": claim["source_id"],
                                          "locator": claim["locator"]}]
    for record in evidence + pathways + [profile]:
        assert record["review_status"] == "draft" and record["review_date"] is None
    assert review["status"] == "draft"
    assert review["reviewer"] is None and review["reviewed_on"] is None
    assert review["evidence_ids"] == [r["evidence_id"] for r in evidence]
    assert review["pathway_ids"] == [r["pathway_id"] for r in pathways]
    assert review["dossier_path"] == f"countries/{iso3}/candidates/2026.10.26/dossier.md"
    assert (country / "dossier.md").read_text(encoding="utf-8") == build_dossier(country)
    with pytest.raises(ValueError, match="draft"):
        promote_release([country], generated_at="2026-10-26T00:00:00Z",
                        content_version="ida-draft", current_dir=tmp_path / "current")
    assert not (tmp_path / "current").exists()
