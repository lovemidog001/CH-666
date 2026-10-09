#!/usr/bin/env python3
"""Load configuration and output to GITHUB_OUTPUT"""
import json
import os
import sys

def main():
    gen_path = os.environ.get('GENERATION_CONFIG')
    providers_path = os.environ.get('AI_PROVIDERS_CONFIG')
    channel_config_path = os.environ.get('CHANNEL_CONFIG')
    count_override = os.environ.get('COUNT_OVERRIDE')

    with open(gen_path) as f:
        gen = json.load(f)
    with open(providers_path) as f:
        providers = json.load(f)
    with open(channel_config_path) as f:
        channel_config = json.load(f)

    enabled = gen['daily_generation']['enabled']
    articles = int(count_override or gen['daily_generation']['articles_per_day'])

    # Check if unified channel is enabled
    channel_enabled = channel_config.get('enabled', True)

    out = os.environ.get('GITHUB_OUTPUT')
    with open(out, 'a', encoding='utf-8') as f:
        f.write(f'enabled={enabled}\n')
        f.write(f'channel_enabled={channel_enabled}\n')
        f.write(f'articles_per_day={articles}\n')
        f.write(f'providers_count={len([p for p in providers if p["enabled"]])}\n')
        f.write(f'categories={",".join(channel_config.get("valid_categories", ["3", "6", "9"]))}\n')

    print(f"enabled={enabled}")
    print(f"channel_enabled={channel_enabled}")
    print(f"articles_per_day={articles}")
    print(f"categories={','.join(channel_config.get('valid_categories', ['3', '6', '9']))}")

if __name__ == '__main__':
    main()