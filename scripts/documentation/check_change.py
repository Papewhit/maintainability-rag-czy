"""Check one OpenSpec change's evidence disposition readiness."""
import argparse

from _governance import DEFAULT_ROOT, check_change, print_diagnostics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("change_name")
    args = parser.parse_args()
    result = check_change(DEFAULT_ROOT, args.change_name)
    print_diagnostics(result)
    if not result.errors:
        print(f"Change evidence closure passed: {args.change_name}")
    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
