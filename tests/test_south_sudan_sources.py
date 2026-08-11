"""Contract tests for the South Sudan pilot source registry."""

import json
from pathlib import Path

from climate_bank.validation import validate_country_directory


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
COUNTRY_DIR = REPOSITORY_ROOT / "countries" / "SSD"
EXPECTED_SOURCES = {
    "SSD-SRC-001": {
        "url": (
            "https://www.sipri.org/publications/2025/partner-publications/"
            "climate-peace-and-security-fact-sheet-south-sudan-2025"
        ),
        "roles": {"direct-climate-fcv"},
        "source_type": "think-tank-report",
    },
    "SSD-SRC-002": {
        "url": "https://www.un.org/climatesecuritymechanism/en/media/338",
        "roles": {"direct-climate-fcv", "vulnerability-capacity"},
        "source_type": "un-report",
    },
    "SSD-SRC-003": {
        "url": (
            "https://www.un.org/climatesecuritymechanism/en/news/"
            "joining-forces-conflict-sensitive-flood-response-south-sudan"
        ),
        "roles": {"direct-climate-fcv", "vulnerability-capacity"},
        "source_type": "web-page",
    },
    "SSD-SRC-004": {
        "url": (
            "https://documents.worldbank.org/en/publication/documents-reports/"
            "documentdetail/099013026015514714"
        ),
        "roles": {"vulnerability-capacity", "physical-baseline"},
        "source_type": "mdb-report",
    },
    "SSD-SRC-005": {
        "url": (
            "https://www.undp.org/south-sudan/publications/"
            "first-national-adaptation-plan-climate-change-republic-south-sudan"
        ),
        "roles": {"vulnerability-capacity"},
        "source_type": "government-report",
    },
    "SSD-SRC-006": {
        "url": "https://unfccc.int/documents/497930",
        "roles": {"vulnerability-capacity"},
        "source_type": "government-report",
    },
    "SSD-SRC-007": {
        "url": (
            "https://dtm.iom.int/reports/"
            "south-sudan-flood-damage-and-needs-assessment-study-2021"
        ),
        "roles": {"vulnerability-capacity"},
        "source_type": "un-report",
    },
    "SSD-SRC-008": {
        "url": (
            "https://southsudan.un.org/en/"
            "187947-south-sudan-un-common-country-analysis-cca"
        ),
        "roles": {"direct-climate-fcv", "vulnerability-capacity"},
        "source_type": "un-report",
    },
    "SSD-SRC-009": {
        "url": (
            "https://drmkc.jrc.ec.europa.eu/Inform-Index/Portals/0/InfoRM/"
            "CountryProfiles/SSD.pdf"
        ),
        "roles": {"vulnerability-capacity"},
        "source_type": "dataset",
    },
    "SSD-SRC-010": {
        "url": (
            "https://southsudan.un.org/en/"
            "293784-climate-change-deepens-gender-inequality-and-violence-"
            "south-sudan-unfpa-study-highlights"
        ),
        "roles": {"direct-climate-fcv", "vulnerability-capacity"},
        "source_type": "web-page",
    },
    "SSD-SRC-011": {
        "url": (
            "https://dtm.iom.int/reports/south-sudan-event-tracking-report-73-"
            "flood-displacements-1-31-december-2024"
        ),
        "roles": {"vulnerability-capacity"},
        "source_type": "un-report",
    },
    "SSD-SRC-012": {
        "url": (
            "https://climateknowledgeportal.worldbank.org/"
            "country/south-sudan/era5-historical"
        ),
        "roles": {"physical-baseline"},
        "source_type": "web-page",
    },
}

EXPECTED_LIMITATION_MARKERS = {
    "SSD-SRC-001": ("april 2025", "month precision"),
    "SSD-SRC-006": ("submission date", "2021-09-21", "not the portal"),
    "SSD-SRC-007": ("publication year 2021", "year precision"),
    "SSD-SRC-008": ("portal publication date", "2022-06-27", "2021-12-24"),
    "SSD-SRC-009": ("version 2021", "stated version year"),
    "SSD-SRC-012": ("living page", "era5", "national"),
}


def _load_country_file(filename: str):
    path = COUNTRY_DIR / filename
    assert path.is_file(), f"Missing South Sudan pilot file: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def test_south_sudan_pilot_release_lock_has_exact_source_registry() -> None:
    """Intentionally lock the pilot release to its exact 12-source registry."""
    sources = _load_country_file("sources.json")
    by_id = {source["source_id"]: source for source in sources}

    # Exact count is intentional release-lock coverage for this named pilot.
    assert len(sources) == 12
    assert len(by_id) == 12
    assert set(by_id) == set(EXPECTED_SOURCES)
    assert {
        role for source in sources for role in source["analytical_roles"]
    } == {
        "direct-climate-fcv",
        "vulnerability-capacity",
        "physical-baseline",
    }

    qualitative_count = sum(
        bool(
            {"direct-climate-fcv", "vulnerability-capacity"}
            & set(source["analytical_roles"])
        )
        for source in sources
    )
    physical_count = sum(
        "physical-baseline" in source["analytical_roles"] for source in sources
    )
    assert qualitative_count >= physical_count * 3

    for source_id, expected in EXPECTED_SOURCES.items():
        assert by_id[source_id]["url"] == expected["url"]
        assert set(by_id[source_id]["analytical_roles"]) == expected["roles"]
        assert by_id[source_id]["source_type"] == expected["source_type"]


def test_south_sudan_sources_are_link_only_and_reviewable() -> None:
    """Public records stay link-only and retain source-specific caveats."""
    sources = _load_country_file("sources.json")

    assert all(source["repository_file"] is None for source in sources)
    assert all(source["checksum"] is None for source in sources)
    assert all(source["accessed_on"] == "2026-07-30" for source in sources)
    assert all(source["country_codes"] == ["SSD"] for source in sources)
    assert all(source["methodology"].strip() for source in sources)
    assert all(source["limitations"].strip() for source in sources)
    assert {source["license_status"] for source in sources} == {"unknown"}
    assert all(
        isinstance(source["geographic_coverage"], list)
        and source["geographic_coverage"]
        and all(
            isinstance(location, str) and location.strip()
            for location in source["geographic_coverage"]
        )
        for source in sources
    )
    assert all(
        isinstance(source["temporal_coverage"], str)
        and source["temporal_coverage"].strip()
        for source in sources
    )


def test_south_sudan_sources_have_specific_and_transparent_notes() -> None:
    """Representative source classes retain focused method and caveat anchors."""
    sources = _load_country_file("sources.json")
    by_id = {source["source_id"]: source for source in sources}

    assert "jointly developed" in by_id["SSD-SRC-002"]["methodology"].lower()
    assert "government submission" in by_id["SSD-SRC-006"]["methodology"].lower()
    assert "two quantitative tools" in by_id["SSD-SRC-007"]["methodology"].lower()
    assert "composite country risk index" in by_id["SSD-SRC-009"]["methodology"].lower()
    era5 = by_id["SSD-SRC-012"]
    assert era5["title"] == "South Sudan Climatology (ERA5)"
    assert era5["geographic_coverage"] == ["South Sudan (national)"]
    assert era5["temporal_coverage"] == (
        "ERA5 climatology for 1991-2020 and historical daily data for 1950-2023."
    )
    assert "era5 reanalysis-derived" in era5["methodology"].lower()
    assert "0.25-degree resolution" in era5["methodology"].lower()
    for source_id, markers in EXPECTED_LIMITATION_MARKERS.items():
        limitation = by_id[source_id]["limitations"].lower()
        assert all(marker in limitation for marker in markers)


def test_south_sudan_review_ledger_records_human_release_approval() -> None:
    """The production package records Lindsey's explicit release decision."""
    review = _load_country_file("review.json")
    assert review["iso3"] == "SSD"
    assert review["country_name"] == "South Sudan"
    assert review["country_aliases"] == ["Republic of South Sudan"]
    assert review["status"] == "approved"
    assert review["reviewer"] == "Lindsey Jones"
    assert review["reviewed_on"] == "2026-07-31"
    assert review["review_due"] == "2027-07-31"
    assert "approved the South Sudan pilot" in review["decision_notes"]
    assert review["dossier_path"] == "countries/SSD/dossier.md"
    assert review["evidence_ids"]
    assert review["pathway_ids"]


def test_south_sudan_country_directory_passes_repository_validation() -> None:
    """The completed South Sudan directory satisfies repository contracts."""
    assert validate_country_directory(COUNTRY_DIR) == []


def test_south_sudan_pilot_release_lock_preserves_publication_provenance() -> None:
    """Intentionally lock all 12 pilot sources to their date precision and basis."""
    expected = {
        "SSD-SRC-001": ("2025-04", "publication"),
        "SSD-SRC-002": ("2025-10-02", "publication"),
        "SSD-SRC-003": ("2025-07-25", "publication"),
        "SSD-SRC-004": ("2026-01-30", "publication"),
        "SSD-SRC-005": ("2021-11-30", "publication"),
        "SSD-SRC-006": ("2021-09-21", "submission"),
        "SSD-SRC-007": ("2021", "publication"),
        "SSD-SRC-008": ("2022-06-27", "portal-publication"),
        "SSD-SRC-009": ("2021", "version"),
        "SSD-SRC-010": ("2025-05-05", "publication"),
        "SSD-SRC-011": ("2025-02-10", "publication"),
        "SSD-SRC-012": (None, "not-stated"),
    }
    sources = _load_country_file("sources.json")
    actual = {
        source["source_id"]: (
            source["publication_date"],
            source["publication_date_basis"],
        )
        for source in sources
    }

    assert actual == expected
    assert all("normalized to" not in source["limitations"].lower() for source in sources)
    assert all("schema-required" not in source["limitations"].lower() for source in sources)
