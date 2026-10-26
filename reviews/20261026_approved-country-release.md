# Approved country release: 26 October 2026

Lindsey Jones approved integration of the corrected country-review package on
26 October 2026. The reviewed inputs are frozen at commit
79fbe8abde57633120f37b8b0212c6eb7c9531ea. This approval does not authorize deployment.

The release `2026.10.26.approved-country-bank` contains 24 countries, 272 referenced
sources, 531 evidence records and 168 pathways. It uses the existing schema 1.1.0
production contract with `candidate: false`.

Countries: AFG, BFA, CAF, CMR, COD, ETH, HTI, IRN, IRQ, LBN, LBY, MLI, MMR, MOZ,
NER, NGA, PNG, PSE, SDN, SOM, SSD, SYR, UKR and YEM.

## Approval and preservation

Approved copies are under `countries/ISO/approved/2026.10.26/`. Original corrected
drafts, source reviews and pending-at-the-time manifests remain unchanged.
Only approval metadata and generated dossiers differ from the corrected drafts.
No evidence statements, pathway claims, source metadata, projection horizons or
evidence review deadlines were changed.

The six expired country-level deadlines were aligned with the earliest included
evidence deadline: BFA, HTI, PNG, UKR and YEM expire after 10 November 2026; SSD
expires after 31 January 2027. Other country-level deadlines remain unchanged.
Evidence-level checks can withhold individual current records earlier than a
country-level deadline. Approval is not a fresh verification of changing conditions.

`20261026_production-approval-manifest.json` binds all 144 corrected candidate
files, all 144 approved files and the runtime releases using normalized UTF-8/LF
SHA-256 hashes. The approved current runtime hash is
`12f0a7b5c8267ec3a8ed8033f3e4716af69024a9290e023e5264a94ed35ebda8`.

The previous current release is preserved at
`releases/archive/2026.07.south-sudan-pilot/runtime.json`. Legacy pilot and review
freeze tests now verify that archive with their original expected content and
hashes. The `releases/candidates/2026.08/runtime.json` preview is unchanged.

## Limitations and application integration

National coverage is broader than subnational coverage. Geographic specificity,
causal strength, inaccessible sources and evaluation gaps remain as documented
in the accepted dossiers. Deferred records remain excluded.

The app must pin this release commit and retain `python render_build.py` so fresh
checkouts initialize the submodule. Its existing approved-bank reader needs no
new preview token. A future deployment must check `CLIMATE_COUNTRY_BANK_PATH`:
an old candidate override would continue selecting the old preview. This task
does not change hosted settings, deploy services, merge branches or run paid calls.
