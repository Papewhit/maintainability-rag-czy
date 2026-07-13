"""Validate governed documentation and report non-blocking delivery warnings."""
import argparse

from _governance import DEFAULT_ROOT, print_diagnostics, validate


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    result = validate(DEFAULT_ROOT)
    print_diagnostics(result)
    if not result.errors and not result.warnings:
        print("Documentation governance validation passed.")
    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
