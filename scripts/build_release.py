"""Build a candidate runtime release or explicitly promote approved content."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from climate_bank.release import (  # noqa: E402
    CANDIDATE_SCHEMA_VERSION,
    CONTENT_VERSION,
    SCHEMA_VERSION,
    build_release,
    promote_release,
    write_canonical_json,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generated-at", required=True)
    parser.add_argument(
        "--country-dir",
        action="append",
        type=Path,
        help="Explicit country directory; repeat for multiple countries.",
    )
    parser.add_argument(
        "--schema-version",
        choices=(SCHEMA_VERSION, CANDIDATE_SCHEMA_VERSION),
    )
    parser.add_argument("--content-version")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--promote", action="store_true")
    parser.add_argument("--current-dir", type=Path)
    return parser


def _country_dirs(args: argparse.Namespace, repository_root: Path) -> list[Path]:
    if args.country_dir:
        return sorted(args.country_dir, key=lambda path: str(path))
    countries_root = repository_root / "countries"
    return (
        sorted(path for path in countries_root.iterdir() if path.is_dir())
        if countries_root.is_dir()
        else []
    )


def main(argv: list[str] | None = None, root: Path | None = None) -> int:
    args = _parser().parse_args(argv)
    repository_root = (
        Path(root) if root is not None else Path(__file__).resolve().parents[1]
    )

    try:
        if args.promote:
            if not args.country_dir:
                raise ValueError("promotion requires explicit --country-dir input")
            if args.current_dir is None:
                raise ValueError("promotion requires explicit --current-dir")
            if args.content_version is None:
                raise ValueError("promotion requires explicit --content-version")
            if (
                args.schema_version is not None
                and args.schema_version != CANDIDATE_SCHEMA_VERSION
            ):
                raise ValueError("promotion schema_version must be 1.1.0")
            release = promote_release(
                _country_dirs(args, repository_root),
                generated_at=args.generated_at,
                content_version=args.content_version,
                current_dir=args.current_dir,
            )
            output_path = args.current_dir / "runtime.json"
        else:
            schema_version = args.schema_version or SCHEMA_VERSION
            content_version = args.content_version or CONTENT_VERSION
            if schema_version == CANDIDATE_SCHEMA_VERSION:
                if not args.country_dir:
                    raise ValueError(
                        "candidate build requires explicit --country-dir input"
                    )
                if args.output is None:
                    raise ValueError("candidate build requires explicit --output")
                if args.content_version is None:
                    raise ValueError(
                        "candidate build requires explicit --content-version"
                    )
                output_path = args.output
                release = build_release(
                    _country_dirs(args, repository_root),
                    generated_at=args.generated_at,
                    schema_version=schema_version,
                    content_version=content_version,
                    output_path=output_path,
                )
            else:
                output_path = (
                    args.output
                    if args.output is not None
                    else repository_root
                    / "releases"
                    / "current"
                    / "runtime.json"
                )
                release = build_release(
                    _country_dirs(args, repository_root),
                    generated_at=args.generated_at,
                    schema_version=schema_version,
                    content_version=content_version,
                )
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
