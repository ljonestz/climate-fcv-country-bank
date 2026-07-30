"""Build deterministic runtime releases from human-approved country ledgers."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable

from .validation import validate_country_directory, validate_runtime_release


SCHEMA_VERSION = "1.0.0"
CONTENT_VERSION = "2026.07.south-sudan-pilot"
_DATE_TIME_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


def _parse_generated_at(value: str) -> datetime:
    """Parse a canonical ISO date-time while retaining the caller's string."""
    if not isinstance(value, str) or not _DATE_TIME_PATTERN.fullmatch(value):
        raise ValueError("generated_at must be a canonical ISO date-time")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            "generated_at must be a canonical ISO date-time"
        ) from exc
    if parsed.tzinfo is None:
        raise ValueError("generated_at must be a canonical ISO date-time")
    return parsed


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _country_validation_error(country_dir: Path, errors: list[str]) -> ValueError:
    joined = "; ".join(sorted(set(errors)))
    return ValueError(f"{country_dir}: {joined}")


def _approved_record_error(
    country_dir: Path, kind: str, record_id: str, detail: str
) -> ValueError:
    return ValueError(f"{country_dir}: {kind} {record_id} {detail}")


def _canonical_evidence(record: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(record)
    result["source_refs"] = sorted(
        result["source_refs"],
        key=lambda ref: (ref["source_id"], ref["locator"]),
    )
    return result


def _canonical_pathway(record: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(record)
    result["supporting_evidence_ids"] = sorted(result["supporting_evidence_ids"])
    result["link_evidence"] = {
        key: sorted(result["link_evidence"][key])
        for key in ("pressure", "impact", "mediator", "consequence")
    }
    return result


def build_release(
    country_dirs: Iterable[Path], *, generated_at: str
) -> dict[str, Any]:
    """Build a schema-valid release containing only fully approved countries."""
    generated = _parse_generated_at(generated_at)
    approved_inputs: list[
        tuple[
            Path,
            dict[str, Any],
            list[dict[str, Any]],
            list[dict[str, Any]],
            list[dict[str, Any]],
        ]
    ] = []

    for country_dir in sorted(
        (Path(path) for path in country_dirs),
        key=lambda path: str(path),
    ):
        errors = validate_country_directory(country_dir)
        if errors:
            raise _country_validation_error(country_dir, errors)

        review = _read_json(country_dir / "review.json")
        if review["status"] != "approved":
            continue
        sources = _read_json(country_dir / "sources.json")
        evidence = _read_json(country_dir / "evidence.json")
        pathways = _read_json(country_dir / "pathways.json")

        if datetime.fromisoformat(review["review_due"]).date() < generated.date():
            raise ValueError(
                f"{country_dir}: review_due {review['review_due']} is earlier "
                f"than generated_at calendar date {generated_at[:10]}"
            )

        for record in evidence:
            record_id = record["evidence_id"]
            if record["review_status"] != "approved":
                raise _approved_record_error(
                    country_dir,
                    "evidence",
                    record_id,
                    "must be approved for an approved country",
                )
            if record["review_date"] is None:
                raise _approved_record_error(
                    country_dir,
                    "evidence",
                    record_id,
                    "must have a non-null review_date",
                )
        for record in pathways:
            record_id = record["pathway_id"]
            if record["review_status"] != "approved":
                raise _approved_record_error(
                    country_dir,
                    "pathway",
                    record_id,
                    "must be approved for an approved country",
                )
            if record["review_date"] is None:
                raise _approved_record_error(
                    country_dir,
                    "pathway",
                    record_id,
                    "must have a non-null review_date",
                )

        approved_inputs.append((country_dir, review, sources, evidence, pathways))

    if not approved_inputs:
        raise ValueError("no approved country content")

    countries: dict[str, dict[str, Any]] = {}
    sources_by_id: dict[str, dict[str, Any]] = {}
    evidence_records: list[dict[str, Any]] = []
    pathway_records: list[dict[str, Any]] = []

    for country_dir, review, sources, evidence, pathways in sorted(
        approved_inputs, key=lambda item: item[1]["iso3"]
    ):
        iso3 = review["iso3"]
        if iso3 in countries:
            raise ValueError(
                f"{country_dir}: duplicate country ISO3 {iso3} in release inputs"
            )

        countries[iso3] = {
            "iso3": iso3,
            "name": review["country_name"],
            "aliases": sorted(review["country_aliases"]),
            "status": "approved",
            "reviewer": review["reviewer"],
            "reviewed_on": review["reviewed_on"],
            "review_due": review["review_due"],
            "dossier_path": review["dossier_path"],
            "evidence_ids": sorted(review["evidence_ids"]),
            "pathway_ids": sorted(review["pathway_ids"]),
            "decision_notes": review["decision_notes"],
        }

        referenced_source_ids = {
            ref["source_id"] for record in evidence for ref in record["source_refs"]
        }
        source_index = {source["source_id"]: source for source in sources}
        for source_id in sorted(referenced_source_ids):
            candidate = deepcopy(source_index[source_id])
            existing = sources_by_id.get(source_id)
            if existing is not None and existing != candidate:
                raise ValueError(
                    f"{country_dir}: conflicting duplicate source definition "
                    f"for {source_id}"
                )
            sources_by_id[source_id] = candidate

        evidence_records.extend(_canonical_evidence(record) for record in evidence)
        pathway_records.extend(_canonical_pathway(record) for record in pathways)

    canonical_sources = [
        sources_by_id[source_id] for source_id in sorted(sources_by_id)
    ]
    evidence_records.sort(key=lambda record: record["evidence_id"])
    pathway_records.sort(key=lambda record: record["pathway_id"])
    manifest_sources = [
        {key: value for key, value in source.items() if key != "checksum"}
        for source in canonical_sources
    ]
    manifest_payload = json.dumps(
        manifest_sources,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    release = {
        "schema_version": SCHEMA_VERSION,
        "content_version": CONTENT_VERSION,
        "generated_at": generated_at,
        "countries": countries,
        "sources": canonical_sources,
        "evidence_records": evidence_records,
        "pathways": pathway_records,
        "source_manifest_checksum": hashlib.sha256(manifest_payload).hexdigest(),
    }
    errors = validate_runtime_release(release)
    if errors:
        raise ValueError(
            "runtime release validation failed: " + "; ".join(sorted(set(errors)))
        )
    return release


def write_canonical_json(path: Path, value: Any) -> None:
    """Write deterministic pretty JSON terminated by one newline."""
    path = Path(path)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
