# Remaining-country review implementation plan

> For agentic workers: use the existing parallel country assignments below. Steps use checkboxes to track review, corrections and acceptance.

Goal: review the remaining 18 existing country banks and prepare traceable corrections for human approval, keeping the accepted six-country package unchanged.

Architecture: preserve `2026.08` as the review baseline. Each country receives a source-review decision sheet and, where the evidence supports it, a new `2026.10.26` draft candidate. Reuse the existing schemas, validator and deterministic dossier generator. Do not alter runtime files, the app's submodule pin or deployment configuration.

Tools: public primary sources, the bank's JSON contracts, Python and existing Git review branches. No model API calls or new dependencies are required.

## Country assignments

| Assignment | Countries | Exclusive new files |
|---|---|---|
| MENA / Afghanistan | AFG, IRN, IRQ, LBN, LBY, PSE | Six candidate files per country under `countries/ISO/candidates/2026.10.26/`; `reviews/20261026_source-review-ISO.md` |
| Africa | CAF, CMR, COD, ETH, MOZ, NGA | Same paths for the assigned countries only |
| Sahel / other contexts | MLI, MMR, NER, SDN, SOM, SYR | Same paths for the assigned countries only |
| Coordinator | All 18, read-only acceptance | Consolidated approval table, manifest, verification test, browser review instructions and app handoff |

## Review and candidate preparation

- [ ] Check all 461 original evidence records, 141 pathways and 250 source-register entries. Distinguish unused sources from sources supporting included claims.
- [ ] Record one retain, revise or defer decision for every original evidence and pathway ID. Link actual primary passages and state access limits. Catalogues and short search snippets do not verify claims.
- [ ] Check dates, historical and projection periods, geographic scope, causal strength and uncertainty. Correct Somalia's horizon mapping and resolve the rolling FAO source's historical edition or update the affected claims from inspected evidence.
- [ ] Repair claim-bearing profile notes only where retained evidence supports their actual wording. Narrow or remove unsupported synthesis. Remove excluded dependencies throughout the new profile and coverage matrix.
- [ ] Create the supported new candidate versions. Set records, profiles and country decisions to draft, clear sign-off metadata, preserve existing review deadlines, record exclusions and regenerate dossiers. A country that lacks a defensible evidence base remains deferred instead of receiving a nominally complete package.
- [ ] Preserve explicit source reuse terms. Use unknown when an open licence was not established, and permission-required where the source notice requires permission. Do not bundle source documents.

## Acceptance and handoff

- [ ] Compare actual country files and decision rows against the original IDs, inspect consequential corrections and verify source-access claims where material.
- [ ] Freeze candidate and review-file hashes using UTF-8 text with LF line endings. Confirm the earlier six candidates, original candidates and runtime files are unchanged.
- [ ] Validate every new candidate against schema 1.1, check references and deterministic dossiers, and run the full bank test suite once after focused checks pass. Report Windows setup failures separately from assertions.
- [ ] Prepare the consolidated approval table, with country-level counts, exclusions, access limitations and exact candidate hashes. Keep human approval separate from automated review.
- [ ] Package the seed ledgers, contracts and review instructions for use in a browser research session. The handoff must preserve uncertainty and produce draft files that can pass the existing local bank validation; it must not assign approval or update runtime content.
- [ ] Review staged changes, commit at logical checkpoints, push the feature branch and update the draft PR and app handoff. No merge or deployment.

The user has already authorized this work. Execute the plan in the existing isolated worktrees; no additional execution-choice prompt is needed.
