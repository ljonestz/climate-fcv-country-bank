from scripts.import_research_packets import _expand_references, parse_packet


PACKET = """# 1. Research summary

Country: Testland (TST)

# 2. Verified source register

| Source ID | Title | Organization | Publication date | Direct URL | Source type | Geographic coverage | Temporal coverage | Methodology/evidence basis | Analytical role(s) | Material limitations |
|---|---|---|---|---|---|---|---|---|---|---|
| TST-SRC-001 | Test source | Test agency | 2026-08-01 | https://example.org/test | web-page | Testland | 2026 | Desk review | physical-baseline | Not causal. |

## Source verification notes

# 3. Atomic evidence ledger

| Evidence ID | Atomic statement | Compact statement | Status | Analytical role | Evidence class | Level | Hazard tags | Impact tags | Geography | Affected groups | Sectors/assets | Institutions | Mediators | Direction | Time horizon/scenario | Source ID + exact locator | Confidence | Uncertainty/limits |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TST-E-001 | A documented test claim. | Test claim. | observed | physical-baseline | climate-pressure | national | drought, heat | crop loss | Testland | farmers | agriculture | Test agency | markets | contextual | current | TST-SRC-001, page 1 | medium | The test is limited. |

# 4. Mediated pathway candidates

## TST-P-001 — Test pathway

* **Climate pressure:** Drought
* **Documented impact:** Crop loss
* **FCV mediator:** Market stress
* **Possible consequence:** Local tension may increase
* **Interaction direction:** climate-to-fcv
* **Geography:** Testland
* **Affected groups:** Farmers
* **Sectors, systems, assets, or resources:** Agriculture, markets
* **Relevant institutions:** Test agency
* **Supporting evidence IDs:** TST-E-001
* **Link evidence:**

  * **pressure:** TST-E-001
  * **impact:** TST-E-001
  * **mediator:** TST-E-001
  * **consequence:** TST-E-001
* **Evidence strength:** **direct**
* **Alternative explanations:** Poverty
* **Uncertainty:** Causal effect is not estimated.
* **Resilience or risk-reducing factors:** Early warning
* **Compact statement:** Drought may increase tension through market stress.

# 5. Country profile synthesis

## Executive assessment

**1. The test pathway is conditional.**

Supporting evidence: **TST-E-001**.
Supporting pathways: **TST-P-001**.

## Coverage matrix

| Dimension | Finding | Coverage: adequate/partial/gap | Supporting evidence/pathway IDs | Gap note |
|---|---|---|---|---|
| Evidence class — climate-pressure | Test coverage | adequate | TST-E-001 | None |

## Geographic notes

The evidence is national in scope.

## Sector notes

Agriculture is represented.

# 6. Known gaps and unresolved questions

1. **Causal evidence:** No causal estimate is available.

# 7. Causal calibration audit

# 8. Final verification checklist
"""


def test_parse_packet_maps_tables_and_pathways_to_candidate_contract():
    parsed = parse_packet(PACKET, iso3="TST", country_name="Testland", review_date="2026-08-13")

    assert parsed["review"]["status"] == "reviewed"
    assert parsed["sources"][0]["url"] == "https://example.org/test"
    assert parsed["evidence"][0]["source_refs"] == [
        {"source_id": "TST-SRC-001", "locator": "page 1"}
    ]
    assert parsed["pathways"][0]["supporting_evidence_ids"] == ["TST-E-001"]
    assert parsed["pathways"][0]["link_evidence"]["consequence"] == ["TST-E-001"]
    assert parsed["profile"]["coverage"][0]["status"] == "covered"
    assert parsed["profile"]["known_gaps"][0]["text"].startswith("Causal evidence")


def test_expand_references_accepts_compact_and_repeated_prefix_ranges():
    assert _expand_references("ETH-E-001–005; ETH-P-001–P-003", "ETH") == [
        "ETH-E-001",
        "ETH-E-002",
        "ETH-E-003",
        "ETH-E-004",
        "ETH-E-005",
        "ETH-P-001",
        "ETH-P-002",
        "ETH-P-003",
    ]
