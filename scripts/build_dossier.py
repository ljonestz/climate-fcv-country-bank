"""Build one country's deterministic Markdown dossier."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from climate_bank.dossier import build_dossier


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country", required=True)
    return parser


def main(argv: list[str] | None = None, root: Path | None = None) -> int:
    args = _parser().parse_args(argv)
    repository_root = (
        Path(root) if root is not None else Path(__file__).resolve().parents[1]
    )
    country_dir = repository_root / "countries" / args.country
    output_path = country_dir / "dossier.md"
    try:
        dossier = build_dossier(country_dir)
        output_path.write_text(dossier, encoding="utf-8")
    except (OSError, ValueError) as exc:
        print(f"dossier build failed: {exc}", file=sys.stderr)
        return 1

    print(f"{output_path} words={len(dossier.split())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
