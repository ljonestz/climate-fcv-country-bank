"""Assemble versioned draft banks from extraction plus explicit coordinator decisions.

This is a deterministic importer, not an evidence reviewer. It never infers a
pathway, human approval, or a renewed deadline for inherited evidence.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import re

from climate_bank.dossier import build_dossier
from climate_bank.release import write_canonical_json
from climate_bank.validation import _schema_errors, validate_country_directory


ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research/20261026_global_depth'
CLASSES = ('climate-pressure', 'exposure', 'sensitivity', 'coping-capacity',
           'adaptive-capacity', 'institutional-capacity', 'response-performance',
           'direct-climate-fcv', 'resilience-peace-capacity')
NAMED = {'named-admin', 'named-site', 'named-livelihood-zone'}


def read(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def note(text, ids=()):
    return {'text': text, 'evidence_ids': list(ids), 'pathway_ids': []}


def assemble_candidate(raw: dict, decision: dict, *, base_dir: Path | None,
                       version: str) -> tuple[dict, dict]:
    """Return ledgers and an import crosswalk without editing the baseline."""
    iso3 = raw['iso3']
    if decision.get('iso3') != iso3 or decision.get('human_approval') is not False:
        raise ValueError('coordinator decisions must not grant human approval')
    decisions = {r['claim_id']: r for r in decision['claim_decisions']}
    claims = {r['claim_id']: r for r in raw['claims']}
    if len(decisions) != len(decision['claim_decisions']) or set(decisions) != set(claims):
        raise ValueError('every claim requires exactly one explicit decision')
    if len(claims) != len(raw['claims']):
        raise ValueError('duplicate claim ID')
    bundle = {name + '.json': read(base_dir / (name + '.json'))
              for name in ('sources', 'evidence', 'pathways')} if base_dir else {
                  'sources.json': [], 'evidence.json': [], 'pathways.json': []}
    sources, evidence, pathways = (bundle[name] for name in
                                  ('sources.json', 'evidence.json', 'pathways.json'))
    for record in evidence + pathways:
        record.update(review_status='draft', review_date=None)
    source_ids = {s['source_id'] for s in sources}
    source_urls = {s['url'].rstrip('/'): s['source_id'] for s in sources}
    source_mapping = {}
    for source in raw['sources']:
        source = {**source, **decision.get('source_overrides', {}).get(source['source_id'], {})}
        sid = source['source_id']
        if sid in source_mapping or not sid.startswith(iso3 + '-SRC-'):
            raise ValueError(f'duplicate or cross-country source {sid}')
        existing = source_urls.get(source['url'].rstrip('/'))
        if existing:
            source_mapping[sid] = existing
        else:
            if sid in source_ids:
                raise ValueError(f'source ID collision {sid}')
            sources.append(deepcopy(source))
            source_mapping[sid] = sid
            source_ids.add(sid)
            source_urls[source['url'].rstrip('/')] = sid
    evidence_ids = {r['evidence_id'] for r in evidence}
    claim_mapping, named_ids, new_ids = {}, [], []
    for claim in raw['claims']:
        d = decisions[claim['claim_id']]
        if not d.get('reason') or d.get('decision') not in {'include', 'exclude'}:
            raise ValueError('each decision needs include/exclude and a reason')
        if d['decision'] == 'exclude':
            continue
        if claim['access_method'] not in {'full-text', 'official-excerpt'}:
            raise ValueError('metadata-only or blocked sources cannot support evidence')
        eid = claim['claim_id'].replace('-C-', '-E-')
        if eid in evidence_ids or not re.fullmatch(iso3 + r'-E-\d{3}', eid):
            raise ValueError(f'evidence ID collision or invalid ID {eid}')
        tier, direction = d['refresh_tier'], d['interaction_direction']
        if tier not in {'current', 'structural'}:
            raise ValueError('invalid refresh tier')
        source = next(s for s in raw['sources'] if s['source_id'] == claim['source_id'])
        accessed = date.fromisoformat(source['accessed_on'])
        due = (accessed + timedelta(days=90 if tier == 'current' else 365)).isoformat()
        evidence_class = d.get('evidence_class', claim['kind'])
        role = ('direct-climate-fcv' if evidence_class == 'direct-climate-fcv'
                else 'physical-baseline' if evidence_class == 'climate-pressure'
                else 'vulnerability-capacity')
        record = {
            'evidence_id': eid, 'iso3': iso3,
            'statement': d.get('statement', claim['paraphrase']),
            'compact_statement': d.get('compact_statement', d.get('statement', claim['paraphrase'])),
            'evidence_status': claim['basis'], 'analytical_role': role,
            'evidence_class': evidence_class,
            'administrative_level': claim['administrative_level'],
            'ecological_level': None, 'refresh_tier': tier, 'review_due': due,
            'hazard_tags': claim['hazards'], 'impact_tags': [],
            'geographies': d.get('geographies', claim['geographies']),
            'affected_groups': claim['affected_groups'],
            'sectors': claim['sectors'], 'systems_assets_resources': claim['systems'],
            'institutions': claim['institutions'], 'mediator_tags': d.get('mediator_tags', []),
            'interaction_direction': direction,
            'time_horizons': d.get('time_horizons', claim['time_horizons']),
            'scenario': d.get('scenario', claim['scenario']), 'source_refs': [{
                'source_id': source_mapping[claim['source_id']],
                'locator': d.get('locator', claim['locator'])}],
            'confidence': d.get('confidence', 'medium'),
            'uncertainty': d.get('uncertainty', claim['limitations']),
            'review_status': 'draft', 'review_date': None,
        }
        if record['evidence_status'] == 'projected' and not record['scenario']:
            raise ValueError(f'{eid}: projected evidence requires a scenario')
        evidence.append(record)
        evidence_ids.add(eid)
        claim_mapping[claim['claim_id']] = eid
        new_ids.append(eid)
        if d.get('subnational_specificity', claim['subnational_specificity']) in NAMED:
            named_ids.append(eid)
    for pathway in decision['pathways']:
        if pathway['review_status'] != 'draft' or pathway['review_date'] is not None:
            raise ValueError('coordinator pathways must remain draft/null')
        pathways.append(deepcopy(pathway))
    evidence.sort(key=lambda r: r['evidence_id'])
    pathways.sort(key=lambda r: r['pathway_id'])
    sources.sort(key=lambda r: r['source_id'])
    if not evidence:
        raise ValueError('an empty scaffold is not a country bank')
    coverage = []
    for kind in CLASSES:
        ids = [r['evidence_id'] for r in evidence if r['evidence_class'] == kind]
        coverage.append({'dimension': 'evidence-class', 'value': kind,
                         'status': 'partial' if ids else 'gap', 'record_ids': ids,
                         'gap_note': 'Selected source-supported evidence only; not comprehensive.'
                         if ids else 'No dedicated record assembled; absence of evidence is not absence of risk.'})
    coverage.extend([
        {'dimension': 'geography', 'value': 'new named subnational examples',
         'status': 'partial' if named_ids else 'gap', 'record_ids': named_ids,
         'gap_note': 'Named places only; generic rural/coastal zones excluded. No complete local risk ranking.'},
        {'dimension': 'pathway', 'value': 'mediated climate-FCV links',
         'status': 'partial' if pathways else 'gap',
         'record_ids': [p['pathway_id'] for p in pathways],
         'gap_note': 'Conditional mechanisms, not national causal estimates.' if pathways
         else 'No complete supported chain assembled; do not infer one from co-occurrence.'},
    ])
    inherited_profile = read(base_dir / 'profile.json') if base_dir else None
    inherited_gaps = [n['text'] for n in inherited_profile['known_gaps']
                      if n['text'] not in decision.get('superseded_gap_notes', {})] if inherited_profile else []
    retained_raw_gaps = [g for g in raw['gaps'] if g not in decision.get('superseded_gap_notes', {})]
    gaps = list(dict.fromkeys([*inherited_gaps, *retained_raw_gaps, *decision['gaps'],
                              'Draft extension: human source review and approval remain pending. '
                              'Lending eligibility is not an FCV classification.']))
    profile = {
        'iso3': iso3, 'profile_version': version,
        'executive_assessment': decision.get('executive_assessment') or [
            note(r['statement'], [r['evidence_id']]) for r in
            [next((r for r in evidence if r['evidence_id'] in new_ids), evidence[0])]],
        'coverage': coverage,
        'geographic_notes': [note(r['statement'], [r['evidence_id']]) for r in evidence
                             if r['evidence_id'] in named_ids],
        'sector_notes': [], 'known_gaps': [note(g) for g in gaps],
        'selection_aliases': deepcopy(inherited_profile['selection_aliases']) if inherited_profile
                             else {k: {} for k in ('geographies', 'sectors', 'affected_groups',
                                                   'institutions', 'systems_assets', 'hazards')},
        'review_status': 'draft', 'review_date': None,
    }
    old_review = read(base_dir / 'review.json') if base_dir else {}
    review = {
        'iso3': iso3, 'country_name': raw['country_name'],
        'country_aliases': sorted(set(old_review.get('country_aliases', []))
                                  | set(decision.get('country_aliases', []))),
        'status': 'draft', 'reviewer': None, 'reviewed_on': None, 'review_due': None,
        'dossier_path': f'countries/{iso3}/candidates/{version}/dossier.md',
        'evidence_ids': [r['evidence_id'] for r in evidence],
        'pathway_ids': [r['pathway_id'] for r in pathways],
        'decision_notes': 'Unapproved depth extension. Prior snapshots and inherited evidence deadlines '
                          'are preserved. Coordinator decisions are not designated human approval.',
    }
    bundle.update({'profile.json': profile, 'review.json': review})
    errors = []
    for name in ('sources', 'evidence', 'pathways', 'profile', 'review'):
        schema = 'source' if name == 'sources' else 'pathway' if name == 'pathways' else name
        errors.extend(_schema_errors(bundle[name + '.json'], schema + '.schema.json', name))
    if errors:
        raise ValueError(errors)
    trace = {'iso3': iso3, 'base_dir': base_dir.relative_to(ROOT).as_posix() if base_dir else None,
             'claim_evidence_mapping': claim_mapping, 'source_id_mapping': source_mapping,
             'new_evidence_ids': new_ids, 'new_named_local_evidence_ids': named_ids,
             'excluded_claims': [d for d in decision['claim_decisions'] if d['decision'] == 'exclude']}
    return bundle, trace


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iso3', required=True)
    parser.add_argument('--version', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Z]{3}', args.iso3) or not re.fullmatch(r'[A-Za-z0-9.-]+', args.version):
        parser.error('invalid ISO3 or version')
    roster = read(RESEARCH / 'TARGET_COUNTRIES.json')
    existing = {r['iso3']: r for r in roster['existing_countries']}
    phase = 'phase1' if args.iso3 in existing else 'phase2'
    raw_path = RESEARCH / phase / f'{args.iso3}.json'
    raw = read(raw_path)
    decision = read(RESEARCH / 'decisions' / f'{args.iso3}.json')
    digest = hashlib.sha256(raw_path.read_text(encoding='utf-8').encode()).hexdigest()
    if decision.get('extraction_sha256_utf8_lf') != digest:
        raise ValueError('extraction changed since coordinator decision')
    output = ROOT / 'countries' / args.iso3 / 'candidates' / args.version
    if output.exists():
        raise FileExistsError(output)
    base = ROOT / existing[args.iso3]['base_dir'] if args.iso3 in existing else None
    bundle, trace = assemble_candidate(raw, decision, base_dir=base, version=args.version)
    for name, value in bundle.items():
        write_canonical_json(output / name, value)
    errors = validate_country_directory(output, require_profile=True, schema_version='1.1.0')
    if errors:
        raise ValueError(errors)
    (output / 'dossier.md').write_text(build_dossier(output), encoding='utf-8', newline='\n')
    write_canonical_json(RESEARCH / 'assembly' / f'{args.iso3}.json', trace)
    print(f'{args.iso3}: {len(bundle["evidence.json"])} evidence, {len(bundle["pathways.json"])} pathways; DRAFT')


if __name__ == '__main__':
    main()
