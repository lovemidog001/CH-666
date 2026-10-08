#!/usr/bin/env python3
"""Determine target date and output to GITHUB_OUTPUT"""
import os
import sys
from datetime import datetime, timedelta, timezone

def main():
    force_date = os.environ.get('FORCE_DATE', '')
    tz = timezone(timedelta(hours=8))

    if force_date:
        target = datetime.strptime(force_date, '%Y-%m-%d').replace(tzinfo=tz)
    else:
        now = datetime.now(tz)
        target = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    out = os.environ.get('GITHUB_OUTPUT')
    with open(out, 'a', encoding='utf-8') as f:
        f.write(f'target_date={target.strftime("%Y-%m-%d")}\n')
        f.write(f'target_iso={target.isoformat()}\n')
        f.write(f'tomorrow_iso={(target + timedelta(days=1)).isoformat()}\n')

    print(f"target_date={target.strftime('%Y-%m-%d')}")
    print(f"target_iso={target.isoformat()}")

if __name__ == '__main__':
    main()