#!/usr/bin/env python3
"""Create and verify a consistent backup of a Praxis SQLite database."""

from __future__ import annotations

import argparse

from praxis_api.sqlite_operations import backup_sqlite


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="source SQLite URL, e.g. sqlite:////var/lib/praxis.db")
    parser.add_argument("destination", help="destination SQLite URL")
    args = parser.parse_args()
    destination = backup_sqlite(args.source, args.destination)
    print(f"SQLite backup verified: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
