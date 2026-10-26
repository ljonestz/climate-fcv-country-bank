# IDA expansion review package

The package adds 60 draft country banks: 153 source records, 392 passage-linked evidence records and 14 conditional pathways. Combined with the 18 existing IDA banks, the roster covers all 78 FY27 IDA-eligible countries. Six existing non-IDA banks remain in scope and unchanged. These are initial banks with uneven depth, not comprehensive country assessments.

Start with [the approval table](../../reviews/20261026_ida-approval-table.md). Each country link opens a dossier with evidence, source locators, geographic detail and gaps. The [roster](TARGET_COUNTRIES.json) records the official eligibility sources. `extractions/` preserves the passage-level claims and access audit, including rejected, blocked and metadata-only sources.

## Review in Codex web browser (work)

Open `ljonestz/climate-fcv-country-bank` on branch `feat/ida-country-candidates-20261026`, then use this prompt:

> Read CLAUDE.md, research/20261026_ida_expansion/START_HERE.md, the approval table and its manifest. Verify the manifest and run the focused tests below. Review the country rows I select against their actual primary sources, prioritizing subnational scope, climate-FCV mediation, dates/scenarios and the distinction between plans and evaluated outcomes. Do not infer conflict from IDA eligibility. Report unsupported or outdated claims and exact proposed corrections. Do not approve records, alter releases/current, change the app submodule pin, merge, deploy, or make paid application-model calls. Preserve existing banks and review deadlines. Any corrections need a new branch, an updated bound snapshot and human approval.

All public-source content is in the bank repository. No work account credentials, source PDFs, internal project documents or application secrets are included.

## Verification

From the bank repository root, with its existing development dependencies:

```powershell
python -m pytest tests/test_ida_expansion.py -q -p no:cacheprovider
python -m pytest -q -p no:cacheprovider
```

To inspect one version explicitly:

```powershell
python -m scripts.validate_bank --country-dir countries/KEN/candidates/2026.10.26 --require-profile --schema-version 1.1.0
python -m scripts.build_dossier --country-dir countries/KEN/candidates/2026.10.26 --check
```

The default root-discovery validation command assumes flat ledgers. It already fails on 23 older versioned country roots at the baseline commit; use explicit versioned paths. This package does not change that utility.

## Scope and limits

All records remain draft. The promotion utility rejects them. The existing 24-country approved release and app bank pin remain unchanged at `cccf251d86a8f3f3a73c930ff8b284c256304c1a`. The app handoff branch starts at `7aee640`, preserving the recent Word design work.

A substantive official summary supports only its inspected text, not an inaccessible underlying report. Historical impacts, modeled exposure, prospective risk statements, policy commitments and reported outputs retain their limitations. Selected local examples do not establish nationwide local coverage. No completed pathway is asserted for 46 countries; this does not establish absence of climate-FCV interactions.

Current-record recheck deadlines are 26 January 2027; structural-record deadlines are 26 October 2027. They are administrative recheck dates, not approval dates or warranties of current accuracy. Country-level approval deadlines remain unset until review. Existing country deadlines are not extended.

The manifest uses SHA-256 of UTF-8 text with normalized LF line endings, matching Python `read_text`. It binds the 360 country files and supporting review material, without granting approval. The coordinator's semantic annotations are recorded separately. No new app code, dependencies or schema changes are needed.
