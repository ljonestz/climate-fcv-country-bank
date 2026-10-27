# Global country-bank source extraction contract

## Objective and boundaries
Strengthen named subnational vulnerability and FCV depth. Collect source-faithful claims only; coordinator retains causal synthesis and final acceptance. Public original research, government, UN, MDB, peer-reviewed reports preferred. No source PDFs/restricted materials, no copied long passages, no invention, no approval status changes.
For phase2's62 new IBRD banks, seek4–6 substantive sources and12–20 useful claims covering physical climate, differentiated vulnerability, institutions, relevant FCV mediators and resilience capacities. These are search objectives, never quotas or a requirement to invent conflict links. The same provenance and uncertainty standards apply.
Read the existing country version before searching; avoid duplicating its claims. Seek substantive reports, not just press-release summaries. Target 3–5 additional country-specific sources and 8–14 useful claims per existing country where available; this is a search objective, not permission to invent or fill quotas. Record access and evidence gaps.

## Ownership
Each collector writes only its assigned ISO files under research/20261026_global_depth/phase1/ISO.json (phase2 for new IBRD). Use apply_patch. No edits to countries, runtime, code, approvals, manifests or other collectors' files. No commits/pushes. Persist after every country; notify coordinator after four. Do not stop at a batch subset.

## Extraction shape
Each file: {iso3,country_name,sources:[source.schema.json records],claims:[...],access_audit:[...],search_audit:[...],gaps:[strings]}.
Read schemas/source.schema.json and research/20261026_ida_expansion/EXTRACTION_CONTRACT.md for full source/claim fields. Use source IDs ISO-SRC-101 onward and claim IDs ISO-C-101 onward (new country also starts101).
Each claim includes claim_id,source_id,locator,paraphrase,kind,basis,time_horizons,scenario,geographies,administrative_level,hazards,sectors,affected_groups,systems,institutions,limitations,access_method.
Add subnational_specificity: named-admin / named-site / named-livelihood-zone / generic-zone / national / cross-border.
Add source_stated_fcv_link: null or short original paraphrase of explicitly source-stated mediated relationship; include its exact locator. Do not infer a chain from co-occurrence.
kind only climate-pressure,exposure,sensitivity,coping-capacity,adaptive-capacity,institutional-capacity,response-performance,direct-climate-fcv,resilience-peace-capacity.
basis observed/projected. Policy intentions observed as commitments, never delivered outcomes. Projected requires actual scenario/explicit source-unspecified qualifier and future horizon.
Administrative levels only national,state,administrative-area,county,payam,boma,site,cross-border,not-applicable.
Access audit rows: source_id (or null),url,access_method full-text/official-excerpt/metadata-only/blocked,locator,notes,reuse_terms.
Search audit rows: query,purpose (subnational-vulnerability/fcv-mediators/reverse-fcv/resilience-capacity),outcome,urls. All four purposes must be searched, meaningful negatives logged.
Sources may have license_status unknown; do not label open without verifying.
Use actual access date, actual publication date basis. Read full cited passages. Search snippets/metadata alone cannot support evidence.
PDF locator: explicitly one-based PDF page or exact printed page. Never guess pages from search text.

## Depth and calibration
Seek at least two concrete named local examples where evidence allows, affected groups, tenure/access/exclusion, displacement/protection, local institutions, insecurity constraining adaptation and resilience/peace capacities. Include historical vs current vs modeled vs conditional distinction. A hazard is not evidence of anthropogenic attribution. Generic rural/coastal zones are not named subnational examples. Do not force conflict pathways into low-FCV settings. Not found is not absence.
Do not carry over stale current assertions uncritically; note their dated scope. Include current original documents when accessible.

## Copyright and verification
Use original concise paraphrases. Maximum 180 words per URL across source methodology + source limitations + all claim paraphrases + claim limitations + scenarios + source_stated_fcv_link (including duplicated shared regional URLs). Prefer more independent original sources. No verbatim quotes needed.
Before handoff: parse all owned JSON, validate source rows against source.schema.json, check unique IDs/references, word budgets, four search purposes and named-place classification. Report files, sources/claims, failed accesses, checks, unresolved gaps. All output remains DRAFT.
