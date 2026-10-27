"""Draft depth extensions reproduce their decisions without altering the baseline."""

import hashlib
import json
from pathlib import Path

import pytest

from climate_bank.dossier import build_dossier
from climate_bank.validation import validate_country_directory
from scripts.assemble_depth_candidates import assemble_candidate


ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research/20261026_global_depth'
VERSION = '2026.10.26.deep'


def test_final_scope_has_all_146_countries_and_no_unreviewed_scaffolds():
    roster = read(RESEARCH / 'TARGET_COUNTRIES.json')
    existing = {r['iso3'] for r in roster['existing_countries']}
    added = {r['iso3'] for r in roster['additional_ibrd']}
    assert len(existing) == 84 and len(added) == 62
    assert not existing & added
    expected = existing | added
    completed = {p.parents[1].name for p in
                 (ROOT / 'countries').glob(f'*/candidates/{VERSION}')}
    assert completed == expected, f'missing: {sorted(expected - completed)}'
    assert {p.stem for p in (RESEARCH / 'phase1').glob('*.json')} == existing
    assert {p.stem for p in (RESEARCH / 'phase2').glob('*.json')} == added
    for layer in ('decisions', 'assembly'):
        assert {p.stem for p in (RESEARCH / layer).glob('*.json')} == expected


def read(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            assert key not in result, f'duplicate JSON key: {key}'
            result[key] = value
        return result
    text = path.read_text(encoding='utf-8')
    assert '\ufffd' not in text, f'corrupt Unicode: {path}'
    return json.loads(text, object_pairs_hook=unique)


def test_prior_snapshots_code_approvals_and_current_release_are_unchanged():
    freeze = read(ROOT / 'reviews/20261026_global-depth-baseline-freeze.json')
    assert freeze['baseline_commit'] == '97dec8a6c5f94f3cc2c8df6e73f9aac51bbfa643'
    assert freeze['algorithm'] == 'sha256-utf8-lf'
    assert len(freeze['files']) == 878
    for relative, expected in freeze['files'].items():
        actual = hashlib.sha256((ROOT / relative).read_text(encoding='utf-8').encode()).hexdigest()
        assert actual == expected, relative


@pytest.mark.parametrize('directory', sorted((ROOT / 'countries').glob(f'*/candidates/{VERSION}')),
                         ids=lambda p: p.parents[1].name)
def test_completed_country_is_valid_draft_and_reproduces_adjudication(directory):
    iso3 = directory.parents[1].name
    roster = read(RESEARCH / 'TARGET_COUNTRIES.json')
    existing = {r['iso3']: r for r in roster['existing_countries']}
    phase = 'phase1' if iso3 in existing else 'phase2'
    raw_path = RESEARCH / phase / f'{iso3}.json'
    raw = read(raw_path)
    decision = read(RESEARCH / 'decisions' / f'{iso3}.json')
    assert decision['extraction_sha256_utf8_lf'] == hashlib.sha256(
        raw_path.read_text(encoding='utf-8').encode()).hexdigest()
    base = ROOT / existing[iso3]['base_dir'] if iso3 in existing else None
    expected, trace = assemble_candidate(raw, decision, base_dir=base, version=VERSION)
    for name, records in expected.items():
        assert read(directory / name) == records, f'{iso3}/{name}'
    assert read(RESEARCH / 'assembly' / f'{iso3}.json') == trace
    assert directory.joinpath('dossier.md').read_text(encoding='utf-8') == build_dossier(directory)
    assert not validate_country_directory(directory, require_profile=True, schema_version='1.1.0')
    assert decision['human_approval'] is False
    assert trace['new_evidence_ids'], f'{iso3}: no accepted depth addition'


def test_restricted_uzbekistan_atlas_has_no_substantive_intake_or_bank_evidence():
    raw = read(RESEARCH / 'phase1/UZB.json')
    assert not {c['claim_id'] for c in raw['claims']} & {'UZB-C-101', 'UZB-C-102', 'UZB-C-103'}
    directory = ROOT / f'countries/UZB/candidates/{VERSION}'
    evidence = read(directory / 'evidence.json')
    assert all(ref['source_id'] != 'UZB-SRC-101' for e in evidence for ref in e['source_refs'])
