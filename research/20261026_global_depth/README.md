# Global country-depth review: 27 October 2026

## Scope and review state

The `2026.10.26.deep` candidates cover 146 country banks: all 84 prior banks, plus 62 remaining FY27 IBRD borrowers. The roster contains 78 IDA-eligible countries (including 19 blend borrowers), 67 IBRD borrowers, and the retained West Bank and Gaza bank. Lending eligibility is not an FCV classification. The scope follows the [World Bank lending-group roster](https://datahelpdesk.worldbank.org/knowledgebase/articles/906519-world-bank-country-and-lending-groups), not the list of IBRD members.

All depth candidates remain draft. Coordinator adjudication and automated checks do not constitute designated human approval. Prior approved snapshots, earlier candidates, inherited evidence deadlines and the 24-country production release are unchanged.

The [approval table](../../reviews/20261027_global-depth-approval-table.md) records each country's additions. Its linked dossiers contain source locators and coverage gaps. The [review manifest](../../reviews/20261027_global-depth-review-manifest.json) binds the review to the actual source-extraction, decision and candidate files.

## Evidence method

Collectors searched each country for named local vulnerability, FCV mediators, insecurity constraining climate response, and resilience capacities. They logged inaccessible sources and negative searches. The coordinator adjudicated every proposed claim and assembled pathways with explicit evidence for each link, alternative explanations and uncertainty.

The same protocol applies across countries; the available evidence differs. Named places are selected examples, not complete local risk rankings. Poverty, mobility and nonviolent protest do not by themselves establish FCV. Forecasts retain their source date and period. Project plans and agency-reported outputs are distinguished from evaluated outcomes.

Only metadata and concise original paraphrases are committed. Source PDFs and restricted materials are excluded. A shared-URL paraphrase limit also covers repeated regional sources. Venezuela's low-confidence climate claims from a user-uploaded mirror require official-source verification before approval. The restricted Uzbekistan atlas contributes no substantive evidence.

## Review before approval

For each country, open the dossier and the cited passages, check geographic scope and dates, and decide whether to retain, revise or exclude the proposed additions. Give particular attention to low-confidence records, source-access limitations, conditional pathways and old evidence deadlines. A pathway count of zero records a review finding, not absence of FCV risk.

Record designated human approval through the existing review workflow before assembling a normal runtime release. Do not change draft flags merely to make a production validator accept these candidates. The test artifact below has a separate format and is deliberately rejected by production promotion.

## Rebuild the isolated test artifact

Run from this bank repository in the existing development environment. The input manifest lists exactly the 146 candidate directories; ordinary discovery also finds older versions and must not replace it.

```powershell
$generated = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
python -m scripts.build_test_bundle --country-manifest research/20261026_global_depth/TEST_INPUTS.json --generated-at $generated --test-expires-on 2026-11-02 --content-version 2026.10.27.global146-test --output releases/testing/20261027_global146-test.json
```

The builder refuses to overwrite a file. If that output already exists, use a new filename. Generation must be on or before the expiry date and the lifetime must be at most seven days. After 2 November, choose a fresh short test window and filename; this does not renew production evidence approval.

The artifact stays under ignored `releases/testing/` and is not a release. Use the app branch's `python -m scripts.run_country_bank_test --bundle <artifact> --check` or `--serve` launcher. It validates all countries in three sectors and, when serving, binds to loopback with an UNAPPROVED banner. Loading requires all explicit test-mode controls. Normal app startup retains the approved 24-country bank. Running a paid assessment, deployment and production promotion require separate authorization.

## Verification

```powershell
python -m pytest -q -p no:cacheprovider
git diff --check
```

The integrity suite verifies all 146 candidates, exact reproduction from raw extraction and adjudication, source references, draft/null review state and the 878 frozen baseline-file hashes. Tests establish structural integrity; human source review and tomorrow's application assessment remain separate checks.
