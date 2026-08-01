"""Build deterministic runtime releases with explicit human approval gates."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Iterable

from .validation import validate_country_directory, validate_runtime_release


SCHEMA_VERSION = "1.0.0"
CANDIDATE_SCHEMA_VERSION = "1.1.0"
CONTENT_VERSION = "2026.07.south-sudan-pilot"
_DATE_TIME_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
_WIN32_RESERVED_DEVICE_PATTERN = re.compile(
    r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$",
    re.IGNORECASE,
)
_CANDIDATE_STATUSES = frozenset({"reviewed", "approved"})
_APPROVED_STATUSES = frozenset({"approved"})
_RELEASE_INPUT_FILENAMES = (
    "sources.json",
    "evidence.json",
    "pathways.json",
    "review.json",
    "profile.json",
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


def _record_error(
    country_dir: Path, kind: str, record_id: str, detail: str
) -> ValueError:
    return ValueError(f"{country_dir}: {kind} {record_id} {detail}")


def _status_error(
    country_dir: Path,
    kind: str,
    record_id: str,
    status: Any,
    allowed_statuses: frozenset[str],
) -> ValueError:
    allowed = " or ".join(sorted(allowed_statuses))
    return _record_error(
        country_dir,
        kind,
        record_id,
        f"status {status} must be {allowed}",
    )


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


def _validate_win32_output_path(path: Path) -> None:
    output_path = Path(path)
    anchor_parts = {
        part
        for part in (output_path.anchor, output_path.drive, output_path.root)
        if part
    }
    for component in output_path.parts:
        if component in anchor_parts or component in {".", ".."}:
            continue
        if component.endswith((".", " ")):
            raise ValueError(
                f"unsafe output path component {component!r}: "
                "trailing dot or space"
            )
        if ":" in component:
            raise ValueError(
                f"unsafe output path component {component!r}: "
                "alternate data stream separator"
            )
        device_name = component.split(".", 1)[0]
        if _WIN32_RESERVED_DEVICE_PATTERN.fullmatch(device_name):
            raise ValueError(
                f"unsafe output path component {component!r}: "
                "reserved DOS device name"
            )


def _resolved_path(path: Path) -> Path:
    return Path(path).resolve(strict=False)


def _is_current_release_directory(path: Path) -> bool:
    normalized = _resolved_path(path)
    current_tail = ("releases", "current")
    path_tail = tuple(part.casefold() for part in normalized.parts[-2:])
    parent_tail = tuple(
        part.casefold() for part in normalized.parent.parts[-2:]
    )
    return path_tail == current_tail or parent_tail == current_tail


def _reject_release_input_collision(
    output_path: Path,
    country_dirs: Iterable[Path],
    *,
    candidate: bool,
) -> None:
    resolved_output = _resolved_path(output_path)
    output_label = "candidate output" if candidate else "release output"
    for country_dir in country_dirs:
        for filename in _RELEASE_INPUT_FILENAMES:
            input_path = Path(country_dir) / filename
            if resolved_output == _resolved_path(input_path):
                raise ValueError(
                    f"{output_label} {output_path} collides with release "
                    f"input {input_path}"
                )


def _validate_release_output_path(
    output_path: Path,
    country_dirs: Iterable[Path],
    *,
    candidate: bool,
) -> None:
    _validate_win32_output_path(output_path)
    if candidate and _is_current_release_directory(output_path):
        raise ValueError(
            "candidate output may not target the releases/current directory "
            "(including releases/current/runtime.json)"
        )
    _reject_release_input_collision(
        output_path,
        country_dirs,
        candidate=candidate,
    )


def _validate_review_due(
    country_dir: Path,
    review: dict[str, Any],
    generated: datetime,
    generated_at: str,
) -> None:
    review_due = review.get("review_due")
    try:
        due = datetime.fromisoformat(review_due).date()
    except (TypeError, ValueError) as exc:
        raise _record_error(
            country_dir,
            "country",
            review.get("iso3", "<unknown>"),
            "requires a valid review_due for release construction",
        ) from exc
    if due < generated.date():
        raise ValueError(
            f"{country_dir}: review_due {review_due} is earlier "
            f"than generated_at calendar date {generated_at[:10]}"
        )


def _validate_approval_date(
    country_dir: Path,
    kind: str,
    record_id: str,
    field_name: str,
    value: Any,
    generated: datetime,
    generated_at: str,
) -> None:
    if not isinstance(value, str):
        return
    try:
        approval_date = datetime.fromisoformat(value).date()
    except ValueError:
        return
    if approval_date > generated.date():
        raise _record_error(
            country_dir,
            kind,
            record_id,
            f"{field_name} {value} is later than generated_at calendar "
            f"date {generated_at[:10]}",
        )


def _collect_inputs(
    country_dirs: Iterable[Path],
    *,
    generated: datetime,
    generated_at: str,
    schema_version: str,
    candidate: bool | None,
) -> list[
    tuple[
        Path,
        dict[str, Any],
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        dict[str, Any] | None,
    ]
]:
    inputs = []
    is_v1_1 = schema_version == CANDIDATE_SCHEMA_VERSION
    allowed_statuses = (
        _CANDIDATE_STATUSES if candidate is True else _APPROVED_STATUSES
    )

    for country_dir in sorted(
        (Path(path) for path in country_dirs),
        key=lambda path: str(path),
    ):
        errors = validate_country_directory(
            country_dir,
            require_profile=is_v1_1,
            schema_version=schema_version,
            as_of=generated.date() if is_v1_1 else None,
        )
        if errors:
            raise _country_validation_error(country_dir, errors)

        review = _read_json(country_dir / "review.json")
        if not is_v1_1 and review["status"] != "approved":
            continue

        sources = _read_json(country_dir / "sources.json")
        evidence = _read_json(country_dir / "evidence.json")
        pathways = _read_json(country_dir / "pathways.json")
        profile = _read_json(country_dir / "profile.json") if is_v1_1 else None

        iso3 = review["iso3"]
        if review["status"] not in allowed_statuses:
            raise _status_error(
                country_dir,
                "country",
                iso3,
                review["status"],
                allowed_statuses,
            )
        _validate_approval_date(
            country_dir,
            "country",
            iso3,
            "reviewed_on",
            review["reviewed_on"],
            generated,
            generated_at,
        )
        _validate_review_due(country_dir, review, generated, generated_at)

        if profile is not None and profile["review_status"] not in allowed_statuses:
            raise _status_error(
                country_dir,
                "profile",
                iso3,
                profile["review_status"],
                allowed_statuses,
            )
        if profile is not None:
            _validate_approval_date(
                country_dir,
                "profile",
                iso3,
                "review_date",
                profile["review_date"],
                generated,
                generated_at,
            )

        for record in evidence:
            record_id = record["evidence_id"]
            if record["review_status"] not in allowed_statuses:
                raise _status_error(
                    country_dir,
                    "evidence",
                    record_id,
                    record["review_status"],
                    allowed_statuses,
                )
            if record["review_date"] is None:
                raise _record_error(
                    country_dir,
                    "evidence",
                    record_id,
                    "must have a non-null review_date",
                )
            _validate_approval_date(
                country_dir,
                "evidence",
                record_id,
                "review_date",
                record["review_date"],
                generated,
                generated_at,
            )
        for record in pathways:
            record_id = record["pathway_id"]
            if record["review_status"] not in allowed_statuses:
                raise _status_error(
                    country_dir,
                    "pathway",
                    record_id,
                    record["review_status"],
                    allowed_statuses,
                )
            if record["review_date"] is None:
                raise _record_error(
                    country_dir,
                    "pathway",
                    record_id,
                    "must have a non-null review_date",
                )
            _validate_approval_date(
                country_dir,
                "pathway",
                record_id,
                "review_date",
                record["review_date"],
                generated,
                generated_at,
            )

        inputs.append(
            (country_dir, review, sources, evidence, pathways, profile)
        )

    if not inputs:
        if is_v1_1 and candidate is True:
            raise ValueError("no reviewed or approved candidate country content")
        raise ValueError("no approved country content")
    return inputs


def _construct_release(
    country_dirs: Iterable[Path],
    *,
    generated_at: str,
    schema_version: str,
    content_version: str,
    candidate: bool | None,
) -> dict[str, Any]:
    generated = _parse_generated_at(generated_at)
    if schema_version not in {SCHEMA_VERSION, CANDIDATE_SCHEMA_VERSION}:
        raise ValueError(f"unsupported schema_version {schema_version}")
    if not isinstance(content_version, str) or not content_version.strip():
        raise ValueError("content_version must be a non-empty string")

    inputs = _collect_inputs(
        country_dirs,
        generated=generated,
        generated_at=generated_at,
        schema_version=schema_version,
        candidate=candidate,
    )

    countries: dict[str, dict[str, Any]] = {}
    sources_by_id: dict[str, dict[str, Any]] = {}
    evidence_records: list[dict[str, Any]] = []
    pathway_records: list[dict[str, Any]] = []

    for country_dir, review, sources, evidence, pathways, profile in sorted(
        inputs, key=lambda item: item[1]["iso3"]
    ):
        iso3 = review["iso3"]
        if iso3 in countries:
            raise ValueError(
                f"{country_dir}: duplicate country ISO3 {iso3} in release inputs"
            )

        summary = {
            "iso3": iso3,
            "name": review["country_name"],
            "aliases": sorted(review["country_aliases"]),
            "status": review["status"],
            "reviewer": review["reviewer"],
            "reviewed_on": review["reviewed_on"],
            "review_due": review["review_due"],
            "dossier_path": review["dossier_path"],
            "evidence_ids": sorted(review["evidence_ids"]),
            "pathway_ids": sorted(review["pathway_ids"]),
            "decision_notes": review["decision_notes"],
        }
        if schema_version == CANDIDATE_SCHEMA_VERSION:
            assert profile is not None
            summary["selection_aliases"] = deepcopy(
                profile["selection_aliases"]
            )
        countries[iso3] = summary

        referenced_source_ids = {
            ref["source_id"] for record in evidence for ref in record["source_refs"]
        }
        source_index = {source["source_id"]: source for source in sources}
        for source_id in sorted(referenced_source_ids):
            source = deepcopy(source_index[source_id])
            existing = sources_by_id.get(source_id)
            if existing is not None and existing != source:
                raise ValueError(
                    f"{country_dir}: conflicting duplicate source definition "
                    f"for {source_id}"
                )
            sources_by_id[source_id] = source

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
        "schema_version": schema_version,
        "content_version": content_version,
        "generated_at": generated_at,
        "countries": countries,
        "sources": canonical_sources,
        "evidence_records": evidence_records,
        "pathways": pathway_records,
        "source_manifest_checksum": hashlib.sha256(manifest_payload).hexdigest(),
    }
    if schema_version == CANDIDATE_SCHEMA_VERSION:
        release["candidate"] = bool(candidate)

    errors = validate_runtime_release(release)
    if errors:
        raise ValueError(
            "runtime release validation failed: " + "; ".join(sorted(set(errors)))
        )
    return release


def build_release(
    country_dirs: Iterable[Path],
    *,
    generated_at: str,
    schema_version: str = SCHEMA_VERSION,
    content_version: str = CONTENT_VERSION,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Build a legacy 1.0 release or an explicit schema 1.1 candidate."""
    materialized_country_dirs = tuple(Path(path) for path in country_dirs)
    if schema_version not in {SCHEMA_VERSION, CANDIDATE_SCHEMA_VERSION}:
        raise ValueError(f"unsupported schema_version {schema_version}")

    if schema_version == CANDIDATE_SCHEMA_VERSION:
        if output_path is None:
            raise ValueError(
                "schema 1.1 candidate build requires an explicit output_path"
            )
        candidate_output = Path(output_path)
        _validate_release_output_path(
            candidate_output,
            materialized_country_dirs,
            candidate=True,
        )
        release = _construct_release(
            materialized_country_dirs,
            generated_at=generated_at,
            schema_version=schema_version,
            content_version=content_version,
            candidate=True,
        )
        write_canonical_json(candidate_output, release)
        return release

    legacy_output = Path(output_path) if output_path is not None else None
    if legacy_output is not None:
        _validate_release_output_path(
            legacy_output,
            materialized_country_dirs,
            candidate=False,
        )
    release = _construct_release(
        materialized_country_dirs,
        generated_at=generated_at,
        schema_version=schema_version,
        content_version=content_version,
        candidate=None,
    )
    if legacy_output is not None:
        write_canonical_json(legacy_output, release)
    return release


def promote_release(
    country_dirs: Iterable[Path],
    *,
    generated_at: str,
    content_version: str,
    current_dir: Path,
) -> dict[str, Any]:
    """Promote only fully approved schema 1.1 inputs without changing statuses."""
    materialized_country_dirs = tuple(Path(path) for path in country_dirs)
    output_path = Path(current_dir) / "runtime.json"
    _validate_release_output_path(
        output_path,
        materialized_country_dirs,
        candidate=False,
    )
    release = _construct_release(
        materialized_country_dirs,
        generated_at=generated_at,
        schema_version=CANDIDATE_SCHEMA_VERSION,
        content_version=content_version,
        candidate=False,
    )
    write_canonical_json(output_path, release)
    return release


def write_canonical_json(path: Path, value: Any) -> None:
    """Atomically write deterministic pretty JSON terminated by one newline."""
    path = Path(path)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
