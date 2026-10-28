"""Build reproducible, unapproved remediation candidates from the exact 146-bank roster."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import tempfile

from climate_bank.dossier import build_dossier
from climate_bank.release import write_canonical_json
from climate_bank.validation import validate_country_directory


ROOT = Path(__file__).resolve().parents[1]
VERSION = "2026.10.27.remediated"
SOURCE_VERSION = "2026.10.26.deep"
RESEARCH = ROOT / "research/20261027_remediation"
SOURCE_MANIFEST = ROOT / "research/20261026_global_depth/TEST_INPUTS.json"
PRIOR_REVIEW = ROOT / "reviews/20261027_global-depth-review-manifest.json"
OUTPUT_MANIFEST = ROOT / "reviews/20261027_remediated-review-manifest.json"
OUTPUT_LEDGER = ROOT / "reviews/20261027_remediated-country-ledger.json"
OUTPUT_TABLE = ROOT / "reviews/20261027_remediated-approval-table.md"
COUNTRY_FILES = (
    "sources.json", "evidence.json", "pathways.json", "profile.json", "review.json"
)
OUTPUT_FILES = (*COUNTRY_FILES, "dossier.md")
PATCH_FIELDS = {
    "source_updates", "evidence_updates", "pathway_updates", "add_sources",
    "add_evidence", "add_pathways", "exclude_evidence_ids", "exclude_pathway_ids",
    "add_gaps", "remove_gap_texts", "profile_updates", "decisions",
}
PROFILE_UPDATE_FIELDS = {
    "executive_assessment", "coverage", "geographic_notes", "sector_notes",
    "known_gaps", "selection_aliases",
}
STALE_PATHWAY_GAP = (
    "The bank contains no completed mediated climate-FCV pathway; "
    "this is an evidence gap, not evidence of absence."
)
DISPOSITIONS = {"reviewed-unchanged", "corrected", "enriched", "unresolved-limited"}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path):
    text = Path(path).read_text(encoding="utf-8")
    if "\ufffd" in text:
        raise ValueError(f"replacement character in UTF-8 input: {path}")
    return json.loads(text, object_pairs_hook=_unique_object)


def _text_hash(path: Path) -> str:
    return hashlib.sha256(Path(path).read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def _map_hash(file_hashes: dict[str, str]) -> str:
    payload = json.dumps(file_hashes, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _verify_frozen_baseline(root: Path, prior_manifest: dict) -> dict:
    freeze_relative = prior_manifest.get("baseline_freeze")
    relative = Path(freeze_relative) if isinstance(freeze_relative, str) else None
    if relative is None or relative.is_absolute() or ".." in relative.parts:
        raise ValueError("prior review manifest has an invalid baseline freeze path")
    freeze_path = (root / relative).resolve()
    if not freeze_path.is_relative_to(root.resolve()):
        raise ValueError("baseline freeze path escapes repository")
    freeze = read_json(freeze_path)
    files = freeze.get("files")
    expected_count = prior_manifest.get("baseline_file_count")
    if (not isinstance(files, dict) or len(files) != expected_count
            or freeze.get("algorithm") != "sha256-utf8-lf"
            or freeze.get("baseline_commit") != prior_manifest.get("baseline_commit")):
        raise ValueError("frozen baseline manifest does not match the prior review contract")
    mismatched = []
    for name, expected_hash in files.items():
        item = Path(name)
        if item.is_absolute() or ".." in item.parts:
            mismatched.append(name)
            continue
        file_path = (root / item).resolve()
        if not file_path.is_relative_to(root.resolve()) or not file_path.is_file():
            mismatched.append(name)
        elif _text_hash(file_path) != expected_hash:
            mismatched.append(name)
    if mismatched:
        raise ValueError(f"frozen baseline changed: {mismatched[:10]}")
    return {
        "file_count": len(files),
        "freeze_file": relative.as_posix(),
        "freeze_sha256_utf8_lf": _text_hash(freeze_path),
    }


def _compare_published_files(files: dict[str, tuple[Path, Path]]) -> None:
    missing = [relative for relative, (_, published) in files.items()
               if not published.is_file()]
    mismatched = [relative for relative, (staged, published) in files.items()
                  if published.is_file() and _text_hash(staged) != _text_hash(published)]
    if missing or mismatched:
        raise ValueError(
            f"published remediation differs from staged output; "
            f"missing={sorted(missing)}, mismatched={sorted(mismatched)}"
        )


def _record_index(rows: list[dict], key: str, label: str) -> dict[str, dict]:
    indexed = {}
    for row in rows:
        record_id = row.get(key)
        if not isinstance(record_id, str) or record_id in indexed:
            raise ValueError(f"{label}: missing or duplicate {key} {record_id!r}")
        indexed[record_id] = row
    return indexed


def _update_records(rows: list[dict], updates: dict, *, id_key: str,
                    label: str, immutable: set[str]) -> None:
    if not isinstance(updates, dict):
        raise ValueError(f"{label} must map record IDs to field updates")
    indexed = _record_index(rows, id_key, label)
    for record_id, fields in updates.items():
        if record_id not in indexed or not isinstance(fields, dict) or not fields:
            raise ValueError(f"{label}: unknown ID or empty update for {record_id}")
        forbidden = set(fields) & immutable
        unknown = set(fields) - set(indexed[record_id])
        if forbidden or unknown:
            raise ValueError(f"{label} {record_id}: immutable={sorted(forbidden)}, unknown={sorted(unknown)}")
        indexed[record_id].update(deepcopy(fields))


def _append_records(rows: list[dict], additions: list[dict], *, id_key: str,
                    iso3: str, label: str) -> None:
    if not isinstance(additions, list):
        raise ValueError(f"{label} must be a list")
    indexed = _record_index(rows, id_key, label)
    for row in additions:
        record_id = row.get(id_key) if isinstance(row, dict) else None
        if not isinstance(record_id, str) or not record_id.startswith(f"{iso3}-"):
            raise ValueError(f"{label}: invalid country record ID {record_id!r}")
        country_match = (
            iso3 in row.get("country_codes", []) if id_key == "source_id"
            else row.get("iso3") == iso3
        )
        if record_id in indexed or not country_match:
            raise ValueError(f"{label}: duplicate ID or country mismatch for {record_id}")
        if id_key != "source_id" and (
            row.get("review_status") != "draft" or row.get("review_date") is not None
        ):
            raise ValueError(f"{label} {record_id} must remain draft/null")
        rows.append(deepcopy(row))
        indexed[record_id] = rows[-1]


def _exclude_records(rows: list[dict], ids: list[str], *, id_key: str, label: str) -> list[str]:
    if not isinstance(ids, list) or len(ids) != len(set(ids)):
        raise ValueError(f"{label} exclusions must be a unique ID list")
    found = _record_index(rows, id_key, label)
    unknown = set(ids) - set(found)
    if unknown:
        raise ValueError(f"{label} exclusion IDs not present: {sorted(unknown)}")
    excluded = set(ids)
    rows[:] = [row for row in rows if row[id_key] not in excluded]
    return sorted(excluded)


def _audit_record_index(audit: dict, key: str) -> dict[str, dict]:
    rows = audit.get(key)
    if not isinstance(rows, list):
        raise ValueError(f"audit.{key} must be a list")
    indexed = {}
    for row in rows:
        record_id = row.get("record_id") if isinstance(row, dict) else None
        if not isinstance(record_id, str) or record_id in indexed:
            raise ValueError(f"audit.{key} has missing or duplicate record ID {record_id!r}")
        indexed[record_id] = row
    return indexed


def _apply_global_rules(bundle: dict, *, audit: dict, rules: dict) -> dict:
    required = {
        "apply_full_statement_to_compact", "append_projected_scenario",
        "unverified_uncertainty_suffix", "verified_record_ids",
    }
    if not isinstance(rules, dict) or not required <= set(rules):
        raise ValueError(f"remediation rules must include {sorted(required)}")
    if rules["apply_full_statement_to_compact"] is not True or rules["append_projected_scenario"] is not True:
        raise ValueError("global compact-statement and projection safeguards must be enabled")
    suffix = rules["unverified_uncertainty_suffix"]
    if not isinstance(suffix, str) or not suffix.strip():
        raise ValueError("unverified uncertainty suffix is required")

    evidence = bundle["evidence.json"]
    pathways = bundle["pathways.json"]
    evidence_ids = _record_index(evidence, "evidence_id", "evidence")
    pathway_ids = _record_index(pathways, "pathway_id", "pathways")
    audited_evidence = _audit_record_index(audit, "evidence")
    audited_pathways = _audit_record_index(audit, "pathways")
    base_evidence_ids = set(evidence_ids) & set(audited_evidence)
    base_pathway_ids = set(pathway_ids) & set(audited_pathways)
    if not base_evidence_ids or len(base_evidence_ids) != len(audited_evidence):
        raise ValueError("audit evidence IDs do not match the candidate records")
    if len(base_pathway_ids) != len(audited_pathways):
        raise ValueError("audit pathway IDs do not match the candidate records")

    verified = {
        record_id for record_id, row in (*audited_evidence.items(), *audited_pathways.items())
        if row.get("claim_verification") == "verified"
    }
    root_verified = rules["verified_record_ids"]
    if not isinstance(root_verified, list) or len(root_verified) != len(set(root_verified)):
        raise ValueError("verified_record_ids must be a unique list")
    # Root adjudications span the whole roster; only apply this country's IDs.
    verified.update(record_id for record_id in root_verified
                    if record_id.startswith(f"{audit['iso3']}-"))
    all_ids = set(evidence_ids) | set(pathway_ids)
    if not verified <= all_ids:
        raise ValueError(f"verification references unknown records: {sorted(verified - all_ids)}")

    copied, scenarios, qualified = [], [], []
    for record in evidence:
        if record["compact_statement"] != record["statement"]:
            record["compact_statement"] = record["statement"]
            copied.append(record["evidence_id"])
        scenario = record.get("scenario")
        compact = record["compact_statement"]
        if (record.get("evidence_status") == "projected" and isinstance(scenario, str)
                and scenario.strip() and scenario.casefold() not in compact.casefold()):
            record["compact_statement"] = f"{compact.rstrip()} Scenario: {scenario}"
            scenarios.append(record["evidence_id"])

    for record in evidence + pathways:
        record_id = record.get("evidence_id", record.get("pathway_id"))
        if record_id not in verified and suffix not in record["uncertainty"]:
            record["uncertainty"] = f"{record['uncertainty'].rstrip()} {suffix}"
            qualified.append(record_id)

    unverified_evidence = sorted(set(evidence_ids) - verified)
    unverified_pathways = sorted(set(pathway_ids) - verified)
    disclosure = {
        "text": (
            "Automated machine-screening is not independent source verification or human approval. "
            f"{len(unverified_evidence)} of {len(evidence)} evidence records and "
            f"{len(unverified_pathways)} of {len(pathways)} pathways lack claim-level verification "
            "in this remediation; review the linked records before relying on them."
        ),
        "evidence_ids": unverified_evidence,
        "pathway_ids": unverified_pathways,
    }
    gaps = bundle["profile.json"]["known_gaps"]
    gaps[:] = [gap for gap in gaps if not gap["text"].startswith("Automated machine-screening is not independent source verification")]
    gaps.insert(0, disclosure)
    stale_gap_removed = False
    if pathways and any(gap["text"] == STALE_PATHWAY_GAP for gap in gaps):
        gaps[:] = [gap for gap in gaps if gap["text"] != STALE_PATHWAY_GAP]
        stale_gap_removed = True
    return {
        "compact_statement_copied": sorted(copied),
        "projected_scenario_appended": sorted(scenarios),
        "uncertainty_qualified": sorted(qualified),
        "unverified_evidence_ids": unverified_evidence,
        "unverified_pathway_ids": unverified_pathways,
        "verified_record_ids": sorted(verified),
        "stale_pathway_gap_removed": stale_gap_removed,
    }


def _synchronize_profile_references(bundle: dict, *, previous_statements: dict[str, str]) -> dict:
    """Keep profile references aligned with current records after additions and exclusions."""
    profile = bundle["profile.json"]
    evidence = bundle["evidence.json"]
    pathways = bundle["pathways.json"]
    evidence_by_id = _record_index(evidence, "evidence_id", "evidence")
    pathway_ids = {row["pathway_id"] for row in pathways}
    current_evidence_ids = set(evidence_by_id)
    changed_notes = []
    for note in profile.get("geographic_notes", []):
        refs = note.get("evidence_ids", [])
        if len(refs) == 1 and refs[0] in previous_statements and refs[0] in evidence_by_id:
            old_statement = previous_statements[refs[0]]
            new_statement = evidence_by_id[refs[0]]["statement"]
            if old_statement != new_statement:
                if old_statement in note["text"]:
                    note["text"] = note["text"].replace(old_statement, new_statement)
                else:
                    note["text"] = new_statement
                changed_notes.append(refs[0])
        note["evidence_ids"] = sorted(set(refs) & current_evidence_ids)
        note["pathway_ids"] = sorted(set(note.get("pathway_ids", [])) & pathway_ids)

    refreshed_coverage = []
    for row in profile.get("coverage", []):
        if row["dimension"] == "evidence-class":
            record_ids = sorted(
                record["evidence_id"] for record in evidence
                if record["evidence_class"] == row["value"]
            )
            row["record_ids"] = record_ids
            row["status"] = "partial" if record_ids else "gap"
            refreshed_coverage.append(row["value"])
        elif row["dimension"] == "pathway":
            record_ids = sorted(pathway_ids)
            row["record_ids"] = record_ids
            row["status"] = "partial" if record_ids else "gap"
            refreshed_coverage.append(row["value"])
        else:
            row["record_ids"] = sorted(set(row.get("record_ids", [])) & current_evidence_ids)
            if not row["record_ids"]:
                row["status"] = "gap"
        row["record_ids"] = sorted(set(row.get("record_ids", [])) &
                                   (current_evidence_ids | pathway_ids))

    for gap in profile.get("known_gaps", []):
        gap["evidence_ids"] = sorted(set(gap.get("evidence_ids", [])) & current_evidence_ids)
        gap["pathway_ids"] = sorted(set(gap.get("pathway_ids", [])) & pathway_ids)
    return {
        "coverage_dimensions_refreshed": sorted(refreshed_coverage),
        "geographic_notes_synchronized": sorted(changed_notes),
    }


def remediate_country(source_dir: Path, output_dir: Path, *, iso3: str, version: str,
                      patch: dict, audit: dict, rules: dict) -> dict:
    """Apply explicit patches, then global safety rules, and write one validated draft."""
    source_dir, output_dir = Path(source_dir), Path(output_dir)
    if output_dir.exists():
        raise FileExistsError(output_dir)
    if not re.fullmatch(r"[A-Z]{3}", iso3) or not re.fullmatch(r"[A-Za-z0-9.-]+", version):
        raise ValueError("invalid ISO3 or candidate version")
    source_errors = validate_country_directory(source_dir, require_profile=True, schema_version="1.1.0")
    if source_errors:
        raise ValueError(f"{source_dir}: {source_errors}")
    if audit.get("iso3") != iso3 or audit.get("human_approval") not in {"pending", False}:
        raise ValueError(f"{iso3}: invalid or approved audit record")
    if audit.get("disposition") not in DISPOSITIONS:
        raise ValueError(f"{iso3}: invalid audit disposition")
    if not isinstance(patch, dict) or set(patch) - PATCH_FIELDS:
        raise ValueError(f"{iso3}: unknown override fields {sorted(set(patch) - PATCH_FIELDS)}")

    bundle = {name: read_json(source_dir / name) for name in COUNTRY_FILES}
    evidence_before = _record_index(bundle["evidence.json"], "evidence_id", "evidence")
    pathway_before = _record_index(bundle["pathways.json"], "pathway_id", "pathways")
    evidence_deadlines = {key: row.get("review_due") for key, row in evidence_before.items()}
    previous_statements = {key: row["statement"] for key, row in evidence_before.items()}
    expected_audited_evidence = set(evidence_before)
    expected_audited_pathways = set(pathway_before)
    if set(_audit_record_index(audit, "evidence")) != expected_audited_evidence:
        raise ValueError(f"{iso3}: audit must cover every prior evidence record exactly once")
    if set(_audit_record_index(audit, "pathways")) != expected_audited_pathways:
        raise ValueError(f"{iso3}: audit must cover every prior pathway exactly once")

    _update_records(bundle["sources.json"], patch.get("source_updates", {}), id_key="source_id",
                    label="source_updates", immutable={"source_id", "checksum"})
    _update_records(bundle["evidence.json"], patch.get("evidence_updates", {}), id_key="evidence_id",
                    label="evidence_updates", immutable={"evidence_id", "iso3", "review_status", "review_date", "review_due"})
    _update_records(bundle["pathways.json"], patch.get("pathway_updates", {}), id_key="pathway_id",
                    label="pathway_updates", immutable={"pathway_id", "iso3", "review_status", "review_date"})
    _append_records(bundle["sources.json"], patch.get("add_sources", []), id_key="source_id", iso3=iso3, label="add_sources")
    _append_records(bundle["evidence.json"], patch.get("add_evidence", []), id_key="evidence_id", iso3=iso3, label="add_evidence")
    _append_records(bundle["pathways.json"], patch.get("add_pathways", []), id_key="pathway_id", iso3=iso3, label="add_pathways")

    excluded_evidence = _exclude_records(bundle["evidence.json"], patch.get("exclude_evidence_ids", []),
                                         id_key="evidence_id", label="evidence")
    excluded_pathways = _exclude_records(bundle["pathways.json"], patch.get("exclude_pathway_ids", []),
                                         id_key="pathway_id", label="pathways")
    for name, id_key in (("sources.json", "source_id"), ("evidence.json", "evidence_id"),
                         ("pathways.json", "pathway_id")):
        bundle[name].sort(key=lambda row: row[id_key])

    profile = bundle["profile.json"]
    removals = patch.get("remove_gap_texts", [])
    additions = patch.get("add_gaps", [])
    if (not isinstance(removals, list) or not isinstance(additions, list)
            or any(not isinstance(text, str) or not text.strip() for text in removals + additions)):
        raise ValueError(f"{iso3}: add_gaps/remove_gap_texts must contain non-empty text")
    original_gap_texts = {row["text"] for row in profile["known_gaps"]}
    if not set(removals) <= original_gap_texts or set(removals) & set(additions):
        raise ValueError(f"{iso3}: gap removal is missing or conflicts with an addition")
    profile["known_gaps"] = [row for row in profile["known_gaps"] if row["text"] not in set(removals)]
    for text in additions:
        if text not in {row["text"] for row in profile["known_gaps"]}:
            profile["known_gaps"].append({"text": text, "evidence_ids": [], "pathway_ids": []})
    profile_updates = patch.get("profile_updates", {})
    if not isinstance(profile_updates, dict) or set(profile_updates) - PROFILE_UPDATE_FIELDS:
        raise ValueError(f"{iso3}: invalid profile_updates")
    profile.update(deepcopy(profile_updates))
    profile["profile_version"] = version

    review = bundle["review.json"]
    review["dossier_path"] = f"countries/{iso3}/candidates/{version}/dossier.md"
    review["evidence_ids"] = sorted(row["evidence_id"] for row in bundle["evidence.json"])
    review["pathway_ids"] = sorted(row["pathway_id"] for row in bundle["pathways.json"])
    if (review["status"] != "draft" or review["reviewer"] is not None
            or review["reviewed_on"] is not None or profile["review_status"] != "draft"
            or profile["review_date"] is not None):
        raise ValueError(f"{iso3}: candidate review flags must remain draft/null")
    for record_id, due in evidence_deadlines.items():
        if record_id in {r["evidence_id"] for r in bundle["evidence.json"]}:
            current = next(r["review_due"] for r in bundle["evidence.json"] if r["evidence_id"] == record_id)
            if current != due:
                raise ValueError(f"{iso3}/{record_id}: inherited review deadline changed")

    profile_transforms = _synchronize_profile_references(
        bundle, previous_statements=previous_statements
    )
    transforms = _apply_global_rules(bundle, audit=audit, rules=rules)
    transforms.update(profile_transforms)
    for rows in (bundle["evidence.json"], bundle["pathways.json"]):
        if any(row["review_status"] != "draft" or row["review_date"] is not None for row in rows):
            raise ValueError(f"{iso3}: candidate records must remain draft/null")

    output_dir.mkdir(parents=True)
    for name, value in bundle.items():
        write_canonical_json(output_dir / name, value)
    errors = validate_country_directory(output_dir, require_profile=True, schema_version="1.1.0")
    if errors:
        raise ValueError(f"{output_dir}: {errors}")
    (output_dir / "dossier.md").write_text(build_dossier(output_dir), encoding="utf-8", newline="\n")
    file_hashes = {name: _text_hash(output_dir / name) for name in OUTPUT_FILES}
    return {
        "iso3": iso3,
        "country_name": review["country_name"],
        "audit_disposition": audit["disposition"],
        "human_approval": "pending",
        "counts": {"sources": len(bundle["sources.json"]), "evidence": len(bundle["evidence.json"]),
                   "pathways": len(bundle["pathways.json"])},
        "decisions": deepcopy(patch.get("decisions", [])),
        "excluded_evidence_ids": excluded_evidence,
        "excluded_pathway_ids": excluded_pathways,
        "applied_transformations": transforms,
        "candidate_file_hashes": file_hashes,
    }


def _source_roster(root: Path, manifest_path: Path, prior_manifest: dict) -> list[tuple[str, Path, str]]:
    names = read_json(manifest_path)
    if not isinstance(names, list) or len(names) != 146:
        raise ValueError("the remediation input manifest must list the exact 146-country roster")
    expected = {row["iso3"] for row in prior_manifest["countries"]}
    result = []
    seen = set()
    for name in names:
        if not isinstance(name, str):
            raise ValueError(f"invalid prior candidate path: {name!r}")
        relative = Path(name)
        if (relative.is_absolute() or ".." in relative.parts
                or len(relative.parts) != 4 or relative.parts[0] != "countries"
                or relative.parts[2] != "candidates" or relative.parts[3] != SOURCE_VERSION):
            raise ValueError(f"invalid prior candidate path: {name!r}")
        iso3 = relative.parts[1]
        if not re.fullmatch(r"[A-Z]{3}", iso3) or iso3 in seen:
            raise ValueError(f"duplicate or invalid ISO3 in source manifest: {iso3}")
        source_dir = (root / relative).resolve()
        if not source_dir.is_relative_to(root.resolve()):
            raise ValueError(f"country manifest path escapes repository: {name}")
        seen.add(iso3)
        result.append((iso3, source_dir, relative.as_posix()))
    if seen != expected:
        raise ValueError("source manifest does not match the prior all-country review manifest")
    return result


def _audit_inputs(root: Path, audit_dir: Path, countries: set[str]) -> tuple[dict[str, Path], dict[str, Path]]:
    paths = sorted(audit_dir.glob("*.json"))
    files = {path.stem: path for path in paths if re.fullmatch(r"[A-Z]{3}", path.stem)}
    support_paths = {path.name: path for path in paths if not re.fullmatch(r"[A-Z]{3}", path.stem)}
    if set(files) != countries or set(support_paths) != {"aggregate.json"}:
        raise ValueError(
            f"audit inputs must contain 146 ISO files and aggregate.json; "
            f"missing={sorted(countries - set(files))}, extra-country={sorted(set(files) - countries)}, "
            f"support={sorted(support_paths)}"
        )
    return (
        {iso3: path.resolve() for iso3, path in files.items()},
        {name: path.resolve() for name, path in support_paths.items()},
    )


def _approval_table(countries: list[dict], summary: dict) -> str:
    lines = [
        "# Remediated global country-depth candidates: 27 October 2026",
        "",
        "All candidates remain DRAFT; designated human approval is pending for every country.",
        "Automated machine-screening and deterministic remediation do not constitute independent source verification or human approval.",
        "The 2026.10.26.deep inputs and frozen 878-file baseline are retained; the approved production release is unchanged.",
        "See the [review manifest](20261027_remediated-review-manifest.json) for country file identities and source inputs.",
        "",
        "## Method and limitations",
        "",
        f"The exact 146-country input roster now contains {summary['evidence']} evidence records and {summary['pathways']} pathways. "
        f"Claim-level verification is recorded for {summary['verified_evidence']} evidence records and {summary['verified_pathways']} pathways; "
        f"the remaining {summary['unverified_evidence']} evidence records and {summary['unverified_pathways']} pathways carry explicit uncertainty and profile disclosures.",
        "Each country row links to its new candidate dossier. The review manifest records candidate and input file hashes, override bundle and audit JSON identities.",
        "",
        "| ISO3 | Country | Audit disposition | Sources | Evidence | Pathways | Verified E/P | Human decision |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for row in sorted(countries, key=lambda item: item["iso3"]):
        t = row["applied_transformations"]
        verified_e = row["counts"]["evidence"] - len(t["unverified_evidence_ids"])
        verified_p = row["counts"]["pathways"] - len(t["unverified_pathway_ids"])
        dossier = f"../countries/{row['iso3']}/candidates/{VERSION}/dossier.md"
        lines.append(
            f"| {row['iso3']} | [{row['country_name']}]({dossier}) | {row['audit_disposition']} | "
            f"{row['counts']['sources']} | {row['counts']['evidence']} | {row['counts']['pathways']} | "
            f"{verified_e}/{verified_p} | Pending |"
        )
    return "\n".join(lines) + "\n"


def build_remediation(root: Path = ROOT, *, publish: bool = True) -> dict:
    """Preflight, stage and write all countries and review identities without overwriting."""
    root = Path(root).resolve()
    prior_manifest = read_json(root / PRIOR_REVIEW.relative_to(ROOT))
    baseline_verification = _verify_frozen_baseline(root, prior_manifest)
    inputs = _source_roster(root, root / SOURCE_MANIFEST.relative_to(ROOT), prior_manifest)
    input_codes = {iso3 for iso3, _, _ in inputs}
    overrides_path = root / RESEARCH.relative_to(ROOT) / "overrides.json"
    override_doc = read_json(overrides_path)
    if override_doc.get("version") != VERSION or not isinstance(override_doc.get("countries"), dict):
        raise ValueError(f"overrides.json must target {VERSION} and contain a countries map")
    rules = override_doc.get("rules")
    audit_dir = root / RESEARCH.relative_to(ROOT) / "audit"
    audits, audit_support_files = _audit_inputs(root, audit_dir, input_codes)
    audit_support_hashes = {
        path.relative_to(root).as_posix(): _text_hash(path)
        for path in audit_support_files.values()
    }
    if set(override_doc["countries"]) - input_codes:
        raise ValueError("override bundle contains countries outside the fixed roster")

    artifact_paths = [
        root / RESEARCH.relative_to(ROOT) / "TEST_INPUTS.json",
        root / OUTPUT_MANIFEST.relative_to(ROOT),
        root / OUTPUT_LEDGER.relative_to(ROOT),
        root / OUTPUT_TABLE.relative_to(ROOT),
    ]
    output_dirs = [root / "countries" / iso3 / "candidates" / VERSION for iso3 in sorted(input_codes)]
    existing = [path for path in (*output_dirs, *artifact_paths) if path.exists()]
    if publish and existing:
        raise FileExistsError(f"refusing to overwrite remediation outputs: {existing[:5]}")

    prior_manifest_hash = _text_hash(root / PRIOR_REVIEW.relative_to(ROOT))
    input_manifest_hash = _text_hash(root / SOURCE_MANIFEST.relative_to(ROOT))
    overrides_hash = _text_hash(overrides_path)
    pipeline_hash = _text_hash(Path(__file__))
    stage_root_parent = root
    countries = []
    matched_existing_outputs = False
    with tempfile.TemporaryDirectory(prefix=".depth-remediation-", dir=stage_root_parent) as temp_name:
        stage_root = Path(temp_name).resolve()
        if not stage_root.is_relative_to(root):
            raise ValueError("remediation staging directory must stay within the repository")
        for iso3, source_dir, source_relative in inputs:
            source_hashes = {name: _text_hash(source_dir / name) for name in OUTPUT_FILES}
            audit = read_json(audits[iso3])
            patch = override_doc["countries"].get(iso3, {})
            staged = stage_root / iso3 / "candidate"
            row = remediate_country(source_dir, staged, iso3=iso3, version=VERSION,
                                    patch=patch, audit=audit, rules=rules)
            audit_relative = audits[iso3].relative_to(root).as_posix()
            output_hashes = {
                f"countries/{iso3}/candidates/{VERSION}/{name}": value
                for name, value in row.pop("candidate_file_hashes").items()
            }
            identity_files = {
                **{f"{source_relative}/{name}": digest for name, digest in source_hashes.items()},
                **output_hashes,
                "research/20261026_global_depth/TEST_INPUTS.json": input_manifest_hash,
                "reviews/20261027_global-depth-review-manifest.json": prior_manifest_hash,
                baseline_verification["freeze_file"]: baseline_verification["freeze_sha256_utf8_lf"],
                "research/20261027_remediation/overrides.json": overrides_hash,
                audit_relative: _text_hash(audits[iso3]),
                **audit_support_hashes,
                "scripts/remediate_depth_candidates.py": pipeline_hash,
            }
            row.update({
                "source_candidate": source_relative,
                "audit_file": audit_relative,
                "audit_sha256_utf8_lf": _text_hash(audits[iso3]),
                "override_sha256_utf8_lf": overrides_hash,
                "source_file_hashes": source_hashes,
                "candidate_file_hashes": output_hashes,
                "identity_file_hashes": dict(sorted(identity_files.items())),
                "identity_sha256_utf8_lf": _map_hash(identity_files),
                "audit_method": audit.get("method", "Automated machine-screening; not source verification."),
                "verification_summary": audit.get("verification_summary", {}),
            })
            countries.append(row)

        summary = {
            "countries": len(countries),
            "sources": sum(row["counts"]["sources"] for row in countries),
            "evidence": sum(row["counts"]["evidence"] for row in countries),
            "pathways": sum(row["counts"]["pathways"] for row in countries),
            "verified_evidence": sum(row["counts"]["evidence"] - len(row["applied_transformations"]["unverified_evidence_ids"]) for row in countries),
            "verified_pathways": sum(row["counts"]["pathways"] - len(row["applied_transformations"]["unverified_pathway_ids"]) for row in countries),
            "unverified_evidence": sum(len(row["applied_transformations"]["unverified_evidence_ids"]) for row in countries),
            "unverified_pathways": sum(len(row["applied_transformations"]["unverified_pathway_ids"]) for row in countries),
        }
        test_inputs = [f"countries/{iso3}/candidates/{VERSION}" for iso3 in sorted(input_codes)]
        staged_artifacts = {}
        test_inputs_stage = stage_root / "TEST_INPUTS.json"
        write_canonical_json(test_inputs_stage, test_inputs)
        staged_artifacts["research/20261027_remediation/TEST_INPUTS.json"] = test_inputs_stage

        ledger = {
            "artifact_kind": "unapproved-global-depth-remediation-ledger",
            "as_of": "2026-10-27",
            "candidate_version": VERSION,
            "human_approval": False,
            "audit_includes_machine_screening": True,
            "audit_scope": (
                "All records screened; selective passage checks separately documented; "
                "remaining unresolved claims retain explicit uncertainty."
            ),
            "audit_supporting_files": audit_support_hashes,
            "source_verification_and_human_approval_are_separate_gates": True,
            "global_rules": rules,
            "baseline_verification": baseline_verification,
            "summary": summary,
            "countries": countries,
        }
        ledger_stage = stage_root / "country-ledger.json"
        write_canonical_json(ledger_stage, ledger)
        staged_artifacts[OUTPUT_LEDGER.relative_to(ROOT).as_posix()] = ledger_stage

        table_text = _approval_table(countries, summary)
        table_stage = stage_root / "approval-table.md"
        table_stage.write_text(table_text, encoding="utf-8", newline="\n")
        staged_artifacts[OUTPUT_TABLE.relative_to(ROOT).as_posix()] = table_stage

        artifact_hashes = {
            relative: _text_hash(path)
            for relative, path in staged_artifacts.items()
        }
        manifest = {
            "artifact_kind": "unapproved-global-depth-remediated-review-manifest",
            "as_of": "2026-10-27",
            "candidate_version": VERSION,
            "human_approval": False,
            "reviewer": None,
            "reviewed_on": None,
            "baseline_commit": prior_manifest["baseline_commit"],
            "baseline_freeze": prior_manifest["baseline_freeze"],
            "baseline_file_count": prior_manifest["baseline_file_count"],
            "baseline_verification": baseline_verification,
            "production_release_unchanged": prior_manifest["production_release_unchanged"],
            "scope": prior_manifest["scope"],
            "hash_method": "SHA-256 of UTF-8 text with normalized LF; country identity hashes the sorted path/hash map using JSON separators ',' and ':'. Digests attest file identity, not verification or approval.",
            "source_test_inputs_manifest": SOURCE_MANIFEST.relative_to(ROOT).as_posix(),
            "source_test_inputs_sha256_utf8_lf": input_manifest_hash,
            "source_review_manifest_sha256_utf8_lf": prior_manifest_hash,
            "overrides_file": overrides_path.relative_to(root).as_posix(),
            "overrides_sha256_utf8_lf": overrides_hash,
            "pipeline_file": Path(__file__).resolve().relative_to(root).as_posix(),
            "pipeline_sha256_utf8_lf": pipeline_hash,
            "audit_directory": audits[next(iter(sorted(audits)))].parent.relative_to(root).as_posix(),
            "audit_supporting_files": audit_support_hashes,
            "summary": summary,
            "artifacts": artifact_hashes,
            "countries": countries,
        }
        manifest_stage = stage_root / "review-manifest.json"
        write_canonical_json(manifest_stage, manifest)
        staged_artifacts[OUTPUT_MANIFEST.relative_to(ROOT).as_posix()] = manifest_stage

        if not publish:
            published_roots = (*output_dirs, *artifact_paths)
            if any(path.exists() for path in published_roots):
                incomplete = [
                    str(path) for path in output_dirs if not path.is_dir()
                ] + [str(path) for path in artifact_paths if not path.is_file()]
                if incomplete:
                    raise ValueError(
                        f"published remediation is incomplete; missing={incomplete[:8]}"
                    )
                files = {
                    f"countries/{iso3}/candidates/{VERSION}/{name}": (
                        stage_root / iso3 / "candidate" / name,
                        root / "countries" / iso3 / "candidates" / VERSION / name,
                    )
                    for iso3, _, _ in inputs
                    for name in OUTPUT_FILES
                }
                files.update({
                    relative: (staged, root / relative)
                    for relative, staged in staged_artifacts.items()
                })
                _compare_published_files(files)
                matched_existing_outputs = True

        if publish:
            for iso3, _, _ in inputs:
                destination = root / "countries" / iso3 / "candidates" / VERSION
                destination.parent.mkdir(parents=True, exist_ok=True)
                (stage_root / iso3 / "candidate").rename(destination)
            for relative, staged in staged_artifacts.items():
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                staged.rename(destination)
    return {
        "summary": summary,
        "manifest": OUTPUT_MANIFEST,
        "ledger": OUTPUT_LEDGER,
        "table": OUTPUT_TABLE,
        "published": publish,
        "matched_existing_outputs": matched_existing_outputs,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-only", action="store_true",
        help="stage and validate all 146 countries without writing final artifacts",
    )
    args = parser.parse_args(argv)
    result = build_remediation(publish=not args.check_only)
    action = "Validated staged" if args.check_only else "Wrote DRAFT"
    reproduced = " Published artifacts match." if result["matched_existing_outputs"] else ""
    print(
        f"{action} remediation: {result['summary']['countries']} countries, "
        f"{result['summary']['evidence']} evidence records, {result['summary']['pathways']} pathways; "
        f"human approval pending. Manifest target: {result['manifest']}.{reproduced}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
