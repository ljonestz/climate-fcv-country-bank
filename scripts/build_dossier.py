"""Build or check one deterministic Markdown dossier."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from climate_bank.dossier import build_dossier


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--country")
    target.add_argument("--country-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the existing output differs; do not write.",
    )
    return parser


def main(argv: list[str] | None = None, root: Path | None = None) -> int:
    args = _parser().parse_args(argv)
    repository_root = (
        Path(root) if root is not None else Path(__file__).resolve().parents[1]
    )
    country_dir = (
        args.country_dir
        if args.country_dir is not None
        else repository_root / "countries" / args.country
    )
    output_path = args.output or country_dir / "dossier.md"
    try:
        dossier = build_dossier(country_dir)
        if args.check:
            if not output_path.is_file():
                print(f"dossier check failed: {output_path}: missing file", file=sys.stderr)
                return 1
            if output_path.read_text(encoding="utf-8") != dossier:
                print(f"dossier check failed: {output_path}: differs from generated dossier", file=sys.stderr)
                return 1
        else:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(dossier, encoding="utf-8")
    except (OSError, ValueError) as exc:
        print(f"dossier build failed: {exc}", file=sys.stderr)
        return 1

    action = "checked" if args.check else "wrote"
    print(f"{output_path} {action} words={len(dossier.split())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
