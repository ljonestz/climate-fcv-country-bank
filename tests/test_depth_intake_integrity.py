"""Validate frozen source intakes, including budgets shared across countries."""

from collections import defaultdict
import re
from urllib.parse import unquote, urlsplit
from pathlib import Path

import pytest

from climate_bank.validation import _schema_errors
from tests.test_global_depth_integrity import read


ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research/20261026_global_depth'
FILES = sorted(RESEARCH.glob('phase[12]/*.json'))
ADMIN = {'national', 'state', 'administrative-area', 'county', 'payam',
         'boma', 'site', 'cross-border', 'not-applicable'}
CLASSES = {'climate-pressure', 'exposure', 'sensitivity', 'coping-capacity',
           'adaptive-capacity', 'institutional-capacity', 'response-performance',
           'direct-climate-fcv', 'resilience-peace-capacity'}
HORIZONS = {'historical', 'current', 'near-term', 'medium-term', 'long-term'}
SPECIFICITY = {'named-admin', 'named-site', 'named-livelihood-zone',
               'generic-zone', 'national', 'cross-border'}
PURPOSES = {'subnational-vulnerability', 'fcv-mediators',
            'reverse-fcv', 'resilience-capacity'}


@pytest.mark.parametrize('file', FILES, ids=lambda p: p.stem)
def test_intake_has_valid_sources_claims_and_audits(file):
    raw = read(file)
    iso = file.stem
    assert raw['iso3'] == iso
    assert not _schema_errors(raw['sources'], 'source.schema.json', iso)
    sources = {s['source_id'] for s in raw['sources']}
    assert len(sources) == len(raw['sources'])
    ids = [c['claim_id'] for c in raw['claims']]
    assert len(ids) == len(set(ids))
    for claim in raw['claims']:
        assert re.fullmatch(iso + r'-C-\d{3}', claim['claim_id'])
        assert claim['source_id'] in sources
        assert claim['kind'] in CLASSES
        assert claim['administrative_level'] in ADMIN
        assert claim['subnational_specificity'] in SPECIFICITY
        assert claim['basis'] in {'observed', 'projected'}
        assert set(claim['time_horizons']) <= HORIZONS
        assert claim['locator'] and claim['paraphrase'] and claim['limitations']
        assert claim['access_method'] in {'full-text', 'official-excerpt'}
        assert 'source_stated_fcv_link' in claim
        # Missing scenario can be explicitly resolved by the adjudication layer.
        if claim['basis'] == 'projected' and not claim['scenario']:
            decision = read(RESEARCH / 'decisions' / f'{iso}.json')
            row = next(d for d in decision['claim_decisions']
                       if d['claim_id'] == claim['claim_id'])
            assert row['decision'] == 'exclude' or row.get('scenario')
    assert PURPOSES <= {r['purpose'] for r in raw['search_audit']}
    assert all(r['query'] and r['outcome'] and isinstance(r['urls'], list)
               for r in raw['search_audit'])
    assert raw['access_audit'] and raw['gaps']


def canonical_url(url):
    parts = urlsplit(url)
    host = parts.hostname.lower().removeprefix('www.')
    path = unquote(parts.path).rstrip('/')
    query = '' if path.lower().endswith('.pdf') else parts.query
    return (host, path, query)


def test_paraphrase_budget_includes_shared_regional_urls():
    words = defaultdict(int)
    countries = defaultdict(set)
    for file in FILES:
        raw = read(file)
        for source in raw['sources']:
            fields = [source['methodology'], source['limitations']]
            for claim in raw['claims']:
                if claim['source_id'] == source['source_id']:
                    fields.extend(claim.get(k) or '' for k in
                                  ('paraphrase', 'limitations', 'scenario',
                                   'source_stated_fcv_link'))
            url = canonical_url(source['url'])
            words[url] += len(' '.join(fields).split())
            countries[url].add(raw['iso3'])
    excess = [(sorted(countries[url]), count, url) for url, count in words.items()
              if count > 180]
    assert not excess, excess
