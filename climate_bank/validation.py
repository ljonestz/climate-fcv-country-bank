"""Deterministic schema and cross-ledger validation."""

from __future__ import annotations

from collections import Counter
from datetime import date
from functools import lru_cache
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import MappingProxyType
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"
COUNTRY_FILES = {
    "sources.json": "source.schema.json",
    "evidence.json": "evidence.schema.json",
    "pathways.json": "pathway.schema.json",
    "review.json": "review.schema.json",
}


def _read_json(path: Path) -> Any:
    """Read a UTF-8 JSON document."""
    return json.loads(path.read_text(encoding="utf-8"))


def _freeze_json(value: Any) -> Any:
    """Recursively freeze parsed JSON so cached schemas cannot be mutated."""
    if isinstance(value, dict):
        return MappingProxyType(
            {key: _freeze_json(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


@lru_cache(maxsize=None)
def _schema_document(schema_name: str) -> Any:
    return _freeze_json(_read_json(SCHEMA_DIR / schema_name))


@lru_cache(maxsize=1)
def _registry() -> Registry:
    registry = Registry()
    for path in sorted(SCHEMA_DIR.glob("*.schema.json")):
        schema = _schema_document(path.name)
        if isinstance(schema.get("$id"), str):
            registry = registry.with_resource(
                schema["$id"], Resource.from_contents(schema)
            )
    return registry


@lru_cache(maxsize=None)
def _validator(schema_name: str) -> Draft202012Validator:
    return Draft202012Validator(
        _schema_document(schema_name),
        registry=_registry(),
        format_checker=FormatChecker(),
    )


def _json_path(parts) -> str:
    path = "$"
    for part in parts:
        if isinstance(part, int):
            path += f"[{part}]"
        elif isinstance(part, str) and part.isidentifier():
            path += f".{part}"
        else:
            path += f"[{json.dumps(str(part))}]"
    return path


def _schema_errors(value: Any, schema_name: str, label: str) -> list[str]:
    """Return deterministically ordered Draft 2020-12 validation errors."""
    validator = _validator(schema_name)
    errors = [
        f"{label}: schema {_json_path(error.absolute_path)}: {error.message}"
        for error in validator.iter_errors(value)
    ]
    return sorted(set(errors))


def _duplicate_errors(records, id_field: str, label: str) -> list[str]:
    if not isinstance(records, list):
        return []
    ids = [
        record[id_field]
        for record in records
        if isinstance(record, dict) and isinstance(record.get(id_field), str)
    ]
    return [
        f"{label}: duplicate {id_field} {record_id}"
        for record_id, count in sorted(Counter(ids).items(), key=lambda item: str(item[0]))
        if record_id is not None and count > 1
    ]


def _list_duplicate_errors(values, id_field: str, label: str) -> list[str]:
    if not isinstance(values, list):
        return []
    return [
        f"{label}: duplicate {id_field} {record_id}"
        for record_id, count in sorted(Counter(value for value in values if isinstance(value, str)).items())
        if count > 1
    ]


def _is_safe_repo_path(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    if len(value) >= 2 and value[0].isalpha() and value[1] == ":":
        return False
    if PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute():
        return False
    parts = [part.lower() for part in value.replace("\\", "/").split("/")]
    return ".." not in parts and "source_documents" not in parts


def _load_country_files(country_dir: Path) -> tuple[dict[str, Any], list[str]]:
    loaded: dict[str, Any] = {}
    errors: list[str] = []
    for filename, schema_name in COUNTRY_FILES.items():
        path = country_dir / filename
        try:
            value = _read_json(path)
        except FileNotFoundError:
            errors.append(f"{filename}: missing file")
            continue
        except json.JSONDecodeError as exc:
            errors.append(
                f"{filename}: invalid JSON at line {exc.lineno} column {exc.colno}: {exc.msg}"
            )
            continue
        except (OSError, UnicodeError) as exc:
            errors.append(f"{filename}: unreadable ({type(exc).__name__}): {exc}")
            continue
        loaded[filename] = value
        errors.extend(_schema_errors(value, schema_name, filename))
    return loaded, errors


def _id_set(records: Any, field: str) -> set[str]:
    if not isinstance(records, list):
        return set()
    return {
        record[field]
        for record in records
        if isinstance(record, dict) and isinstance(record.get(field), str)
    }


def _record_index(records: Any, field: str) -> dict[str, dict[str, Any]]:
    if not isinstance(records, list):
        return {}
    return {
        record[field]: record
        for record in records
        if isinstance(record, dict) and isinstance(record.get(field), str)
    }


def _chronology_error(
    label: str, reviewed_on: Any, review_due: Any
) -> str | None:
    if not isinstance(reviewed_on, str) or not isinstance(review_due, str):
        return None
    try:
        reviewed_date = date.fromisoformat(reviewed_on)
        due_date = date.fromisoformat(review_due)
    except ValueError:
        return None
    if due_date < reviewed_date:
        return (
            f"{label}: review_due {review_due} is before reviewed_on {reviewed_on}"
        )
    return None


def _exact_ids_error(label: str, review_ids: Any, ledger_ids: set[str]) -> str | None:
    if not isinstance(review_ids, list):
        return None
    review_set = {value for value in review_ids if isinstance(value, str)}
    if review_set == ledger_ids:
        return None
    missing = sorted(ledger_ids - review_set)
    extra = sorted(review_set - ledger_ids)
    return f"review.json: {label} do not exactly match ledger IDs (missing={missing}, extra={extra})"


def validate_country_directory(country_dir: Path) -> list[str]:
    """Validate one country's ledgers without raising for content defects."""
    country_dir = Path(country_dir)
    try:
        loaded, errors = _load_country_files(country_dir)
    except Exception as exc:  # schema infrastructure failure remains a readable result
        return [f"validation infrastructure error: {type(exc).__name__}: {exc}"]

    sources = loaded.get("sources.json")
    evidence = loaded.get("evidence.json")
    pathways = loaded.get("pathways.json")
    review = loaded.get("review.json")
    errors += _duplicate_errors(sources, "source_id", "sources.json")
    errors += _duplicate_errors(evidence, "evidence_id", "evidence.json")
    errors += _duplicate_errors(pathways, "pathway_id", "pathways.json")

    source_ids = _id_set(sources, "source_id")
    evidence_ids = _id_set(evidence, "evidence_id")
    pathway_ids = _id_set(pathways, "pathway_id")
    source_index = _record_index(sources, "source_id")
    evidence_index = _record_index(evidence, "evidence_id")
    evidence_iso3 = {
        evidence_id: record.get("iso3")
        for evidence_id, record in evidence_index.items()
    }
    review_iso3 = review.get("iso3") if isinstance(review, dict) else None
    if isinstance(sources, list):
        for source in sources:
            if not isinstance(source, dict):
                continue
            source_id = source.get("source_id", "<unknown>")
            if source_id == "general-knowledge":
                errors.append("sources.json: general-knowledge may not be a source")
            if isinstance(review_iso3, str) and not str(source_id).startswith(
                f"{review_iso3}-SRC-"
            ):
                errors.append(
                    f"sources.json: {source_id} prefix must match review ISO3 {review_iso3}"
                )
            repo_file = source.get("repository_file")
            if repo_file is not None and not _is_safe_repo_path(repo_file):
                errors.append(f"sources.json: {source_id} repository_file is unsafe")

    if isinstance(evidence, list):
        for record in evidence:
            if not isinstance(record, dict):
                continue
            evidence_id = record.get("evidence_id", "<unknown>")
            if isinstance(review_iso3, str):
                if record.get("iso3") != review_iso3:
                    errors.append(f"evidence.json: {evidence_id} iso3 must equal review ISO3 {review_iso3}")
                if not str(evidence_id).startswith(f"{review_iso3}-E-"):
                    errors.append(f"evidence.json: {evidence_id} prefix must match review ISO3 {review_iso3}")
            if record.get("review_status") != "draft" and record.get("review_date") is None:
                errors.append(f"evidence.json: {evidence_id} {record.get('review_status')} status requires review_date")
            refs = record.get("source_refs")
            if isinstance(refs, list):
                for ref in refs:
                    if not isinstance(ref, dict):
                        continue
                    source_id = ref.get("source_id")
                    locator = ref.get("locator")
                    if source_id == "general-knowledge":
                        errors.append(f"evidence.json: {evidence_id} may not reference general-knowledge")
                    elif isinstance(source_id, str) and source_id not in source_ids:
                        errors.append(f"evidence.json: {evidence_id} references unknown source_id {source_id}")
                    source = source_index.get(source_id) if isinstance(source_id, str) else None
                    evidence_country = record.get("iso3")
                    if isinstance(source, dict) and isinstance(evidence_country, str):
                        country_codes = source.get("country_codes")
                        if isinstance(country_codes, list) and evidence_country not in country_codes:
                            errors.append(
                                f"evidence.json: {evidence_id} source {source_id} "
                                f"country_codes does not include {evidence_country}"
                            )
                    if not isinstance(locator, str) or not locator.strip():
                        errors.append(f"evidence.json: {evidence_id} source locator must be nonempty")

    if isinstance(pathways, list):
        for pathway in pathways:
            if not isinstance(pathway, dict):
                continue
            pathway_id = pathway.get("pathway_id", "<unknown>")
            if isinstance(review_iso3, str):
                if pathway.get("iso3") != review_iso3:
                    errors.append(f"pathways.json: {pathway_id} iso3 must equal review ISO3 {review_iso3}")
                if not str(pathway_id).startswith(f"{review_iso3}-P-"):
                    errors.append(f"pathways.json: {pathway_id} prefix must match review ISO3 {review_iso3}")
            if pathway.get("review_status") != "draft" and pathway.get("review_date") is None:
                errors.append(f"pathways.json: {pathway_id} {pathway.get('review_status')} status requires review_date")
            supporting = pathway.get("supporting_evidence_ids")
            supporting_set = (
                {item for item in supporting if isinstance(item, str)}
                if isinstance(supporting, list)
                else set()
            )
            for evidence_id in sorted(supporting_set - evidence_ids, key=str):
                errors.append(f"pathways.json: {pathway_id} supporting_evidence_ids contains unknown {evidence_id}")
            pathway_iso3 = pathway.get("iso3")
            for evidence_id in sorted(supporting_set & evidence_ids):
                evidence_country = evidence_iso3.get(evidence_id)
                if isinstance(evidence_country, str) and evidence_country != pathway_iso3:
                    errors.append(
                        f"pathways.json: {pathway_id} supporting_evidence_ids ID "
                        f"{evidence_id} belongs to {evidence_country}, not {pathway_iso3}"
                    )
            links = pathway.get("link_evidence")
            if isinstance(links, dict):
                for link_name in ("pressure", "impact", "mediator", "consequence"):
                    link_ids = links.get(link_name)
                    if not isinstance(link_ids, list):
                        continue
                    for evidence_id in sorted(
                        {item for item in link_ids if isinstance(item, str)}
                    ):
                        if evidence_id not in evidence_ids:
                            errors.append(f"pathways.json: {pathway_id} link_evidence.{link_name} contains unknown {evidence_id}")
                        if evidence_id not in supporting_set:
                            errors.append(f"pathways.json: {pathway_id} link_evidence.{link_name} ID {evidence_id} is not in supporting_evidence_ids")
                        evidence_country = evidence_iso3.get(evidence_id)
                        if isinstance(evidence_country, str) and evidence_country != pathway_iso3:
                            errors.append(
                                f"pathways.json: {pathway_id} link_evidence.{link_name} "
                                f"ID {evidence_id} belongs to {evidence_country}, not {pathway_iso3}"
                            )

    if isinstance(review, dict):
        review_evidence = review.get("evidence_ids")
        review_pathways = review.get("pathway_ids")
        errors += _list_duplicate_errors(review_evidence, "evidence_id", "review.json")
        errors += _list_duplicate_errors(review_pathways, "pathway_id", "review.json")
        for mismatch in (
            _exact_ids_error("evidence_ids", review_evidence, evidence_ids),
            _exact_ids_error("pathway_ids", review_pathways, pathway_ids),
        ):
            if mismatch:
                errors.append(mismatch)
        if not _is_safe_repo_path(review.get("dossier_path")):
            errors.append("review.json: dossier_path is unsafe")
        status = review.get("status")
        if status != "draft":
            for field in ("reviewer", "reviewed_on"):
                if review.get(field) is None:
                    errors.append(f"review.json: {status} status requires {field}")
        if status in {"approved", "stale"}:
            for field in ("review_due",):
                if review.get(field) is None:
                    errors.append(f"review.json: {status} status requires {field}")
        chronology_error = _chronology_error(
            "review.json", review.get("reviewed_on"), review.get("review_due")
        )
        if chronology_error:
            errors.append(chronology_error)
    return sorted(set(errors))


def validate_runtime_release(value: Any) -> list[str]:
    """Validate an approved runtime release and all cross-ledger references."""
    try:
        errors = _schema_errors(value, "runtime-release.schema.json", "runtime release")
    except Exception as exc:
        return [
            "runtime release: validation infrastructure error: "
            f"{type(exc).__name__}: {exc}"
        ]
    if not isinstance(value, dict):
        return errors

    sources = value.get("sources") if isinstance(value.get("sources"), list) else []
    evidence = (
        value.get("evidence_records")
        if isinstance(value.get("evidence_records"), list)
        else []
    )
    pathways = (
        value.get("pathways") if isinstance(value.get("pathways"), list) else []
    )
    countries = value.get("countries")
    countries = countries if isinstance(countries, dict) else {}

    errors += _duplicate_errors(sources, "source_id", "runtime release")
    errors += _duplicate_errors(evidence, "evidence_id", "runtime release")
    errors += _duplicate_errors(pathways, "pathway_id", "runtime release")
    source_ids = _id_set(sources, "source_id")
    evidence_ids = _id_set(evidence, "evidence_id")
    source_index = _record_index(sources, "source_id")
    evidence_index = _record_index(evidence, "evidence_id")
    evidence_iso3 = {
        evidence_id: record.get("iso3")
        for evidence_id, record in evidence_index.items()
    }
    country_codes = {iso3 for iso3 in countries if isinstance(iso3, str)}

    for record in evidence:
        if not isinstance(record, dict):
            continue
        evidence_id = record.get("evidence_id", "<unknown>")
        iso3 = record.get("iso3")
        if isinstance(iso3, str) and iso3 not in country_codes:
            errors.append(
                f"runtime release: evidence {evidence_id} references absent country {iso3}"
            )
        if (
            isinstance(evidence_id, str)
            and isinstance(iso3, str)
            and not evidence_id.startswith(f"{iso3}-E-")
        ):
            errors.append(
                f"runtime release: evidence {evidence_id} prefix must match iso3 {iso3}"
            )
        refs = record.get("source_refs")
        if isinstance(refs, list):
            for ref in refs:
                if not isinstance(ref, dict):
                    continue
                source_id = ref.get("source_id")
                if isinstance(source_id, str) and source_id not in source_ids:
                    errors.append(
                        f"runtime release: evidence {evidence_id} references "
                        f"unknown source_id {source_id}"
                    )
                source = source_index.get(source_id) if isinstance(source_id, str) else None
                if isinstance(source_id, str) and isinstance(iso3, str):
                    if not source_id.startswith(f"{iso3}-SRC-"):
                        errors.append(
                            f"runtime release: evidence {evidence_id} source_id "
                            f"{source_id} prefix must match iso3 {iso3}"
                        )
                    if isinstance(source, dict):
                        source_countries = source.get("country_codes")
                        if isinstance(source_countries, list) and iso3 not in source_countries:
                            errors.append(
                                f"runtime release: evidence {evidence_id} source "
                                f"{source_id} country_codes does not include {iso3}"
                            )

    for pathway in pathways:
        if not isinstance(pathway, dict):
            continue
        pathway_id = pathway.get("pathway_id", "<unknown>")
        iso3 = pathway.get("iso3")
        if isinstance(iso3, str) and iso3 not in country_codes:
            errors.append(
                f"runtime release: pathway {pathway_id} references absent country {iso3}"
            )
        if (
            isinstance(pathway_id, str)
            and isinstance(iso3, str)
            and not pathway_id.startswith(f"{iso3}-P-")
        ):
            errors.append(
                f"runtime release: pathway {pathway_id} prefix must match iso3 {iso3}"
            )
        supporting = pathway.get("supporting_evidence_ids")
        supporting_ids = (
            {item for item in supporting if isinstance(item, str)}
            if isinstance(supporting, list)
            else set()
        )
        for evidence_id in sorted(supporting_ids - evidence_ids):
            errors.append(
                f"runtime release: pathway {pathway_id} supporting_evidence_ids "
                f"contains unknown {evidence_id}"
            )
        for evidence_id in sorted(supporting_ids & evidence_ids):
            evidence_country = evidence_iso3.get(evidence_id)
            if isinstance(evidence_country, str) and evidence_country != iso3:
                errors.append(
                    f"runtime release: pathway {pathway_id} supporting_evidence_ids "
                    f"ID {evidence_id} belongs to {evidence_country}, not {iso3}"
                )
        links = pathway.get("link_evidence")
        if isinstance(links, dict):
            for link_name in ("pressure", "impact", "mediator", "consequence"):
                link_values = links.get(link_name)
                if not isinstance(link_values, list):
                    continue
                link_ids = {item for item in link_values if isinstance(item, str)}
                for evidence_id in sorted(link_ids):
                    if evidence_id not in evidence_ids:
                        errors.append(
                            f"runtime release: pathway {pathway_id} "
                            f"link_evidence.{link_name} contains unknown {evidence_id}"
                        )
                    if evidence_id not in supporting_ids:
                        errors.append(
                            f"runtime release: pathway {pathway_id} "
                            f"link_evidence.{link_name} ID {evidence_id} is not in "
                            "supporting_evidence_ids"
                        )
                    evidence_country = evidence_iso3.get(evidence_id)
                    if isinstance(evidence_country, str) and evidence_country != iso3:
                        errors.append(
                            f"runtime release: pathway {pathway_id} "
                            f"link_evidence.{link_name} ID {evidence_id} belongs to "
                            f"{evidence_country}, not {iso3}"
                        )

    for iso3, summary in countries.items():
        if not isinstance(summary, dict):
            continue
        if summary.get("iso3") != iso3:
            errors.append(f"runtime release: countries.{iso3}.iso3 must equal its key")
        summary_evidence = summary.get("evidence_ids")
        summary_pathways = summary.get("pathway_ids")
        errors += _list_duplicate_errors(
            summary_evidence,
            "evidence_id",
            f"runtime release: countries.{iso3}.evidence_ids",
        )
        errors += _list_duplicate_errors(
            summary_pathways,
            "pathway_id",
            f"runtime release: countries.{iso3}.pathway_ids",
        )
        country_evidence = {
            record["evidence_id"]
            for record in evidence
            if isinstance(record, dict)
            and record.get("iso3") == iso3
            and isinstance(record.get("evidence_id"), str)
        }
        country_pathways = {
            record["pathway_id"]
            for record in pathways
            if isinstance(record, dict)
            and record.get("iso3") == iso3
            and isinstance(record.get("pathway_id"), str)
        }
        for mismatch in (
            _exact_ids_error(
                f"countries.{iso3}.evidence_ids", summary_evidence, country_evidence
            ),
            _exact_ids_error(
                f"countries.{iso3}.pathway_ids", summary_pathways, country_pathways
            ),
        ):
            if mismatch:
                errors.append(
                    mismatch.replace("review.json: ", "runtime release: ")
                )
        chronology_error = _chronology_error(
            f"runtime release: countries.{iso3}",
            summary.get("reviewed_on"),
            summary.get("review_due"),
        )
        if chronology_error:
            errors.append(chronology_error)
    return sorted(set(errors))
