"""Build a short-lived UNAPPROVED test artifact, never a runtime release.

Normal release validators and promotion deliberately reject this artifact.
Country and record review metadata remain draft/null. No source files are edited.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import date
import hashlib
import json
from pathlib import Path

from climate_bank.release import (
    _parse_generated_at, _validate_release_output_path, write_canonical_json,
)
from climate_bank.validation import validate_country_directory


def build_test_bundle(country_dirs, *, generated_at: str, test_expires_on: str,
                      content_version: str, output_path: Path) -> dict:
    """Validate draft inputs and write a distinct, non-promotable test artifact."""
    generated = _parse_generated_at(generated_at)
    expiry = date.fromisoformat(test_expires_on)
    if not 0 <= (expiry - generated.date()).days <= 7:
        raise ValueError('test artifact lifetime must be zero to seven days')
    if not isinstance(content_version, str) or not content_version.strip():
        raise ValueError('content_version is required')
    output = Path(output_path)
    parts = tuple(p.casefold() for p in output.resolve().parts)
    if not any(parts[i:i + 2] == ('releases', 'testing') for i in range(len(parts) - 1)):
        raise ValueError('test output must be inside releases/testing')
    if output.exists():
        raise FileExistsError(output)
    directories = tuple(Path(p) for p in country_dirs)
    _validate_release_output_path(output, directories, candidate=True)
    if not directories:
        raise ValueError('explicit country directories required')
    countries, country_profiles, sources, evidence, pathways = {}, {}, {}, [], []
    for directory in sorted(directories):
        errors = validate_country_directory(directory, require_profile=True,
                                             schema_version='1.1.0')
        if errors:
            raise ValueError(f'{directory}: {errors}')
        data = {name: json.loads((directory / f'{name}.json').read_text(encoding='utf-8'))
                for name in ('sources', 'evidence', 'pathways', 'review', 'profile')}
        review, profile = data['review'], data['profile']
        iso3 = review['iso3']
        if iso3 in countries:
            raise ValueError(f'duplicate country {iso3}')
        if (review['status'] != 'draft'
                or any(review[k] is not None for k in ('reviewer', 'reviewed_on', 'review_due'))
                or profile['review_status'] != 'draft' or profile['review_date'] is not None
                or any(r['review_status'] != 'draft' or r['review_date'] is not None
                       for r in data['evidence'] + data['pathways'])):
            raise ValueError(f'{iso3}: test inputs must retain draft/null review metadata')
        countries[iso3] = {
            **{k: deepcopy(review[k]) for k in ('iso3', 'status', 'reviewer', 'reviewed_on',
                 'review_due', 'dossier_path', 'evidence_ids', 'pathway_ids', 'decision_notes')},
            'name': review['country_name'], 'aliases': sorted(review['country_aliases']),
            'selection_aliases': deepcopy(profile['selection_aliases']),
        }
        country_profiles[iso3] = {
            'coverage': deepcopy(profile['coverage']),
            'known_gaps': deepcopy(profile['known_gaps']),
        }
        referenced = {ref['source_id'] for r in data['evidence'] for ref in r['source_refs']}
        for source in data['sources']:
            if source['source_id'] in referenced:
                if source['source_id'] in sources:
                    raise ValueError(f'duplicate source {source["source_id"]}')
                sources[source['source_id']] = source
        evidence.extend(data['evidence'])
        pathways.extend(data['pathways'])
    source_rows = [sources[k] for k in sorted(sources)]
    manifest = [{k: v for k, v in s.items() if k != 'checksum'} for s in source_rows]
    checksum = hashlib.sha256(json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                                        separators=(',', ':')).encode('utf-8')).hexdigest()
    bundle = {
        'artifact_kind': 'unapproved-country-bank-test', 'schema_version': '1.1.0',
        'candidate': True, 'content_version': content_version, 'generated_at': generated_at,
        'test_expires_on': test_expires_on, 'countries': dict(sorted(countries.items())),
        'country_profiles': dict(sorted(country_profiles.items())),
        'sources': source_rows, 'evidence_records': sorted(evidence, key=lambda r: r['evidence_id']),
        'pathways': sorted(pathways, key=lambda r: r['pathway_id']),
        'source_manifest_checksum': checksum,
    }
    write_canonical_json(output, bundle)
    return bundle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--country-dir', action='append', type=Path)
    inputs.add_argument('--country-manifest', type=Path)
    parser.add_argument('--generated-at', required=True)
    parser.add_argument('--test-expires-on', required=True)
    parser.add_argument('--content-version', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    directories = args.country_dir
    if args.country_manifest:
        root = Path(__file__).resolve().parents[1]
        names = json.loads(args.country_manifest.read_text(encoding='utf-8'))
        if (not isinstance(names, list) or not names
                or any(not isinstance(n, str) or Path(n).is_absolute()
                       or not (root / n).resolve().is_relative_to(root) for n in names)):
            parser.error('country manifest must list repository-relative input directories')
        directories = [root / n for n in names]
    bundle = build_test_bundle(directories, generated_at=args.generated_at,
                               test_expires_on=args.test_expires_on,
                               content_version=args.content_version, output_path=args.output)
    print(f'UNAPPROVED test artifact: {len(bundle["countries"])} countries -> {args.output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
