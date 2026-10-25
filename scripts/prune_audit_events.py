#!/usr/bin/env python3
"""Apply an explicitly chosen audit-event retention cutoff."""

from __future__ import annotations

import argparse
from datetime import datetime

from praxis_api.sqlite_operations import audit_event_count, prune_audit_events


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", help="SQLite database URL")
    parser.add_argument("--before", required=True, help="ISO-8601 cutoff timestamp")
    parser.add_argument("--owner-id", help="limit deletion to one owner")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    cutoff = datetime.fromisoformat(args.before)
    if args.dry_run:
        print(f"Audit events retained: {audit_event_count(args.database)}")
        print(f"Dry run; would prune events before {cutoff.isoformat()}")
        return 0
    deleted = prune_audit_events(args.database, cutoff, args.owner_id)
    print(f"Deleted {deleted} audit event(s); retained {audit_event_count(args.database)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
