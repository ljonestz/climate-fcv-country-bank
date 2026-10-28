"""Assembly is explicit, traceable, draft-only, and preserves prior snapshots."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from scripts.assemble_depth_candidates import assemble_candidate


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'countries/BDI/candidates/2026.10.26'


def inputs():
    source = json.loads((BASE / 'sources.json').read_text(encoding='utf-8'))[0]
    source = {**source, 'source_id': 'BDI-SRC-101'}
    raw = {'iso3': 'BDI', 'country_name': 'Burundi', 'sources': [source], 'claims': [{
        'claim_id': 'BDI-C-101', 'source_id': 'BDI-SRC-101', 'locator': 'Synthetic test section',
        'paraphrase': 'Synthetic local vulnerability statement for assembly testing only.',
        'kind': 'sensitivity', 'basis': 'observed', 'time_horizons': ['historical'],
        'scenario': None, 'geographies': ['Synthetic place'], 'administrative_level': 'site',
        'hazards': ['flood'], 'sectors': ['water'], 'affected_groups': ['residents'],
        'systems': ['water supply'], 'institutions': [], 'limitations': 'Synthetic claim.',
        'access_method': 'full-text', 'subnational_specificity': 'named-site',
        'source_stated_fcv_link': None,
    }], 'gaps': ['No causal inference from the synthetic statement.']}
    decision = {'iso3': 'BDI', 'human_approval': False, 'claim_decisions': [{
        'claim_id': 'BDI-C-101', 'decision': 'include', 'reason': 'Synthetic contract test.',
        'refresh_tier': 'structural', 'interaction_direction': 'contextual',
    }], 'pathways': [], 'gaps': []}
    return raw, decision


def test_assembly_preserves_ids_deadlines_and_creates_only_drafts():
    raw, decision = inputs()
    before = {p.name: p.read_bytes() for p in BASE.iterdir() if p.is_file()}
    bundle, trace = assemble_candidate(raw, decision, base_dir=BASE, version='test-depth')
    old = json.loads(before['evidence.json'])
    assert bundle['evidence.json'][-1]['evidence_id'] == 'BDI-E-101'
    for original, result in zip(old, bundle['evidence.json']):
        assert result == {**original, 'review_status': 'draft', 'review_date': None}
    assert all(r['review_status'] == 'draft' and r['review_date'] is None
               for r in bundle['evidence.json'] + bundle['pathways.json'])
    assert bundle['review.json']['reviewer'] is None
    assert bundle['review.json']['review_due'] is None
    assert trace['claim_evidence_mapping'] == {'BDI-C-101': 'BDI-E-101'}
    # Same URL reuses the old canonical source ID, not a duplicate definition.
    assert len(bundle['sources.json']) == len(json.loads(before['sources.json']))
    assert bundle['evidence.json'][-1]['source_refs'][0]['source_id'] != 'BDI-SRC-101'
    assert before == {p.name: p.read_bytes() for p in BASE.iterdir() if p.is_file()}


def test_every_claim_needs_an_explicit_coordinator_decision():
    raw, decision = inputs()
    decision['claim_decisions'] = []
    with pytest.raises(ValueError, match='decision'):
        assemble_candidate(raw, decision, base_dir=BASE, version='test-depth')


def test_excluded_claim_is_not_imported():
    raw, decision = inputs()
    decision['claim_decisions'][0]['decision'] = 'exclude'
    bundle, trace = assemble_candidate(raw, decision, base_dir=BASE, version='test-depth')
    assert len(bundle['evidence.json']) == len(json.loads((BASE / 'evidence.json').read_text()))
    assert trace['claim_evidence_mapping'] == {}


def test_assembly_cannot_approve_or_create_implicit_pathways():
    raw, decision = inputs()
    decision['human_approval'] = True
    with pytest.raises(ValueError, match='approval'):
        assemble_candidate(raw, decision, base_dir=BASE, version='test-depth')
    raw, decision = inputs()
    bundle, _ = assemble_candidate(raw, decision, base_dir=None, version='test-depth')
    assert bundle['pathways.json'] == []
    assert bundle['profile.json']['coverage'][-1]['status'] == 'gap'


def test_explicit_edits_keep_provenance_and_add_country_aliases():
    raw, decision = inputs()
    decision['country_aliases'] = ['Synthetic Burundi alias']
    decision['claim_decisions'][0].update(statement='Explicit scoped correction.',
        locator='Corrected one-based PDF p.2', time_horizons=['historical'],
        subnational_specificity='generic-zone')
    bundle, trace = assemble_candidate(raw, decision, base_dir=BASE, version='test-depth')
    record = bundle['evidence.json'][-1]
    assert record['statement'] == 'Explicit scoped correction.'
    assert record['source_refs'][0]['locator'] == 'Corrected one-based PDF p.2'
    assert record['time_horizons'] == ['historical']
    assert trace['new_named_local_evidence_ids'] == []
    assert 'Synthetic Burundi alias' in bundle['review.json']['country_aliases']


def test_evidence_class_override_also_updates_analytical_role():
    raw, decision = inputs()
    raw['claims'][0]['kind'] = 'direct-climate-fcv'
    decision['claim_decisions'][0]['evidence_class'] = 'coping-capacity'
    bundle, _ = assemble_candidate(raw, decision, base_dir=None, version='test-depth')
    record = bundle['evidence.json'][0]
    assert record['evidence_class'] == 'coping-capacity'
    assert record['analytical_role'] == 'vulnerability-capacity'


def test_invalid_intake_enum_is_rejected_before_output_can_be_written():
    raw, decision = inputs()
    raw['claims'][0]['administrative_level'] = 'region'
    with pytest.raises(ValueError, match='schema'):
        assemble_candidate(raw, decision, base_dir=None, version='test-depth')


def test_projected_claim_requires_explicit_scenario_before_writing():
    raw, decision = inputs()
    raw['claims'][0]['basis'] = 'projected'
    with pytest.raises(ValueError, match='scenario'):
        assemble_candidate(raw, decision, base_dir=None, version='test-depth')


def test_coordinator_can_supply_source_stated_qualitative_scenario():
    raw, decision = inputs()
    raw['claims'][0]['basis'] = 'projected'
    scenario = 'Qualitative risk narrative; no emissions scenario specified.'
    decision['claim_decisions'][0]['scenario'] = scenario
    bundle, _ = assemble_candidate(raw, decision, base_dir=None, version='test-depth')
    assert bundle['evidence.json'][0]['scenario'] == scenario
