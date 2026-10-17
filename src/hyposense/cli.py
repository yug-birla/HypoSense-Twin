"""Command-line entry point (cross-platform replacement for the blueprint's Makefile targets).

Planned subcommands, added stage by stage: audit (S1), freeze (Freeze), confirm (S9), demo (S10).
"""

from __future__ import annotations

import sys

from hyposense import __version__


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args in ([], ["--version"]):
        print(f"hyposense {__version__} - no subcommands implemented yet (see docs/NEXT_STEPS.md)")
        return 0
    print(f"unknown or unimplemented command: {' '.join(args)}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
