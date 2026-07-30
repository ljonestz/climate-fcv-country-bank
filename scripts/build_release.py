"""Build the current approved runtime release."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from climate_bank.release import build_release, write_canonical_json


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generated-at", required=True)
    return parser


def main(argv: list[str] | None = None, root: Path | None = None) -> int:
    args = _parser().parse_args(argv)
    repository_root = (
        Path(root) if root is not None else Path(__file__).resolve().parents[1]
    )
    countries_root = repository_root / "countries"
    country_dirs = (
        sorted(path for path in countries_root.iterdir() if path.is_dir())
        if countries_root.is_dir()
        else []
    )
    output_path = repository_root / "releases" / "current" / "runtime.json"
    try:
        release = build_release(country_dirs, generated_at=args.generated_at)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        write_canonical_json(output_path, release)
    except (OSError, ValueError) as exc:
        print(f"release build failed: {exc}", file=sys.stderr)
        return 1

    print(
        f"{output_path} content_version={release['content_version']} "
        f"countries={len(release['countries'])} "
        f"sources={len(release['sources'])} "
        f"evidence={len(release['evidence_records'])} "
        f"pathways={len(release['pathways'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
