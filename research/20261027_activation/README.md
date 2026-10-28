# Qualified global country-bank activation: 27 October 2026

This activation contains separate approved copies of the 146 remediated country
candidates and a schema 1.1 runtime release. Lindsey Jones authorized qualified
routine/default Climate-FCV application use on 27 October 2026. That approval
covers use of the bank in the application; it does not certify its claims or
sources, or establish independent source verification. Deployment and hosted
configuration changes are outside this activation.

## Reproduction

Run from the repository root:

```powershell
python -m scripts.activate_global_release
python -m scripts.activate_global_release --check
```

The default command stages and validates a reconstruction without publishing.
`--check` reconstructs the release from the bound candidate snapshots, compares
the approved copies, archived originals, approval manifest, and current runtime,
and fails on any identity mismatch. The authorized `--publish` option installs
the approved copies and required archives before replacing the current runtime.
The activation manifest is `reviews/20261027_global-production-approval-manifest.json`.
It binds the candidate and approved files, runtime, prior freeze, and the exact
archive path and old/new hash for every changed frozen file. All other files in
the 878-file baseline remain bound to their original hashes.

The 26 October IDA approval manifest remains an unchanged historical snapshot.
The activation manifest binds `tests/test_ida_expansion.py` as a frozen
replacement by recording its original archived hash and current verifier hash.
The regression test checks that chain and continues to require the original
hash for every other file in the IDA manifest.

## Scope and review limits

The runtime contains 146 countries, 1,045 referenced sources, 2,643 evidence
records, and 241 pathways. Per-country profile coverage and known gaps are
retained in the runtime so the application can present these limits with the
bank content. The evidence and pathways remain claims with their stored
uncertainty and verification status. The remediation audit records 70
claim-to-passage checks among inherited evidence records, 1,591 access-only
records, and 978 unresolved records; passage checks and human decisions are
recorded at the relevant country and record level. Attempting a source URL or
finding accessible text does not by itself verify the linked claim. These counts
do not represent certification of every source or record. Across the remediated
release, 74 evidence records and one pathway have claim-level checks; the other
2,569 evidence records and 240 pathways retain explicit independent-verification
limitations.

The activation preserves the source records, evidence statements, confidence,
source dates, uncertainty wording, and every evidence-level review deadline.
Country-level `review_due` is set to the earliest existing structural evidence
deadline for that country; it does not renew an individual current-record
deadline. Expiry and dependent-path handling remain separate at record level.
No deadline is silently extended. The existing validation gate rejects records already expired as of the release
generation date; historical reconstruction uses that same date.

The two generic draft profile notices are updated in each approved copy to
reflect the qualified routine-use approval and continuing source-verification
limits. Other profile content is preserved. Lending eligibility or inclusion
in this bank is not an FCV classification.
