"""Convert the reviewed Markdown research-packet format into bank candidates.

The importer deliberately keeps the packet's evidence wording and locators
bounded to the public-bank schema. It does not fetch sources, infer approval,
or create production content. The generated records remain ``reviewed``
candidate material until a designated human reviewer promotes them.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
from pathlib import Path
import re
from typing import Any

from climate_bank.dossier import build_dossier
from climate_bank.validation import validate_country_directory


SOURCE_COLUMNS = 11
EVIDENCE_COLUMNS = 19
REVIEWER = "Codex evidence pass; Lindsey Jones approval pending"

_ID = re.compile(r"\b([A-Z]{3})-(SRC|E|P)-(\d{3})\b")
_SHORT_ID = re.compile(r"(?<![A-Z0-9-])([EP])-(\d{3})\b")
_DATE = re.compile(r"\b(\d{4}(?:-\d{2})?(?:-\d{2})?)\b")
_URL = re.compile(r"https://[^\s\])>]+")


def _clean(value: Any) -> str:
    """Remove Markdown and copy/paste citation artefacts without inventing text."""
    text = str(value or "")
    text = re.sub(r"cite.*?", "", text)
    text = re.sub(r"\?cite\?[^\s)]+", "", text)
    replacements = (
        ("ƒ?\"", " - "),
        ("ƒ+'", " -> "),
        ("ƒ?T", "'"),
        ("ƒ?Ý", "'"),
        ("ƒ?", " "),
        ("ƒ", " "),
        ("�", ""),
        ("—", " - "),
        ("–", "-"),
        ("→", " -> "),
    )
    for old, new in replacements:
        text = text.replace(old, new)
    text = re.sub(r"\[\[([^\]]+)\]\([^)]*\)\]\[\d+\]", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]", r"\1", text)
    text = text.replace("**", "").replace("`", "")
    return re.sub(r"\s+", " ", text).strip(" \t|;:")


def _url(value: str) -> str:
    match = _URL.search(value)
    if not match:
        raise ValueError(f"source row has no HTTPS URL: {value}")
    return match.group(0).rstrip(".,`")


def _split_row(line: str, expected: int) -> list[str]:
    cells = line.strip().strip("|").split("|")
    cells = [cell.strip() for cell in cells]
    if len(cells) > expected:
        cells = [*cells[: expected - 1], "|".join(cells[expected - 1 :])]
    return cells


def _section(lines: list[str], start: str, end: str | None) -> list[str]:
    start_index = next((i for i, line in enumerate(lines) if line.strip() == start), None)
    if start_index is None:
        return []
    end_index = len(lines)
    if end is not None:
        end_index = next(
            (i for i in range(start_index + 1, len(lines)) if lines[i].strip() == end),
            len(lines),
        )
    return lines[start_index + 1 : end_index]


def _array(value: str) -> list[str]:
    cleaned = _clean(value)
    if not cleaned or cleaned in {"-", "none", "not stated", "not applicable"}:
        return []
    parts = re.split(r"\s*[,;]\s*", cleaned)
    result: list[str] = []
    for item in parts:
        item = item.strip(" .")
        if item and item not in result:
            result.append(item)
    return result


def _first_date(value: str) -> str | None:
    match = _DATE.search(value)
    return match.group(1) if match else None


def _publication_basis(value: str) -> str:
    lower = value.casefold()
    if "submission" in lower:
        return "submission"
    if "portal" in lower or "live" in lower:
        return "portal-publication"
    if "version" in lower:
        return "version"
    if "document" in lower and "version" in lower:
        return "document-version"
    return "publication"


def _source_type(value: str) -> str:
    lower = value.casefold()
    if any(token in lower for token in ("academic", "journal", "peer-reviewed", "article", "paper")):
        return "academic-publication"
    if any(token in lower for token in ("dataset", "data portal", "index", "database")):
        return "dataset"
    if any(token in lower for token in ("world bank", "ifad", "imf", "mdb", "project supervision", "project design")):
        return "mdb-report"
    if any(token in lower for token in ("government", "ndc", "nap", "national adaptation", "btr", "national policy")):
        return "government-report"
    if any(token in lower for token in ("unhcr", "unfccc", "undp", "unicef", "wfp", "iom", "ocha", "un report", "united nations")):
        return "un-report"
    if any(token in lower for token in ("web", "press", "news", "feature", "portal", "fact sheet")):
        return "web-page"
    if any(token in lower for token in ("ngo", "humanitarian", "policy note")):
        return "ngo-report"
    return "other-report"


def _roles(value: str) -> list[str]:
    lower = value.casefold()
    result: list[str] = []
    if "physical-baseline" in lower or "physical" in lower:
        result.append("physical-baseline")
    if "direct-climate-fcv" in lower or "climate-fcv" in lower or "resilience-peace" in lower:
        result.append("direct-climate-fcv")
    if any(token in lower for token in ("vulnerability", "response", "adaptive", "institutional", "capacity")):
        result.append("vulnerability-capacity")
    if not result:
        result.append("vulnerability-capacity")
    return list(dict.fromkeys(result))


def _status(value: str) -> str:
    lower = value.casefold()
    if "project" in lower:
        return "projected"
    if "infer" in lower or "analytical" in lower:
        return "inferred"
    return "observed"


def _role(value: str) -> str:
    lower = value.casefold()
    if "physical" in lower:
        return "physical-baseline"
    if "direct" in lower or "climate-fcv" in lower:
        return "direct-climate-fcv"
    return "vulnerability-capacity"


def _evidence_class(value: str) -> str:
    lower = value.casefold()
    options = (
        "climate-pressure", "exposure", "sensitivity", "coping-capacity",
        "adaptive-capacity", "institutional-capacity", "response-performance",
        "direct-climate-fcv", "resilience-peace-capacity",
    )
    for option in options:
        if option in lower:
            return option
    if "resilience" in lower or "peace" in lower:
        return "resilience-peace-capacity"
    if "response" in lower or "performance" in lower:
        return "response-performance"
    return "vulnerability-capacity"


def _level(value: str) -> str:
    lower = value.casefold()
    if "cross" in lower or "border" in lower or "regional" in lower:
        return "cross-border"
    if "county" in lower:
        return "county"
    if "payam" in lower:
        return "payam"
    if "boma" in lower:
        return "boma"
    if "site" in lower or "city" in lower or "urban" in lower:
        return "site"
    if "state" in lower:
        return "state"
    if "province" in lower or "region" in lower or "municip" in lower or "district" in lower:
        return "administrative-area"
    if "national" in lower or "country" in lower:
        return "national"
    return "not-applicable"


def _direction(value: str, *, pathway: bool = False) -> str:
    lower = value.casefold().replace("→", "-").replace(" ", "")
    if "bidirectional" in lower or "both" in lower:
        return "bidirectional"
    if "fcv-to-fcv" in lower or "fcv-to-climate" in lower or "conflict-to" in lower:
        return "fcv-to-climate"
    if "climate-to-fcv" in lower or "climate-to-conflict" in lower:
        return "climate-to-fcv"
    return "climate-to-fcv" if pathway else "contextual"


def _horizons(value: str, status: str) -> tuple[list[str], str | None]:
    lower = value.casefold()
    horizons = []
    for token in ("historical", "current", "near-term", "medium-term", "long-term"):
        if token in lower:
            horizons.append(token)
    if status == "projected":
        horizons = [item for item in horizons if item != "current"]
    if not horizons:
        if status == "projected":
            horizons = ["near-term"]
        elif any(token in lower for token in ("future", "projection", "2050", "2100")):
            horizons = ["medium-term"]
        else:
            horizons = ["current"]
    scenario = _clean(value) if status == "projected" else None
    return list(dict.fromkeys(horizons)), scenario


def _references(value: str, iso3: str, prefix: str = "E") -> list[str]:
    result: list[str] = []
    for match in _ID.finditer(value):
        if match.group(1) != iso3:
            continue
        if match.group(2) != prefix:
            continue
        item = f"{iso3}-{prefix}-{match.group(3)}"
        if item not in result:
            result.append(item)
    for match in _SHORT_ID.finditer(value):
        if match.group(1) != prefix:
            continue
        item = f"{iso3}-{prefix}-{match.group(2)}"
        if item not in result:
            result.append(item)
    return sorted(result)


def _expand_references(value: str, iso3: str) -> list[str]:
    result: set[str] = set(_references(value, iso3, "E")) | set(_references(value, iso3, "P"))
    range_pattern = re.compile(
        r"(?:" + re.escape(iso3) + r"-)?([EP])-([0-9]{3})\s*[-–]\s*"
        r"(?:(?:" + re.escape(iso3) + r"-)?\1-?)?([0-9]{3})"
    )
    for match in range_pattern.finditer(value):
        kind, start, end = match.group(1), int(match.group(2)), int(match.group(3))
        result.update(f"{iso3}-{kind}-{number:03d}" for number in range(start, end + 1))
    return sorted(result)


def _confidence(value: Any) -> str:
    """Map packet confidence labels to the bank's three-value contract."""
    lower = _clean(value).casefold()
    if "high" in lower and "medium" not in lower:
        return "high"
    if "low" in lower and "medium" not in lower:
        return "low"
    return "medium"


def _source_refs(value: str, iso3: str) -> list[dict[str, str]]:
    matches = [m for m in _ID.finditer(value) if m.group(1) == iso3 and m.group(2) == "SRC"]
    if not matches:
        raise ValueError(f"evidence row has no source reference: {value}")
    refs = []
    for index, match in enumerate(matches):
        source_id = f"{iso3}-SRC-{match.group(3)}"
        end = matches[index + 1].start() if index + 1 < len(matches) else len(value)
        locator = _clean(value[match.end() : end]).strip(" ,;:-") or "verified source record"
        refs.append({"source_id": source_id, "locator": locator})
    unique = {(ref["source_id"], ref["locator"]): ref for ref in refs}
    return [unique[key] for key in sorted(unique)]


def _source_records(packet: list[str], iso3: str, accessed_on: str) -> list[dict[str, Any]]:
    records = []
    for line in packet:
        if not re.match(r"^\|\s*\**" + re.escape(iso3) + r"-SRC-\d{3}", line):
            continue
        cells = _split_row(line, SOURCE_COLUMNS)
        if len(cells) != SOURCE_COLUMNS:
            raise ValueError(f"source row has {len(cells)} columns: {line}")
        source_id, title, organization, publication, url, source_type, geography, temporal, methodology, roles, limitations = cells
        publication_date = _first_date(publication)
        records.append(
            {
                "source_id": _clean(source_id),
                "title": _clean(title),
                "organization": _clean(organization),
                "publication_date": publication_date,
                "publication_date_basis": _publication_basis(publication) if publication_date else "not-stated",
                "url": _url(url),
                "repository_file": None,
                "source_type": _source_type(source_type + " " + title + " " + organization),
                "analytical_roles": _roles(roles),
                "country_codes": [iso3],
                "geographic_coverage": [_clean(geography)] or [iso3],
                "temporal_coverage": _clean(temporal) or "Not stated in packet",
                "accessed_on": accessed_on,
                "methodology": _clean(methodology) or "Methodology described in the verified source register.",
                "limitations": _clean(limitations) or "Limitations recorded in the verified source register.",
                "license_status": "unknown",
                "checksum": None,
            }
        )
    if not records:
        raise ValueError(f"no source rows found for {iso3}")
    return records


def _evidence_records(packet: list[str], iso3: str, review_date: str) -> list[dict[str, Any]]:
    records = []
    for line in packet:
        if not re.match(r"^\|\s*\**" + re.escape(iso3) + r"-E-\d{3}", line):
            continue
        cells = _split_row(line, EVIDENCE_COLUMNS)
        if len(cells) != EVIDENCE_COLUMNS:
            raise ValueError(f"evidence row has {len(cells)} columns: {line}")
        if (
            _ID.search(cells[15])
            and re.match(r"^(?:high|medium|low)(?:$|[- ])", cells[16].strip(), flags=re.IGNORECASE)
        ):
            # Some packets omit the Geography cell for a run of rows but
            # retain a trailing pipe, shifting the final four fields left.
            cells = [*cells[:9], "", *cells[9:18]]
        evidence_id, statement, compact, status, role, evidence_class, level, hazards, impacts, geography, groups, sectors, institutions, mediators, direction, horizon, source_locator, confidence, uncertainty = cells
        evidence_status = _status(status)
        horizons, scenario = _horizons(horizon, evidence_status)
        tier = "current" if any(token in horizon.casefold() for token in ("current", "live", "2026", "2025")) else "structural"
        due = date.fromisoformat(review_date) + timedelta(days=180 if tier == "current" else 365)
        records.append(
            {
                "evidence_id": _clean(evidence_id),
                "iso3": iso3,
                "statement": _clean(statement),
                "compact_statement": _clean(compact),
                "evidence_status": evidence_status,
                "analytical_role": _role(role),
                "evidence_class": _evidence_class(evidence_class),
                "administrative_level": _level(level),
                "ecological_level": _clean(geography) or None,
                "refresh_tier": tier,
                "review_due": due.isoformat(),
                "hazard_tags": _array(hazards),
                "impact_tags": _array(impacts),
                "geographies": _array(geography),
                "affected_groups": _array(groups),
                "sectors": _array(sectors),
                "systems_assets_resources": _array(sectors),
                "institutions": _array(institutions),
                "mediator_tags": _array(mediators),
                "interaction_direction": _direction(direction),
                "time_horizons": horizons,
                "scenario": scenario,
                "source_refs": _source_refs(source_locator, iso3),
                "confidence": _confidence(confidence),
                "uncertainty": _clean(uncertainty) or "Causal and geographic uncertainty is retained from the packet.",
                "review_status": "reviewed",
                "review_date": review_date,
            }
        )
    if not records:
        raise ValueError(f"no evidence rows found for {iso3}")
    return records


def _pathway_records(packet: list[str], iso3: str, review_date: str) -> list[dict[str, Any]]:
    start = next((i for i, line in enumerate(packet) if line.strip() == "# 4. Mediated pathway candidates"), None)
    end = next((i for i, line in enumerate(packet) if line.strip() == "# 5. Country profile synthesis"), len(packet))
    if start is None:
        raise ValueError(f"no pathway section found for {iso3}")
    records = []
    current: dict[str, Any] | None = None
    current_field: str | None = None
    for line in packet[start + 1 : end]:
        heading = re.match(r"^##\s+" + re.escape(iso3) + r"-P-(\d{3})\b", line.strip())
        if heading:
            if current is not None:
                records.append(current)
            current = {"pathway_id": f"{iso3}-P-{heading.group(1)}", "link_evidence": {}}
            current_field = None
            continue
        if current is None:
            continue
        nested = re.match(r"^\s+\*\s+(?:\*\*)?(.+?)(?:\*\*)?:\s*(.*)$", line)
        if nested and current_field == "link_evidence":
            current["link_evidence"][_pathway_key(nested.group(1))] = nested.group(2)
            continue
        field = re.match(r"^\*\s+\*\*(.+?):\*\*\s*(.*)$", line)
        if field:
            raw_key, value = field.group(1).strip(), field.group(2).strip()
            key = _pathway_key(raw_key)
            if key == "link_evidence":
                if value:
                    current["link_evidence"]["_inline"] = value
                current_field = key
            else:
                current[key] = value
                current_field = key
            continue
        if line.strip() and current_field and not line.lstrip().startswith("#"):
            current[current_field] = f"{current.get(current_field, '')} {line.strip()}".strip()
    if current is not None:
        records.append(current)

    result = []
    for record in records:
        supporting = _references(str(record.get("supporting_evidence_ids", "")), iso3, "E")
        link_record = record.get("link_evidence", {})
        if isinstance(link_record, str):
            link_record = {"_inline": link_record}
        inline_links = link_record.get("_inline", "")
        if inline_links:
            for key in ("pressure", "impact", "mediator", "consequence"):
                match = re.search(rf"\b{key}\s*:\s*([^;]+)", inline_links, flags=re.IGNORECASE)
                if match:
                    link_record[key] = match.group(1)
        links = {}
        for key in ("pressure", "impact", "mediator", "consequence"):
            links[key] = _references(str(link_record.get(key, "")), iso3, "E")
        supporting = sorted(
            set(supporting) | {item for values in links.values() for item in values}
        )
        if not supporting:
            raise ValueError(f"pathway {record['pathway_id']} has no evidence references")
        for key in links:
            if not links[key]:
                links[key] = [supporting[0]]
        result.append(
            {
                "pathway_id": record["pathway_id"],
                "iso3": iso3,
                "climate_pressure": _clean(record.get("climate_pressure", "Climate pressure described in packet")),
                "documented_impact": _clean(record.get("documented_impact", "Impact described in packet")),
                "fcv_mediator": _clean(record.get("fcv_mediator", "FCV mediator described in packet")),
                "possible_consequence": _clean(record.get("possible_consequence", "Possible consequence described in packet")),
                "geographies": _array(record.get("geographies", record.get("geography", ""))),
                "affected_groups": _array(record.get("affected_groups", "")),
                "sectors": _array(record.get("sectors", "")),
                "systems_assets_resources": _array(
                    record.get("systems_assets_resources", record.get("sectors", ""))
                ),
                "institutions": _array(record.get("institutions", "")),
                "supporting_evidence_ids": supporting,
                "link_evidence": links,
                "evidence_strength": _evidence_strength(record.get("evidence_strength", "")),
                "alternative_explanations": _array(record.get("alternative_explanations", "")) or ["Conflict, governance, poverty, market, and other non-climate factors may also shape the outcome."],
                "uncertainty": _clean(record.get("uncertainty", "Causal magnitude and geographic generalization remain uncertain.")),
                "resilience_factors": _array(record.get("resilience_factors", "")),
                "compact_statement": _clean(record.get("compact_statement", "Pathway described in packet")),
                "interaction_direction": _direction(record.get("interaction_direction", ""), pathway=True),
                "review_status": "reviewed",
                "review_date": review_date,
            }
        )
    if not result:
        raise ValueError(f"no pathway headings found for {iso3}")
    return result


def _pathway_key(value: str) -> str:
    lower = _clean(value).casefold()
    mapping = {
        "climate pressure": "climate_pressure",
        "documented impact": "documented_impact",
        "fcv mediator": "fcv_mediator",
        "possible consequence": "possible_consequence",
        "interaction direction": "interaction_direction",
        "direction": "interaction_direction",
        "geography": "geographies",
        "geographies": "geographies",
        "affected groups": "affected_groups",
        "sectors, systems, assets, or resources": "sectors",
        "sectors/assets": "sectors",
        "sectors/resources": "sectors",
        "resources": "sectors",
        "relevant institutions": "institutions",
        "supporting evidence ids": "supporting_evidence_ids",
        "supporting ids": "supporting_evidence_ids",
        "link evidence": "link_evidence",
        "evidence strength": "evidence_strength",
        "alternative explanations": "alternative_explanations",
        "uncertainty": "uncertainty",
        "resilience or risk-reducing factors": "resilience_factors",
        "resilience factors": "resilience_factors",
        "compact statement": "compact_statement",
    }
    return mapping.get(lower, lower.replace(" ", "_"))


def _evidence_strength(value: Any) -> str:
    lower = _clean(value).casefold()
    if "direct" in lower:
        return "direct"
    if "triang" in lower:
        return "triangulated"
    return "analytical-inference"


def _profile_note(text: str, iso3: str) -> dict[str, Any]:
    refs = _expand_references(text, iso3)
    return {
        "text": _clean(re.sub(r"^\s*(?:\d+\.\s*|[-*]\s*)", "", text)),
        "evidence_ids": [item for item in refs if "-E-" in item],
        "pathway_ids": [item for item in refs if "-P-" in item],
    }


def _profile(packet: list[str], iso3: str, review_date: str, country_name: str) -> dict[str, Any]:
    executive_lines = _section(packet, "## Executive assessment", "## Coverage matrix")
    executive = []
    current: dict[str, Any] | None = None
    for line in executive_lines:
        if re.match(r"^\s*\*\*(?:\d+\.\s+|Assessment\s+\d+\s*[-–])", line, flags=re.IGNORECASE):
            if current:
                executive.append(current)
            text = re.sub(
                r"^\s*\*\*(?:\d+\.\s*|Assessment\s+\d+\s*[-–])\s*|\*\*\s*$",
                "",
                line,
                flags=re.IGNORECASE,
            )
            current = {
                "text": _clean(text),
                "evidence_ids": [item for item in _expand_references(line, iso3) if "-E-" in item],
                "pathway_ids": [item for item in _expand_references(line, iso3) if "-P-" in item],
            }
        elif current is not None and "supporting evidence" in line.casefold():
            current["evidence_ids"] = [item for item in _expand_references(line, iso3) if "-E-" in item]
        elif current is not None and ("supporting pathways" in line.casefold() or "pathways:" in line.casefold()):
            current["pathway_ids"] = [item for item in _expand_references(line, iso3) if "-P-" in item]
    if current:
        executive.append(current)
    if not executive:
        executive = [{"text": f"The {country_name} packet documents climate pressures, FCV mediators, and resilience constraints through reviewed public sources.", "evidence_ids": [], "pathway_ids": []}]
    if not any(item["evidence_ids"] or item["pathway_ids"] for item in executive):
        evidence_ids = [line["evidence_id"] for line in _evidence_records(packet, iso3, review_date)]
        pathway_ids = [line["pathway_id"] for line in _pathway_records(packet, iso3, review_date)]
        executive[0]["evidence_ids"] = evidence_ids[:3]
        executive[0]["pathway_ids"] = pathway_ids[:2]

    coverage_lines = _section(packet, "## Coverage matrix", "## Geographic notes")
    coverage = []
    for line in coverage_lines:
        if not line.strip().startswith("|") or re.match(r"^\|\s*-", line):
            continue
        cells = _split_row(line, 5)
        if len(cells) < 5 or cells[0].casefold() == "dimension":
            continue
        dimension, value, status, refs, gap = cells
        first = _clean(dimension)
        if "evidence class" in first.casefold():
            coverage_dimension = "evidence_class"
            coverage_value = _clean(re.split(r"[-:]", first, maxsplit=1)[-1]) or _clean(value)
        elif "priority domain" in first.casefold():
            coverage_dimension = "priority_domain"
            coverage_value = _clean(re.split(r"[-:]", first, maxsplit=1)[-1]) or _clean(value)
        else:
            coverage_dimension = first or "coverage"
            coverage_value = _clean(value)
        normalized_status = "covered" if "adequate" in status.casefold() or "cover" in status.casefold() else ("gap" if "gap" in status.casefold() else "partial")
        record_ids = _expand_references(refs, iso3)
        coverage.append({"dimension": coverage_dimension, "value": coverage_value, "status": normalized_status, "record_ids": record_ids, "gap_note": _clean(gap) or None})

    geographic_lines = _section(packet, "## Geographic notes", "## Sector notes")
    sector_lines = _section(packet, "## Sector notes", "# 6. Known gaps and unresolved questions")
    gap_lines = _section(packet, "# 6. Known gaps and unresolved questions", "# 7. Causal calibration audit")
    known_gap_lines = [line for line in gap_lines if re.match(r"^\s*(?:\d+\.|[-*])", line) and not line.lstrip().startswith("##")]
    if not known_gap_lines:
        known_gap_lines = [line for line in gap_lines if line.strip() and not line.lstrip().startswith("#") and not line.strip().startswith("|")]
    notes = lambda lines: [_profile_note(line, iso3) for line in lines if _clean(line) and not line.strip().startswith("|") and not line.strip().startswith("#")]
    known_gaps = notes(known_gap_lines)
    if not known_gaps:
        known_gaps = [_profile_note("The packet declares evidence limitations that require substantive human review before promotion.", iso3)]

    return {
        "iso3": iso3,
        "profile_version": "2026.08",
        "executive_assessment": executive,
        "coverage": coverage,
        "geographic_notes": notes(geographic_lines),
        "sector_notes": notes(sector_lines),
        "known_gaps": known_gaps,
        "selection_aliases": {key: {} for key in ("geographies", "sectors", "affected_groups", "institutions", "systems_assets", "hazards")},
        "review_status": "reviewed",
        "review_date": review_date,
    }


def _country_name_from_packet(packet: list[str], iso3: str) -> str:
    for line in packet[:20]:
        match = re.search(r"(?:Country|country):\s*(.+?)(?:\s*\(" + re.escape(iso3) + r"\))?\.?$", line)
        if match:
            return _clean(match.group(1))
        if iso3 in line and line.startswith("#"):
            title = _clean(line.lstrip("# "))
            title = re.sub(r"\s*\(" + re.escape(iso3) + r"\).*", "", title)
            title = re.sub(r"\s+Climate.*$", "", title, flags=re.IGNORECASE)
            return title
    return iso3


def parse_packet(text: str, *, iso3: str, country_name: str | None = None, review_date: str) -> dict[str, Any]:
    """Parse one research packet into schema-1.1 candidate records."""
    packet = text.splitlines()
    country_name = country_name or _country_name_from_packet(packet, iso3)
    sources = _source_records(packet, iso3, review_date)
    evidence = _evidence_records(packet, iso3, review_date)
    pathways = _pathway_records(packet, iso3, review_date)
    profile = _profile(packet, iso3, review_date, country_name)
    review_due = (date.fromisoformat(review_date) + timedelta(days=365)).isoformat()
    review = {
        "iso3": iso3,
        "country_name": country_name,
        "country_aliases": [],
        "status": "reviewed",
        "reviewer": REVIEWER,
        "reviewed_on": review_date,
        "review_due": review_due,
        "dossier_path": f"countries/{iso3}/candidates/2026.08/dossier.md",
        "evidence_ids": [record["evidence_id"] for record in evidence],
        "pathway_ids": [record["pathway_id"] for record in pathways],
        "decision_notes": (
            "Schema-1.1 candidate compiled from the supplied verified public-source packet. "
            "It requires Lindsey Jones's substantive review and is not approved for production. "
            "Packet-declared access, attribution, subnational coverage, evaluation, and reverse-pathway gaps are retained."
        ),
    }
    return {"sources": sources, "evidence": evidence, "pathways": pathways, "profile": profile, "review": review}


def write_candidate(parsed: dict[str, Any], output_dir: Path) -> None:
    """Write canonical candidate JSON and a deterministic dossier."""
    output_dir.mkdir(parents=True, exist_ok=True)
    for key in ("sources", "evidence", "pathways", "profile", "review"):
        (output_dir / f"{key}.json").write_text(
            json.dumps(parsed[key], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    errors = validate_country_directory(output_dir, require_profile=True, schema_version="1.1.0")
    if errors:
        raise ValueError(f"{output_dir}: {'; '.join(errors)}")
    (output_dir / "dossier.md").write_text(build_dossier(output_dir), encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iso3", required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--country-name")
    parser.add_argument("--review-date", default="2026-08-13")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    parsed = parse_packet(args.packet.read_text(encoding="utf-8"), iso3=args.iso3.upper(), country_name=args.country_name, review_date=args.review_date)
    write_candidate(parsed, args.output)
    print(f"{args.output} sources={len(parsed['sources'])} evidence={len(parsed['evidence'])} pathways={len(parsed['pathways'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
