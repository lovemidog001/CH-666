#!/usr/bin/env python3
"""Determine target date for generation."""
import os
import sys
from datetime import datetime, timezone, timedelta


def main():
    force = os.environ.get('FORCE_DATE')
    out = os.environ.get('GITHUB_OUTPUT')

    if force:
        target = force
    else:
        # Default: yesterday in UTC (matches 03:05 UTC schedule for "yesterday's news")
        tz = timezone.utc
        target = (datetime.now(tz) - timedelta(days=1)).strftime('%Y-%m-%d')

    target_iso = target + 'T00:00:00Z'
    tomorrow_iso = (datetime.strptime(target, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d') + 'T00:00:00Z'

    print(f"Target date: {target}")
    if out:
        with open(out, 'a', encoding='utf-8') as f:
            f.write(f"target_date={target}\n")
            f.write(f"target_iso={target_iso}\n")
            f.write(f"tomorrow_iso={tomorrow_iso}\n")
    else:
        print(f"::set-output name=target_date::{target}")
        print(f"::set-output name=target_iso::{target_iso}")
        print(f"::set-output name=tomorrow_iso::{tomorrow_iso}")

    sys.exit(0)


if __name__ == '__main__':
    main()