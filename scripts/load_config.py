#!/usr/bin/env python3
"""Load configuration and output to GITHUB_OUTPUT"""
import json
import os
import sys

def main():
    gen_path = os.environ.get('GENERATION_CONFIG')
    providers_path = os.environ.get('AI_PROVIDERS_CONFIG')
    channels_path = os.environ.get('CHANNELS_CONFIG')
    channel_code = os.environ.get('MATRIX_CHANNEL')
    count_override = os.environ.get('COUNT_OVERRIDE')

    with open(gen_path) as f:
        gen = json.load(f)
    with open(providers_path) as f:
        providers = json.load(f)
    with open(channels_path) as f:
        channels = json.load(f)

    enabled = gen['daily_generation']['enabled']
    articles = int(count_override or gen['daily_generation']['articles_per_day'])

    channel_enabled = False
    for ch in channels['channels']:
        if ch['code'] == channel_code:
            channel_enabled = ch.get('enabled', True)
            break

    out = os.environ.get('GITHUB_OUTPUT')
    with open(out, 'a', encoding='utf-8') as f:
        f.write(f'enabled={enabled}\n')
        f.write(f'channel_enabled={channel_enabled}\n')
        f.write(f'articles_per_day={articles}\n')
        f.write(f'providers_count={len([p for p in providers if p["enabled"]])}\n')
        f.write(f'channel={channel_code}\n')

    print(f"enabled={enabled}")
    print(f"channel_enabled={channel_enabled}")
    print(f"articles_per_day={articles}")
    print(f"channel={channel_code}")

if __name__ == '__main__':
    main()