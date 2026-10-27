"""Approval changes metadata only; the runtime is reproducible from those copies."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path

from climate_bank.dossier import build_dossier
from climate_bank.release import promote_release


ROOT = Path(__file__).resolve().parents[1]
VERSION = "2026.10.26"
COUNTRIES = set("AFG BFA CAF CMR COD ETH HTI IRN IRQ LBN LBY MLI MMR MOZ NER NGA PNG PSE SDN SOM SSD SYR UKR YEM".split())
CURRENT = "releases/current/runtime.json"
ACTIVATION_MANIFEST = "reviews/20261027_global-production-approval-manifest.json"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_approved_release_preserves_reviewed_content_and_rebuilds(tmp_path):
    manifest_path = ROOT / "reviews/20261026_production-approval-manifest.json"
    assert manifest_path.is_file(), "Approved release and approval manifest are missing"
    manifest = read_json(manifest_path)
    assert manifest["reviewer"] == "Lindsey Jones"
    assert manifest["approved_on"] == "2026-10-26"
    assert manifest["reviewed_commit"] == "79fbe8abde57633120f37b8b0212c6eb7c9531ea"
    assert len(manifest["candidate_files"]) == len(manifest["approved_files"]) == 144
    activation_path = ROOT / ACTIVATION_MANIFEST
    assert activation_path.is_file(), "Global activation manifest is missing"
    activation = read_json(activation_path)
    runtime_replacement = activation["frozen_replacements"][CURRENT]
    old_runtime_digest = manifest["release_files"][CURRENT]
    assert runtime_replacement["old_sha256_utf8_lf"] == old_runtime_digest
    archived_runtime = ROOT / runtime_replacement["archive_path"]
    archived_digest = hashlib.sha256(
        archived_runtime.read_text(encoding="utf-8").encode("utf-8")
    ).hexdigest()
    assert archived_digest == old_runtime_digest
    current_digest = hashlib.sha256(
        (ROOT / CURRENT).read_text(encoding="utf-8").encode("utf-8")
    ).hexdigest()
    assert current_digest == runtime_replacement["new_sha256_utf8_lf"]

    for group in ("candidate_files", "approved_files", "release_files"):
        for name, digest in manifest[group].items():
            if group == "release_files" and name == CURRENT:
                continue
            payload = (ROOT / name).read_text(encoding="utf-8").encode("utf-8")
            assert hashlib.sha256(payload).hexdigest() == digest, name

    directories = []
    for iso in sorted(COUNTRIES):
        draft = ROOT / "countries" / iso / "candidates" / VERSION
        approved = ROOT / "countries" / iso / "approved" / VERSION
        directories.append(approved)
        assert read_json(approved / "sources.json") == read_json(draft / "sources.json")
        evidence = read_json(draft / "evidence.json")
        for name in ("evidence", "pathways", "profile"):
            expected = deepcopy(read_json(draft / f"{name}.json"))
            for record in expected if isinstance(expected, list) else [expected]:
                record["review_status"] = "approved"
                record["review_date"] = "2026-10-26"
            assert read_json(approved / f"{name}.json") == expected, (iso, name)
        expected = read_json(draft / "review.json")
        expected.update(status="approved", reviewer="Lindsey Jones", reviewed_on="2026-10-26",
                        dossier_path=f"countries/{iso}/approved/{VERSION}/dossier.md")
        if expected["review_due"] < "2026-10-26":
            expected["review_due"] = min(record["review_due"] for record in evidence)
        actual = read_json(approved / "review.json")
        assert "Approved by Lindsey Jones on 2026-10-26" in actual["decision_notes"]
        expected["decision_notes"] = actual["decision_notes"]
        assert actual == expected, iso
        assert (approved / "dossier.md").read_text(encoding="utf-8") == build_dossier(approved)

    runtime = read_json(archived_runtime)
    assert runtime["schema_version"] == "1.1.0" and runtime["candidate"] is False
    assert runtime["content_version"] == "2026.10.26.approved-country-bank"
    assert set(runtime["countries"]) == COUNTRIES
    assert len(runtime["evidence_records"]) == 531
    assert len(runtime["pathways"]) == 168
    rebuilt = promote_release(directories, generated_at=runtime["generated_at"],
                              content_version=runtime["content_version"], current_dir=tmp_path)
    assert rebuilt == runtime
