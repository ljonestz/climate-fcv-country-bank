# Country-bank review package for a browser research session

Use this package to verify and update one existing country bank at a time. The seed files are research drafts and may contain unsupported statements, incorrect locators or stale claims. They are inputs to review, not verified findings.

The target list covers the 18 remaining existing banks. It does not change the six countries already reviewed: South Sudan, Burkina Faso, Haiti, Papua New Guinea, Ukraine and Yemen. National evidence and supported local examples are sufficient for this phase; comprehensive district coverage is not required.

The archive includes the original country seeds, the bank's JSON schemas, a corrected South Sudan example, and a checksum manifest. It contains public-source metadata and derived summaries, with no source PDFs or credentials.

## Run one country

Give the browser research session this archive if it supports reading attachments, and paste the prompt below. Start with Afghanistan (`AFG`), then repeat for another code in `TARGET_COUNTRIES.json`. If attachments cannot be read, the seed and schema paths are also available in the [public companion repository at the pinned baseline](https://github.com/ljonestz/climate-fcv-country-bank/tree/12a804fe92bacfdaf0bec7926725d8a7a9376fe4).

```text
Review country AFG from the attached Climate-FCV country-bank package.

Read this package's START_HERE.md, TARGET_COUNTRIES.json, schemas and the selected country's seed files before researching. Complete the source review and return the draft files described below. Keep the original country IDs where claims remain; record every retained, revised or deferred evidence and pathway item. Use the source-review method and output contract in START_HERE.md. Do not approve, publish or deploy the result.
```

Use the next country only after the previous country's outputs and access limits have been recorded. A session without working access to primary sources must report that limitation and leave affected claims unverified.

## Source-review method

1. Read every evidence statement, source locator, pathway and profile note in the selected seed. Review the existing claims before deciding whether additional sources are necessary.
2. Open the cited primary publication and inspect the actual passage. Record its direct URL, section or page, geographic scope, applicable period, method and important limitations. If an alternate official edition is used, identify that edition and its pagination.
3. Use a dated document or stable historical edition for seasonal statistics. A rolling country page does not verify a figure from a previous edition. Distinguish observed changes, projections, reported programme outputs, intended capacity and evaluated outcomes.
4. An official indexed passage can support a claim only if it reproduces the continuous relevant text, figures and qualifications under the publisher's URL. Search snippets, catalogues, contents pages and third-party citations do not verify the underlying finding. Describe the access method honestly; do not call a passage check full-document inspection.
5. For each original evidence ID, record RETAIN, REVISE or DEFER. RETAIN means no mandatory content or locator edit. REVISE requires an explicit correction. DEFER means the claim cannot be included responsibly on the inspected evidence. An access failure does not establish that the claim is false.
6. Check every pathway link against the evidence that supports that link. Identify the climate pressure, impact, FCV mediator, possible consequence, alternatives and uncertainty. Use only the schema's climate-to-FCV, FCV-to-climate or bidirectional directions. Preserve distinctions between a conditional mechanism and a measured causal effect. A delivery problem alone does not establish a climate interaction.
7. Repair profile references only after checking that the evidence supports the actual sentence. Narrow or remove unsupported synthesis. Do not attach a convenient ID simply to satisfy a validator. Preserve local scope and the distinction between FCV sensitivity and active responsiveness.
8. Exclude deferred records from the new ledgers and remove their substantive dependencies from pathways, profiles and coverage rows. Keep the original IDs and reasons in the source-review decision sheet. If too little evidence remains for a defensible country package, defer the country and explain what is missing.
9. Preserve verified reuse terms in source limitations. Use `unknown` unless explicit terms establish reuse permission, and `permission-required` when the notice requires permission. Public download alone does not establish an open licence. Do not return source-document copies, long extracts, credentials, restricted institutional material or model-generated citations.

## Output contract

Return a folder named with the selected ISO3 code containing:

- `sources.json`: source records matching `schemas/source.schema.json`.
- `evidence.json`: retained and corrected records matching the schema-1.1 evidence contract.
- `pathways.json`: supported pathways with valid evidence links.
- `profile.json`: supported synthesis, coverage, geographic and sector notes, known gaps and selection aliases.
- `review.json`: the draft country decision, included IDs and candidate dossier path.
- `source-review.md`: the decision sheet and access audit described below.

Use candidate version `2026.10.26` for this batch. Preserve original evidence, pathway and source IDs; assign genuinely new records the next unused ID without renumbering existing records. Do not introduce fields outside the schemas.

All evidence, pathways and profiles must have `review_status: draft` and `review_date: null`. The profile version is `2026.10.26`. The country review has `status: draft`, `reviewer: null` and `reviewed_on: null`. Its dossier path is `countries/ISO3/candidates/2026.10.26/dossier.md`, using the actual country code. Preserve existing country and record review deadlines; do not extend them as a side effect of research. Document source-access dates accurately. Do not invent checksums for undownloaded sources; no source document is to be stored in the repository.

The decision sheet must include one row per original evidence and pathway ID:

| Record ID | Decision | Primary source and exact inspected locator | Finding and required change |
|---|---|---|---|

Also include source-access results, date/version and reuse findings, profile changes, exclusions and remaining evidence gaps. Distinguish verified passages from inaccessible ones. Do not describe every source as verified if only some were inspected.

The final response should state the number of records retained, revised and deferred, the files returned, any validation actually run and unresolved issues. Do not claim automated tests or schema validation ran unless they actually ran in the session.

## Absorb the returned work into the bank

The coordinator checks the returned decision sheet and files, writes the reviewed outputs into a new candidate directory, runs schema and reference validation, and regenerates the dossier with the existing bank tool. The current Markdown importer must not be used unmodified for this batch: it contains version/date defaults and reference or horizon guesses that this review must not silently inherit.

For example, after checking Afghanistan's returned files in the companion repository:

```text
python -m scripts.validate_bank --country-dir countries/AFG/candidates/2026.10.26 --require-profile --schema-version 1.1.0
python -m scripts.build_dossier --country-dir countries/AFG/candidates/2026.10.26
python -m scripts.build_dossier --country-dir countries/AFG/candidates/2026.10.26 --check
```

Human review follows the corrected files and their recorded hashes. Runtime construction, the app's bank pin and deployment remain separate decisions.
