"""Validate country directories in the repository evidence bank."""

import argparse
from pathlib import Path
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from climate_bank.validation import validate_country_directory


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--country-dir",
        type=Path,
        help="Validate one explicit country directory instead of the repository bank.",
    )
    parser.add_argument(
        "--require-profile",
        action="store_true",
        help="Require each validated country directory to contain profile.json.",
    )
    parser.add_argument(
        "--schema-version",
        choices=("1.0.0", "1.1.0"),
        default="1.0.0",
        help="Evidence schema version to validate (default: 1.0.0).",
    )
    return parser


def main(argv: list[str] | None = None, root: Path | None = None) -> int:
    args = _parser().parse_args(argv)
    repository_root = Path(root) if root is not None else REPOSITORY_ROOT
    if args.country_dir is not None:
        country_dirs = [args.country_dir]
    else:
        countries_root = repository_root / "countries"
        country_dirs = (
            sorted(path for path in countries_root.iterdir() if path.is_dir())
            if countries_root.is_dir()
            else []
        )
    errors = sorted(
        f"{country_dir.name}: {error}"
        for country_dir in country_dirs
        for error in validate_country_directory(
            country_dir,
            require_profile=args.require_profile,
            schema_version=args.schema_version,
        )
    )
    if errors:
        for error in errors:
            print(error)
        return 1
    print("Climate-FCV country bank validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
