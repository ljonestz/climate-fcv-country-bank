"""A test artifact must not change or impersonate an approved runtime release."""

import json
from pathlib import Path

import pytest

from climate_bank.release import promote_release
from climate_bank.validation import validate_runtime_release
from scripts.build_test_bundle import build_test_bundle
from scripts import build_test_bundle as test_cli


ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / 'countries/BDI/candidates/2026.10.26'


def test_build_keeps_drafts_and_is_not_a_runtime_release(tmp_path):
    output = tmp_path / 'releases/testing/runtime.json'
    bundle = build_test_bundle([DRAFT], generated_at='2026-10-26T00:00:00Z',
                               test_expires_on='2026-10-27', content_version='test',
                               output_path=output)
    assert bundle['artifact_kind'] == 'unapproved-country-bank-test'
    assert bundle['candidate'] is True
    assert bundle['countries']['BDI']['status'] == 'draft'
    assert bundle['countries']['BDI']['reviewer'] is None
    assert bundle['countries']['BDI']['review_due'] is None
    profile = json.loads((DRAFT / 'profile.json').read_text(encoding='utf-8'))
    assert bundle['country_profiles']['BDI'] == {
        'coverage': profile['coverage'], 'known_gaps': profile['known_gaps']
    }
    assert all(r['review_status'] == 'draft' and r['review_date'] is None
               for r in bundle['evidence_records'])
    assert json.loads(output.read_text(encoding='utf-8')) == bundle
    assert validate_runtime_release(bundle)
    with pytest.raises(ValueError):
        promote_release([DRAFT], generated_at='2026-10-26T00:00:00Z',
                        content_version='test', current_dir=tmp_path / 'current')


@pytest.mark.parametrize('relative', ['releases/current/runtime.json', 'runtime.json',
                                   'releases/testing/../current/runtime.json'])
def test_output_is_restricted_to_testing(tmp_path, relative):
    with pytest.raises(ValueError):
        build_test_bundle([DRAFT], generated_at='2026-10-26T00:00:00Z',
                          test_expires_on='2026-10-27', content_version='test',
                          output_path=tmp_path / relative)


def test_existing_artifact_is_not_overwritten(tmp_path):
    output = tmp_path / 'releases/testing/runtime.json'
    output.parent.mkdir(parents=True)
    output.write_text('preserve', encoding='utf-8')
    with pytest.raises(FileExistsError):
        build_test_bundle([DRAFT], generated_at='2026-10-26T00:00:00Z',
                          test_expires_on='2026-10-27', content_version='test',
                          output_path=output)
    assert output.read_text(encoding='utf-8') == 'preserve'


@pytest.mark.parametrize('expiry', ['2026-10-25', '2026-11-03', 'invalid'])
def test_test_lifetime_is_at_most_seven_days(tmp_path, expiry):
    with pytest.raises(ValueError):
        build_test_bundle([DRAFT], generated_at='2026-10-26T00:00:00Z',
                          test_expires_on=expiry, content_version='test',
                          output_path=tmp_path / 'releases/testing/runtime.json')


def test_cli_can_read_explicit_repository_relative_inputs_manifest(tmp_path):
    manifest = tmp_path / 'inputs.json'
    manifest.write_text(json.dumps([DRAFT.relative_to(ROOT).as_posix()]), encoding='utf-8')
    output = tmp_path / 'releases/testing/runtime.json'
    assert test_cli.main(['--country-manifest', str(manifest),
        '--generated-at', '2026-10-26T00:00:00Z', '--test-expires-on', '2026-10-27',
        '--content-version', 'manifest-test', '--output', str(output)]) == 0
    assert set(json.loads(output.read_text(encoding='utf-8'))['countries']) == {'BDI'}
