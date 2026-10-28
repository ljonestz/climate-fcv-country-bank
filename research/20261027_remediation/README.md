# Global country-bank remediation: 27 October 2026

These are **unapproved candidates for supervised testing and human review**. All
146 countries remain draft. No approved bank, production release or prior depth
snapshot is replaced.

## Method and limits

The audit inventories every source, evidence record, pathway and profile in the
exact `research/20261026_global_depth/TEST_INPUTS.json` roster, including inherited
material. Automated checks identify reference, locator, geography, projection,
causal-role and coverage issues for follow-up. They do not establish that a source
supports a claim. One selected source URL per country was attempted; accessible
text, metadata and a successful download are distinguished from passage review.

The inherited inventory contains 2,639 evidence records, 240 pathways and 1,094
sources. Seventy inherited evidence claims received individual passage-to-claim
checks. The audit records 1,591 other records as access-only and 978 as unresolved.
Every whole-bank disposition remains `unresolved-limited`. Four new evidence
records and one new pathway are separately adjudicated in `overrides.json`.
Verification is claim-specific, not certification of an entire bank or source.

The remediation preserves full statements in compact evidence, adds explicit
scenario text for projections where absent, and attaches an independent-
verification limitation to every remaining unverified evidence record and
pathway. Each profile starts with its verification counts and limitations. This
keeps unresolved material visible for review without presenting it as verified.
Inherited review deadlines and draft/null approval fields are preserved.

## Material adjudications

- PNG's 12 areas/projects, 24 communities, nine grants and over 16,000 expected
  beneficiaries are retained with the verified physical-page locator. Expected
  reach remains distinct from achieved reach. Hela programme evidence is not
  attached to Carteret relocation; the unrelated Port Moresby survey is removed
  from that pathway's support.
- Chad retains the report-level flood/conflict assertion as direct reporting with
  an explicit causal limit. New evidence supports a bounded reverse pathway from
  conflict displacement and constrained settlement/services to flood exposure.
  The dated food-security estimate retains its period and analysed-population
  denominator. No named adaptation project is claimed to be obstructed.
- Tuvalu retains SSP2-4.5/SSP5-8.5 and the 2060 horizon with its flood projection.
  New official treaty evidence covers bilateral voluntary mobility and continuing
  statehood/sovereignty. Preliminary 2022 risk evidence predates entry into force;
  it does not establish inevitable state extinction or armed conflict.
- Somalia retains source-specific, non-counterfactual outcome limits and corrects
  the cooperative-member denominator. Elapsed seasonal projections and a full-year
  projection are distinguished. The mutable March GIEWS edition is unresolved.
  EIP reuse terms are qualified; its accurate year-only publication date remains,
  with the audit recording the recommended finer cover date.
- Vietnam's historical provincial names receive the 2025 boundary-change
  qualification. Venezuela's unauthenticated mirror remains low confidence and
  explicitly unresolved. Uzbekistan's restricted atlas is not filled speculatively.
- Stale generic zero-pathway statements are removed where pathways exist. Zero
  assembled pathways does not establish hazard-only evidence. Legitimate standalone
  evidence is retained; links are not added to satisfy a pathway count.

The record-level decisions, locators, access dates and verification methods are in
`overrides.json` and `audit/<ISO3>.json`. Missing passages or inaccessible sources
are not treated as contradictory evidence. Further source work and analytical
approval remain necessary before operational reliance.

## Reproduce and inspect

From the bank repository:

```powershell
python -m scripts.remediate_depth_candidates --check-only
python research/20261027_remediation/audit_sources.py --check
python -m pytest -q -p no:cacheprovider
```

The first command validates all frozen inputs, including all 878 baseline hashes,
rebuilds every candidate in temporary staging, and compares every published output
to that rebuild. It writes no final files. A fresh checkout can publish the absent
remediation outputs with the same command without `--check-only`; it refuses to
overwrite any existing output. Do not rerun source-access collection to reproduce
the frozen review: source websites can change.

Outputs:

- `countries/<ISO3>/candidates/2026.10.27.remediated/`: six files per country,
  including regenerated dossiers, profiles and draft review metadata.
- `TEST_INPUTS.json`: exact 146-country test-input manifest.
- `../../reviews/20261027_remediated-country-ledger.json`: transformations,
  decisions, source limits, counts and country identities.
- `../../reviews/20261027_remediated-review-manifest.json`: candidate and input
  file hashes, baseline checks and review-artifact identities.
- `../../reviews/20261027_remediated-approval-table.md`: all-country review index.

Hashes establish reproducible file identity, not analytical approval. Downloaded
documents, excerpts, access logs and generated test bundles are ignored and must
not be committed. The app's dated remediation-results document records fresh
verification, the short-lived bundle's identity/expiry, and supervised-test steps.

## Fresh verification and local bundle

The full bank suite passed: **697 tests in 759.19 seconds**, using
`python -X utf8 -m pytest tests -q -p no:cacheprovider`. Repository configuration
sets `testpaths = ["tests"]`; all tracked test modules are there. Independent
checks also matched all 146 prior nine-file identities, all new candidate and
review-artifact identities, all 878 frozen files, approval fields, inherited
deadlines and the approved runtime identity.

The ignored local artifact is
`releases/testing/20261027_global146-remediated-test.json`, generated
`2026-10-27T10:55:08Z`, expiring `2026-10-30`, version
`2026.10.27.global146-remediated-test`. It contains 146 country profiles, 2,643
evidence records, 241 pathways and 1,045 referenced sources; the candidate
directories retain 1,096 source-metadata records, including unreferenced sources.
It is 8,609,267 bytes. Byte/UTF-8-LF SHA-256:
`0dfc90df2422c769e07a715fd338d82dc2ab3d42143506060145bf329cf4a6df`.
Source-manifest checksum:
`e72a1c766cedcd8e6a8eefa2a040afca082d34eff4a0f596e97e73fd11daf4bf`.

This test-only artifact includes bounded-profile input under `country_profiles`.
The production builder/schema are unchanged and reject it as a runtime release.
The approved 24-country runtime's normalized UTF-8/LF SHA-256 remains
`12f0a7b5c8267ec3a8ed8033f3e4716af69024a9290e023e5264a94ed35ebda8`.
