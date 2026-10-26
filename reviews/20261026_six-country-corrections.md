# Revised six-country candidates for human review

Candidate version: `2026.10.26`. Prepared from bank commit `12a804fe92bacfdaf0bec7926725d8a7a9376fe4`, following the [26 October source review and correction table](https://github.com/ljonestz/FCV-AGENT/blob/1a34499/docs/20261026_six-country-bank-approval-table.md). The user accepted preparation of these corrections. Human approval of the revised evidence remains pending.

The package contains 103 evidence records and 35 pathways. All new records, profiles and country decisions have `draft` status. Reviewer and sign-off dates are empty. Existing review deadlines are preserved, including the expired country deadlines. The `2026.08` candidates and both runtime files remain available unchanged.

| Country | Evidence | Pathways | Revised dossier |
|---|---:|---:|---|
| South Sudan | 27 | 7 | [SSD dossier](../countries/SSD/candidates/2026.10.26/dossier.md) |
| Burkina Faso | 15 | 5 | [BFA dossier](../countries/BFA/candidates/2026.10.26/dossier.md) |
| Haiti | 15 | 6 | [HTI dossier](../countries/HTI/candidates/2026.10.26/dossier.md) |
| Papua New Guinea | 15 | 6 | [PNG dossier](../countries/PNG/candidates/2026.10.26/dossier.md) |
| Ukraine | 16 | 6 | [UKR dossier](../countries/UKR/candidates/2026.10.26/dossier.md) |
| Yemen | 15 | 5 | [YEM dossier](../countries/YEM/candidates/2026.10.26/dossier.md) |

The revisions correct statement scope, locators, projections, evidence strength, source dates, reuse metadata and profile dependencies as specified in the source reviews. Source registers retain an `open` flag only where the review established explicit reuse terms; unknown or permission-required notices are recorded without redistributing source documents.

Three items are excluded from this version. Their originals remain in `2026.08`:

- `BFA-P-005`: municipal delivery evidence lacks the climate interaction needed for this pathway.
- `YEM-E-009`: the cited pages were unavailable for verification of the complete governance, enforcement and utility-finance statement.
- `YEM-P-005`: programme-delivery evidence lacks the climate interaction needed for this pathway.

The Yemen food-security record uses the October-December 2026 partial-area IPC projection with its June publication and April information cutoff. It preserves the difference between that projection and the later WFP account of deteriorating conditions. Historical service evidence, local qualitative samples and modelled facility exposure retain their period and scope limits.

The [hash manifest](20261026_six-country-candidate-manifest.json) binds all 36 new files and records hashes for the 36 original files and two preserved runtime files. Hashes use UTF-8 text with LF line endings so Git's Windows line-ending conversion does not change the review identity. Any content edit to a candidate changes the artifacts awaiting sign-off. The accompanying test checks schema and reference integrity, deterministic dossiers, expected exclusions, unchanged deadlines and rejection by the production promotion gate.

## Human decision still required

Review the six linked dossiers and their ledgers against the source-review corrections. Record the named reviewer, decision and review date for the exact candidate hashes, and choose suitable expiry dates for the included current evidence and each country. Approval must cover the evidence, pathways and profile together. An old seasonal projection must not become a current observation merely through a new review date.

After those decisions are recorded, a separate release step can build and validate an approved runtime artifact. No runtime artifact was built from these drafts, the application's bank pin was not changed, and no deployment or paid model call was made. Source access limitations and causal uncertainty remain as documented in the source reviews.

Verification: all 295 companion-bank tests passed in 105.77 seconds with normal Windows process permissions. The new checks cover all six schema-1.1 candidates, deterministic dossiers, unchanged review deadlines, the 74-file hash manifest and rejection of draft promotion. A separate content comparison confirmed exactly the 21 mandatory evidence corrections, 11 pathway corrections and three exclusions, along with the specified source dates and reuse classifications. No previously tracked file was modified.

Command:

```text
python -m pytest tests -q -p no:cacheprovider --tb=short
```
