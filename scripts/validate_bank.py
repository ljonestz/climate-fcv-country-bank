"""Validate every country directory in the repository evidence bank."""

from pathlib import Path

from climate_bank.validation import validate_country_directory


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    countries_root = REPOSITORY_ROOT / "countries"
    country_dirs = (
        sorted(path for path in countries_root.iterdir() if path.is_dir())
        if countries_root.is_dir()
        else []
    )
    errors = sorted(
        f"{country_dir.name}: {error}"
        for country_dir in country_dirs
        for error in validate_country_directory(country_dir)
    )
    if errors:
        for error in errors:
            print(error)
        return 1
    print("Climate-FCV country bank validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
