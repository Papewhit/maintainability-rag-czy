"""Build the governed documentation catalog or query its Finding Inbox."""
import argparse

from _governance import (
    DEFAULT_ROOT,
    catalog,
    finding_inbox,
    finding_inbox_report,
    print_diagnostics,
    source_fingerprint,
    validate,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("build", help="write the validated evidence catalog")
    subcommands.add_parser("inbox", help="print the read-only Global Finding Inbox")
    args = parser.parse_args()
    result = validate(DEFAULT_ROOT, delivery=False)
    if result.errors:
        print_diagnostics(result)
        return 1
    if args.command == "inbox":
        print(finding_inbox_report(result, DEFAULT_ROOT), end="")
        return 0
    output = catalog(result, DEFAULT_ROOT)
    destination = DEFAULT_ROOT / "docs/evidence-catalog.md"
    temporary = destination.with_name(".evidence-catalog.md.tmp")
    temporary.write_text(output, encoding="utf-8")
    temporary.replace(destination)
    print(f"Wrote {_relative_destination(destination)}")
    print(f"Documents: {len(result.sources)}")
    print(f"Inbox entries: {len(finding_inbox(result, DEFAULT_ROOT))}")
    print(f"Fingerprint: {source_fingerprint(result, DEFAULT_ROOT)}")
    return 0


def _relative_destination(destination):
    return destination.relative_to(DEFAULT_ROOT).as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
