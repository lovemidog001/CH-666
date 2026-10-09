#!/usr/bin/env python3
"""Load config and output to GITHUB_OUTPUT for workflow."""
import os
import sys

# Add scripts to path
sys.path.insert(0, os.path.dirname(__file__))

from config import load_config


def main():
    cfg = load_config()
    out = os.environ.get('GITHUB_OUTPUT')

    with open(out, 'a', encoding='utf-8') as f:
        f.write(f"enabled={cfg.enabled}\n")
        f.write(f"articles_per_day={cfg.articles_per_day}\n")
        f.write(f"categories={','.join(cfg.valid_categories)}\n")

    print(f"enabled={cfg.enabled}")
    print(f"articles_per_day={cfg.articles_per_day}")
    print(f"categories={','.join(cfg.valid_categories)}")


if __name__ == '__main__':
    main()