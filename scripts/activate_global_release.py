"""Reproduce the explicitly authorized, qualified 146-country routine-use release.

Default: stage and validate only. --publish installs the approved snapshots and
archives before replacing current. --check reproduces and compares checked-in files.
Approval/date constants describe the 27 October decision; rerunning never renews them.
"""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from climate_bank.dossier import build_dossier
from climate_bank.release import promote_release, write_canonical_json
from climate_bank.validation import validate_country_directory

ROOT = Path(__file__).resolve().parents[1]
APPROVED_VERSION = "2026.10.27"
APPROVED_ON = "2026-10-27"
CONTENT_VERSION = "2026.10.27.approved-global-country-bank"
GENERATED_AT = "2026-10-27T14:14:21Z"
SOURCE_COMMIT = "7a89952dee352b408f6b79132ba61406b8981cb2"
INPUT_MANIFEST = "reviews/20261027_remediated-review-manifest.json"
APPROVAL_MANIFEST = "reviews/20261027_global-production-approval-manifest.json"
FREEZE = "reviews/20261026_global-depth-baseline-freeze.json"
CURRENT = "releases/current/runtime.json"
OLD_RELEASE_ARCHIVE = "releases/archive/2026.10.26.approved-country-bank/runtime.json"
FROZEN_REPLACEMENTS = frozenset({
    CURRENT, "climate_bank/release.py", "climate_bank/validation.py",
    "schemas/runtime-release.schema.json", "tests/test_release.py",
    "tests/test_global_depth_integrity.py", "tests/test_approved_october_release.py",
    "tests/test_ida_expansion.py",
})
NOTICE_REPLACEMENTS = (
    ("Automated machine-screening is not independent source verification or human approval.",
     "Automated machine-screening is not independent source verification. "
     "Routine/default app-use approval does not certify claims or sources."),
    ("Draft extension: human source review and approval remain pending.",
     "Routine/default app-use approval granted by Lindsey Jones on 2026-10-27; "
     "independent source verification remains incomplete."),
)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def text_hash(path: Path) -> str:
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def prepare_approved_country(candidate_dir: Path, approved_dir: Path, *, iso3: str) -> dict:
    """Copy one bound draft, changing approval metadata and two exact notices only."""
    records = {name: read_json(candidate_dir / f"{name}.json")
               for name in ("evidence", "pathways", "profile", "review")}
    review = records["review"]
    if review["iso3"] != iso3 or review["status"] != "draft":
        raise ValueError(f"{iso3}: expected the bound draft review")
    structural = [row["review_due"] for row in records["evidence"]
                  if row["refresh_tier"] == "structural"]
    if not structural or min(structural) < APPROVED_ON:
        raise ValueError(f"{iso3}: no usable structural review window")
    approved_dir.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(candidate_dir / "sources.json", approved_dir / "sources.json")
    for name in ("evidence", "pathways"):
        for record in records[name]:
            if record["review_status"] != "draft" or record["review_date"] is not None:
                raise ValueError(f"{iso3}: expected draft {name} metadata")
            record.update(review_status="approved", review_date=APPROVED_ON)
    profile = records["profile"]
    notices = []
    for old, new in NOTICE_REPLACEMENTS:
        matched = [row for row in profile["known_gaps"] if row["text"].startswith(old)]
        if len(matched) != 1:
            raise ValueError(f"{iso3}: expected exactly one generic notice: {old}")
        matched[0]["text"] = new + matched[0]["text"][len(old):]
        notices.append({"old_prefix": old, "new_prefix": new, "count": 1})
    profile.update(review_status="approved", review_date=APPROVED_ON)
    review.update(
        status="approved", reviewer="Lindsey Jones", reviewed_on=APPROVED_ON,
        review_due=min(structural),
        dossier_path=f"countries/{iso3}/approved/{APPROVED_VERSION}/dossier.md",
        decision_notes=review["decision_notes"] + "\n\nPrior draft notes are historical. "
        "Approved by Lindsey Jones on 2026-10-27 for qualified routine/default "
        "Climate-FCV application use. This is release-use approval, not independent "
        "verification or certification of claims or sources. Existing uncertainty, "
        "source-access limits and individual evidence review deadlines remain in force. "
        f"See {APPROVAL_MANIFEST}.",
    )
    for name, value in records.items():
        write_canonical_json(approved_dir / f"{name}.json", value)
    (approved_dir / "dossier.md").write_text(build_dossier(approved_dir), encoding="utf-8", newline="\n")
    errors = validate_country_directory(approved_dir, require_profile=True,
                                       schema_version="1.1.0", as_of=date.fromisoformat(APPROVED_ON))
    if errors:
        raise ValueError(f"{iso3}: {errors}")
    return {"iso3": iso3, "country_review_due": min(structural),
            "profile_notice_transformations": notices,
            "evidence": len(records["evidence"]), "pathways": len(records["pathways"])}


def _install_immutable(source: Path, target: Path) -> None:
    if target.exists():
        if text_hash(source) != text_hash(target):
            raise ValueError(f"Existing immutable output differs: {target.relative_to(ROOT)}")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def _install_outputs(stage: Path, outputs: list[str], *, check: bool) -> None:
    """Reject every collision before installing any immutable output."""
    for relative in outputs:
        target = ROOT / relative
        if target.exists() and text_hash(target) != text_hash(stage / relative):
            raise ValueError(f"Existing immutable output differs: {relative}")
        if check and not target.is_file():
            raise ValueError(f"Missing output: {relative}")
    if not check:
        for relative in outputs:
            _install_immutable(stage / relative, ROOT / relative)


def build_activation(*, publish: bool = False, check: bool = False) -> dict:
    for relative in (INPUT_MANIFEST, FREEZE):
        original = subprocess.run(["git", "show", f"{SOURCE_COMMIT}:{relative}"],
                                  cwd=ROOT, check=True, capture_output=True).stdout
        original_hash = hashlib.sha256(original.decode("utf-8").replace("\r\n", "\n").encode("utf-8")).hexdigest()
        if text_hash(ROOT / relative) != original_hash:
            raise ValueError(f"Bound input manifest changed: {relative}")
    inputs = read_json(ROOT / INPUT_MANIFEST)
    rows = inputs["countries"]
    if len(rows) != 146 or len({row["iso3"] for row in rows}) != 146:
        raise ValueError("Expected exactly the bound 146-country roster")
    candidate_files = {}
    for row in rows:
        for relative, digest in row["candidate_file_hashes"].items():
            expected_prefix = f"countries/{row['iso3']}/candidates/2026.10.27.remediated/"
            if not relative.startswith(expected_prefix) or text_hash(ROOT / relative) != digest:
                raise ValueError(f"Changed or unbound candidate: {relative}")
            candidate_files[relative] = digest
    if len(candidate_files) != 876:
        raise ValueError("Expected six bound input files per country")
    freeze = read_json(ROOT / FREEZE)
    if len(freeze["files"]) != 878 or freeze["algorithm"] != "sha256-utf8-lf":
        raise ValueError("Unexpected frozen baseline contract")
    with tempfile.TemporaryDirectory(prefix=".activation-stage-", dir=ROOT) as stage_name:
        stage = Path(stage_name)
        transformations = []
        approved_files = {}
        for row in sorted(rows, key=lambda value: value["iso3"]):
            iso3 = row["iso3"]
            relative = f"countries/{iso3}/approved/{APPROVED_VERSION}"
            target = stage / relative
            transformations.append(prepare_approved_country(
                ROOT / f"countries/{iso3}/candidates/2026.10.27.remediated", target, iso3=iso3))
            for path in sorted(target.iterdir()):
                approved_files[path.relative_to(stage).as_posix()] = text_hash(path)
        release = promote_release(
            [stage / f"countries/{row['iso3']}/approved/{APPROVED_VERSION}" for row in rows],
            generated_at=GENERATED_AT, content_version=CONTENT_VERSION,
            current_dir=stage / "releases/current", include_country_profiles=True,
        )
        counts = {"countries": len(release["countries"]), "sources": len(release["sources"]),
                  "evidence": len(release["evidence_records"]), "pathways": len(release["pathways"])}
        if counts != {"countries": 146, "sources": 1045, "evidence": 2643, "pathways": 241}:
            raise ValueError(f"Unexpected release counts: {counts}")
        replacements = {}
        for relative, old_hash in freeze["files"].items():
            replacement = stage / CURRENT if relative == CURRENT else ROOT / relative
            new_hash = text_hash(replacement)
            if new_hash == old_hash:
                continue
            if relative not in FROZEN_REPLACEMENTS:
                raise ValueError(f"Unrelated frozen file changed: {relative}")
            archive = OLD_RELEASE_ARCHIVE if relative == CURRENT else (
                f"reviews/archive/20261027_pre-activation/{relative}.txt")
            archive_path = stage / archive
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            original = subprocess.run(["git", "show", f"{SOURCE_COMMIT}:{relative}"],
                                      cwd=ROOT, check=True, capture_output=True).stdout
            archive_path.write_bytes(original)
            if text_hash(archive_path) != old_hash:
                raise ValueError(f"Original frozen identity mismatch: {relative}")
            replacements[relative] = {"archive_path": archive, "old_sha256_utf8_lf": old_hash,
                                      "new_sha256_utf8_lf": new_hash}
        manifest = {
            "artifact_kind": "qualified-global-country-bank-routine-use-approval",
            "reviewer": "Lindsey Jones", "approved_on": APPROVED_ON,
            "approval_scope": "qualified routine/default Climate-FCV application use; not independent source certification",
            "source_commit": SOURCE_COMMIT, "content_version": CONTENT_VERSION,
            "generated_at": GENERATED_AT, "input_manifest": INPUT_MANIFEST,
            "input_manifest_sha256_utf8_lf": text_hash(ROOT / INPUT_MANIFEST),
            "pipeline_file": "scripts/activate_global_release.py",
            "pipeline_sha256_utf8_lf": text_hash(Path(__file__)),
            "baseline_freeze": FREEZE, "baseline_freeze_sha256_utf8_lf": text_hash(ROOT / FREEZE),
            "hash_method": "sha256-utf8-lf", "counts": counts,
            "country_review_due_rule": "earliest existing structural evidence deadline; individual current evidence deadlines unchanged",
            "candidate_files": dict(sorted(candidate_files.items())),
            "approved_files": dict(sorted(approved_files.items())),
            "release_files": {CURRENT: text_hash(stage / CURRENT)},
            "frozen_replacements": replacements, "countries": transformations,
        }
        if publish or check:
            if text_hash(ROOT / CURRENT) not in {
                freeze["files"][CURRENT], text_hash(stage / CURRENT)
            }:
                raise ValueError("Refusing to replace unrelated current runtime")
            if (ROOT / APPROVAL_MANIFEST).exists() and read_json(ROOT / APPROVAL_MANIFEST) != manifest:
                raise ValueError("Existing approval manifest differs from reconstruction")
            outputs = [*approved_files, *(entry["archive_path"] for entry in replacements.values())]
            for row in rows:
                directory = ROOT / f"countries/{row['iso3']}/approved/{APPROVED_VERSION}"
                expected_names = {"sources.json", "evidence.json", "pathways.json", "profile.json", "review.json", "dossier.md"}
                if directory.exists() and {path.name for path in directory.iterdir()} - expected_names:
                    raise ValueError(f"Unexpected files in approved snapshot: {row['iso3']}")
            _install_outputs(stage, outputs, check=check)
            if check:
                if text_hash(ROOT / CURRENT) != text_hash(stage / CURRENT):
                    raise ValueError("Current release differs from reconstruction")
                if read_json(ROOT / APPROVAL_MANIFEST) != manifest:
                    raise ValueError("Approval manifest differs from reconstruction")
            else:
                write_canonical_json(ROOT / APPROVAL_MANIFEST, manifest)
                write_canonical_json(ROOT / CURRENT, release)
        return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--publish", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    manifest = build_activation(publish=args.publish, check=args.check)
    print(json.dumps({"mode": "check" if args.check else "publish" if args.publish else "dry-run",
                      "content_version": CONTENT_VERSION, "counts": manifest["counts"],
                      "frozen_replacements": sorted(manifest["frozen_replacements"]),
                      "runtime_sha256_utf8_lf": manifest["release_files"][CURRENT]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
