# IDA expansion source-extraction contract

Routine source collection only. The coordinator retains country synthesis, pathway
inference, approval decisions and application integration. Work only on your
assigned batch JSON file under research/20261026_ida_expansion/extractions/.

Read CLAUDE.md and schemas/source.schema.json before writing. Use public primary
sources: World Bank/ADB climate profiles and CCDRs, government NAPs/NDCs, UN
agencies, and original climate-security research. Inspect the actual substantive
publisher text. Search snippets, contents pages and catalog metadata cannot verify
claims. An official continuous indexed passage is usable only if recorded honestly
as official-excerpt rather than full-document inspection. Do not infer findings
from document titles or fabricate source URLs, dates, numbers or page locators.

Return a JSON array, one object for every assigned country:
- iso3, country_name
- sources: complete source records matching schemas/source.schema.json. Use
  country-scoped ISO-SRC-001 IDs, accessed_on=2026-10-26 only for actual access,
  repository_file=null, checksum=null; license_status=unknown unless inspected
  terms establish otherwise. Sources actually used must have unique URLs per country.
- claims: source-faithful paraphrases with keys claim_id (ISO-C-001 onward),
  source_id, locator, paraphrase, kind, basis, time_horizons, scenario, geographies,
  administrative_level, hazards, sectors, affected_groups, systems, institutions,
  limitations, access_method. Every claim must be traceable to an inspected passage.
  kind is one of the nine evidence_class values in schemas/evidence.schema.json.
  basis is observed or projected; do not invent your own analytical inferences.
  time_horizons uses the evidence schema enums. Projections need a future horizon;
  record the exact scenario when stated, otherwise say the inspected summary does
  not specify it. Do not assign an invented SSP/RCP or numeric horizon.
  administrative_level uses the schema enum. Other list fields contain only
  source-supported terms. access_method is full-text or official-excerpt.
- access_audit: objects with source_id (or null for rejected sources), url,
  access_method (full-text, official-excerpt, metadata-only, blocked), locator,
  notes, reuse_terms. List failed and metadata-only checks here, never as claims.
- gaps: concrete country-specific gaps and access limitations.

Aim for 3 substantive sources and 6-10 useful claims per country, including
hazards, differentiated vulnerability/capacity and explicit climate-FCV material
where available. This is a research target, not a quota: return fewer verified
claims or explicit access gaps rather than padding. Prefer at least one concrete
subnational example where actually supported. IDA eligibility does not imply
conflict or fragility. Do not invent a climate-conflict link to fill the bank.
Plans describe intentions, not evaluated outcomes; modeled exposure is not an
observed effect. Keep historical/dated findings tied to the source period.

Use original short paraphrases, no copied passages; keep all derived prose per
single source URL within 180 words including methodological/limitation summaries.
No raw PDFs, restricted OPCS sources, credentials, tool citation IDs or source
copies in tracked files. Do not approve anything, edit runtime releases, modify
existing country banks, alter schemas/code, commit, push or deploy. Use apply_patch
for your assigned new JSON file. All other files are read-only. Self-check JSON
parsing, country coverage and source-reference resolution with Python; report
actual checks, counts, gaps and files affected. Do not claim full-document access
or schema validation unless actually performed. Send a progress note after each
4-5 countries. Do not spawn further agents.
