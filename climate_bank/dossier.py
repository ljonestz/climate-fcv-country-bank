"""Build deterministic Markdown dossiers from stored, validated ledgers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .validation import validate_country_directory


SECTION_HEADINGS = (
    "## 1. Scope, sources, and limitations",
    "## 2. Climate baseline",
    "## 3. Vulnerability and capacity",
    "## 4. Institutions, services, sectors, and livelihoods",
    "## 5. Mediated Climate-FCV pathways",
    "## 6. Reverse pathways",
    "## 7. Resilience factors",
    "## 8. Uncertainties",
    "## 9. Project-screening implications",
    "## 10. Evidence table",
    "## 11. Bibliography",
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _display_name(country_name: str) -> str:
    if country_name == "Synthetic South Sudan Pilot":
        return "South Sudan"
    return country_name


def _join(values: list[str]) -> str:
    return ", ".join(values) if values else "none recorded"


def _evidence_line(record: dict[str, Any]) -> str:
    return f"Evidence: {record['statement']} [{record['evidence_id']}]"


def _pathway_citation(pathway: dict[str, Any]) -> str:
    evidence_ids = ", ".join(sorted(pathway["supporting_evidence_ids"]))
    return f"[{pathway['pathway_id']}; {evidence_ids}]"


def _stored_value(value: Any) -> str:
    if isinstance(value, (list, dict)) or value is None:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    return str(value)


def _pathway_line(prefix: str, pathway: dict[str, Any]) -> str:
    return (
        f"{prefix}: Pathway ID: {_stored_value(pathway['pathway_id'])} | "
        f"ISO3: {_stored_value(pathway['iso3'])} | "
        f"Climate pressure: {_stored_value(pathway['climate_pressure'])} | "
        f"Documented impact: {_stored_value(pathway['documented_impact'])} | "
        f"FCV mediator: {_stored_value(pathway['fcv_mediator'])} | "
        f"Possible consequence: {_stored_value(pathway['possible_consequence'])} | "
        f"Geographies: {_stored_value(pathway['geographies'])} | "
        f"Affected groups: {_stored_value(pathway['affected_groups'])} | "
        f"Sectors: {_stored_value(pathway['sectors'])} | "
        f"Systems, assets, and resources: "
        f"{_stored_value(pathway['systems_assets_resources'])} | "
        f"Institutions: {_stored_value(pathway['institutions'])} | "
        f"Supporting evidence IDs: "
        f"{_stored_value(pathway['supporting_evidence_ids'])} | "
        f"Link evidence: {_stored_value(pathway['link_evidence'])} | "
        f"Evidence strength: {_stored_value(pathway['evidence_strength'])} | "
        f"Alternative explanations: "
        f"{_stored_value(pathway['alternative_explanations'])} | "
        f"Uncertainty: {_stored_value(pathway['uncertainty'])} | "
        f"Resilience factors: {_stored_value(pathway['resilience_factors'])} | "
        f"Compact statement: {_stored_value(pathway['compact_statement'])} | "
        f"Interaction direction: "
        f"{_stored_value(pathway['interaction_direction'])} | "
        f"Review status: {_stored_value(pathway['review_status'])} | "
        f"Review date: {_stored_value(pathway['review_date'])} "
        f"{_pathway_citation(pathway)}"
    )


def _source_scope_line(source: dict[str, Any]) -> str:
    return (
        f"- {source['title']} | Organization: {source['organization']} | "
        f"Methodology: {source['methodology']} | "
        f"Limitations: {source['limitations']} | URL: {source['url']} | "
        f"Source ID: {source['source_id']}"
    )


def _evidence_table_line(record: dict[str, Any]) -> str:
    references = "; ".join(
        f"{ref['source_id']} ({ref['locator']})"
        for ref in sorted(
            record["source_refs"],
            key=lambda ref: (ref["source_id"], ref["locator"]),
        )
    )
    return (
        f"| {record['evidence_id']} | {record['evidence_status']} / "
        f"{record['review_status']} | {record['analytical_role']} | "
        f"{record['confidence']} | {record['compact_statement']} | {references} |"
    )


def build_dossier(country_dir: Path) -> str:
    """Build a dossier using only validated ledger values and fixed labels."""
    country_dir = Path(country_dir)
    errors = validate_country_directory(country_dir)
    if errors:
        raise ValueError(f"{country_dir}: {'; '.join(sorted(set(errors)))}")

    sources = sorted(
        _read_json(country_dir / "sources.json"),
        key=lambda source: source["source_id"],
    )
    evidence = sorted(
        _read_json(country_dir / "evidence.json"),
        key=lambda record: record["evidence_id"],
    )
    pathways = sorted(
        _read_json(country_dir / "pathways.json"),
        key=lambda pathway: pathway["pathway_id"],
    )
    review = _read_json(country_dir / "review.json")
    referenced_source_ids = {
        ref["source_id"] for record in evidence for ref in record["source_refs"]
    }
    referenced_sources = [
        source for source in sources if source["source_id"] in referenced_source_ids
    ]

    lines = [
        f"# {_display_name(review['country_name'])} Climate-FCV Evidence Dossier",
        "",
        SECTION_HEADINGS[0],
        "",
        f"Country: {review['country_name']}",
        f"Country aliases: {_join(sorted(review['country_aliases']))}",
        f"Review status: {review['status']}",
        f"Decision notes: {review['decision_notes']}",
        "",
        *(_source_scope_line(source) for source in sources),
        "",
        SECTION_HEADINGS[1],
        "",
    ]
    physical = [
        record
        for record in evidence
        if record["analytical_role"] == "physical-baseline"
    ]
    lines.extend(_evidence_line(record) for record in physical)

    lines.extend(["", SECTION_HEADINGS[2], ""])
    vulnerability = [
        record
        for record in evidence
        if record["analytical_role"] == "vulnerability-capacity"
    ]
    lines.extend(_evidence_line(record) for record in vulnerability)

    lines.extend(["", SECTION_HEADINGS[3], ""])
    institutional = [
        record
        for record in evidence
        if record["analytical_role"] == "direct-climate-fcv"
    ]
    lines.extend(_evidence_line(record) for record in institutional)

    lines.extend(["", SECTION_HEADINGS[4], ""])
    mediated = [
        pathway
        for pathway in pathways
        if pathway["interaction_direction"] in {"climate-to-fcv", "bidirectional"}
    ]
    lines.extend(_pathway_line("Pathway", pathway) for pathway in mediated)

    lines.extend(["", SECTION_HEADINGS[5], ""])
    reverse = [
        pathway
        for pathway in pathways
        if pathway["interaction_direction"] in {"fcv-to-climate", "bidirectional"}
    ]
    lines.extend(_pathway_line("Reverse pathway", pathway) for pathway in reverse)

    lines.extend(["", SECTION_HEADINGS[6], ""])
    for pathway in pathways:
        for factor in pathway["resilience_factors"]:
            lines.append(
                f"Resilience factor: {factor} [{pathway['pathway_id']}; "
                f"{', '.join(sorted(pathway['supporting_evidence_ids']))}]"
            )

    lines.extend(["", SECTION_HEADINGS[7], ""])
    for record in evidence:
        lines.append(f"Uncertainty: {record['uncertainty']} [{record['evidence_id']}]")
    for pathway in pathways:
        lines.append(
            f"Uncertainty: {pathway['uncertainty']} {_pathway_citation(pathway)}"
        )

    lines.extend(["", SECTION_HEADINGS[8], ""])
    for record in evidence:
        lines.append(
            f"Screening implication: {record['compact_statement']} "
            f"[{record['evidence_id']}]"
        )
    for pathway in pathways:
        lines.append(
            f"Screening implication: {pathway['compact_statement']} "
            f"{_pathway_citation(pathway)}"
        )

    lines.extend(
        [
            "",
            SECTION_HEADINGS[9],
            "",
            "| Evidence ID | Status | Role | Confidence | Compact statement | "
            "Source references and locators |",
            "|---|---|---|---|---|---|",
        ]
    )
    lines.extend(_evidence_table_line(record) for record in evidence)

    lines.extend(["", SECTION_HEADINGS[10], ""])
    for source in referenced_sources:
        lines.append(
            f"- {source['organization']}. {source['title']}. "
            f"{source['publication_date']}. {source['url']} "
            f"[{source['source_id']}]"
        )

    return "\n".join(lines).rstrip() + "\n"
