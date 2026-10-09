#!/usr/bin/env python3
"""
CH-666 Daily Story Generation Orchestrator
Categories: 3 (CH-333), 6 (CH-666), 9 (CH-999)
Flow: News → Seeds → Dice → AI → Validate → Images → Save → Notify
"""
import sys
import json
import argparse
import os
from pathlib import Path
from datetime import datetime
from typing import List

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent))

from config import Config
from fetch_news import NewsFetcher
from classify import assign_category, DiceRoller
from generate import StoryGenerator, get_providers
from validate import StoryValidator
from images import ImageGenerator
from storage import ContentStorage


# Failure thresholds
MAX_CONSECUTIVE_FAILURES = 3
MAX_CATEGORY_FAILURE_RATE = 0.8


def main():
    parser = argparse.ArgumentParser(description='CH-666 Unified Daily Generation')
    parser.add_argument('--date', required=True, help='Target date YYYY-MM-DD')
    parser.add_argument('--count', type=int, default=6, help='Total stories per day (dice-distributed)')
    parser.add_argument('--config', required=True, help='Generation config path')
    parser.add_argument('--providers', required=True, help='Providers config path')
    parser.add_argument('--channels', required=True, help='Channels config path')
    parser.add_argument('--content-dir', required=True, help='Content directory')
    args = parser.parse_args()

    # Load config
    cfg = Config(args.config, args.providers, args.channels)
    categories = cfg.valid_categories  # ['3', '6', '9']

    print(f"=== CH Unified Generation for {args.date} ===")
    print(f"Total stories: {args.count}")
    print(f"Categories: {', '.join(categories)}")
    print(f"Providers: {len(cfg.providers)}")
    for p in cfg.providers:
        has_key = bool(os.environ.get(p['api_key_env']))
        print(f"  - {p['name']}: {'✓' if has_key else '✗'}")

    # Shared components
    news = NewsFetcher(content_dir=args.content_dir)
    storage = ContentStorage(args.content_dir)
    providers = get_providers(cfg.providers)

    if not providers:
        print("❌ No available AI providers (check API keys)")
        sys.exit(1)

    # Fetch news ONCE for all categories
    print(f"\n[1/7] Fetching latest news...")
    articles = news.fetch_latest_news(max_results=args.count * 3)
    print(f"  Found {len(articles)} candidate articles")

    if not articles:
        print("  No articles, exiting")
        output_results(0, 0, 'none', [], args.date)
        sys.exit(1)

    # Build neutral seeds from all articles first
    neutral_seeds = []
    for art in articles[:args.count * 2]:  # pool of articles
        # Build seed without category config (neutral)
        seed = {
            'seed_id': f"SEED-{art['source_hash'][:8]}",
            'source_title': art['source_title'],
            'source_summary': art['source_summary'],
            'source_content': art.get('source_content', ''),
            'source_url': art['source_url'],
            'source_date': art['source_date'],
            'source_location': art['source_location'],
            'source_language': art['source_language'],
            'unusual_detail': art['unusual_detail'],
            'event': art['event'],
            'people': art.get('people', []),
            'source_hash': art['source_hash'],
            'event_hash': art['event_hash'],
            'reality_level': 50,
        }
        neutral_seeds.append(seed)

    # Assign category to each seed deterministically
    for seed in neutral_seeds:
        seed['category'] = assign_category(seed, categories)

    # Group by category and roll dice
    all_seeds = []
    for cat in categories:
        cat_config = cfg.get_category_config(cat)
        dice_roller = DiceRoller(cat_config)
        cat_seeds = [s for s in neutral_seeds if s['category'] == cat]

        for seed in cat_seeds[:args.count]:
            # Add category-specific info
            seed['category'] = cat
            seed['dice_params'] = dice_roller.roll(seed)
            all_seeds.append(seed)

    print(f"  Created {len(all_seeds)} seeds across categories")

    # Process seeds
    generator = StoryGenerator(providers, {})  # cat_config passed per-seed
    all_stories = []
    all_failed = 0
    last_provider = 'none'

    # Group by category for sequential processing
    for cat in categories:
        cat_config = cfg.get_category_config(cat)
        cat_seeds = [s for s in all_seeds if s['category'] == cat]
        cat_name = cat_config['name']

        print(f"\n{'='*50}")
        print(f"=== {cat_name} ({cat_config['label']}) ===")
        print(f"{'='*50}")

        # Update generator with category config
        generator.cat = cat_config
        generator.genre_labels = generator._build_labels()

        validator = StoryValidator(cat_config)
        img_gen = ImageGenerator(
            os.environ.get('AGNES_API_KEY', ''),
            os.environ.get('FTP_HOST', ''),
            os.environ.get('FTP_USER', ''),
            os.environ.get('FTP_PASS', ''),
            os.environ.get('FTP_PATH', ''),
            os.environ.get('SITE_URL', ''),
        )

        cat_generated = 0
        cat_failed = 0
        consecutive_fail = 0

        for i, seed in enumerate(cat_seeds):
            # Failure thresholds
            if consecutive_fail >= MAX_CONSECUTIVE_FAILURES:
                print(f"  ⚠️ {consecutive_fail} consecutive failures, skipping remaining")
                cat_failed += len(cat_seeds) - i
                break
            processed = i
            if processed > 0 and cat_failed / processed > MAX_CATEGORY_FAILURE_RATE:
                print(f"  ⚠️ Failure rate {cat_failed}/{processed} > 80%, skipping")
                cat_failed += len(cat_seeds) - i
                break

            print(f"\n  Seed {i+1}/{len(cat_seeds)}: {seed['seed_id']}")
            dice = seed['dice_params']
            print(f"    Horror: {dice['horror_score']}, Types: {dice['horror_type']}, Fantasy: {dice['fantasy_level']}")

            # Generate story
            gen_result = generator.generate(seed, dice)
            if not gen_result['success']:
                print(f"    ❌ Generation failed: {gen_result.get('error')}")
                cat_failed += 1
                consecutive_fail += 1
                continue

            last_provider = gen_result['provider_used']
            story_data = gen_result['story']
            print(f"    ✅ Generated: {story_data['title'][:40]}... via {last_provider}")

            # Validate
            is_valid, errors = validator.validate(story_data)
            if not is_valid:
                print(f"    ❌ Validation failed: {errors}")
                cat_failed += 1
                consecutive_fail += 1
                continue

            # Generate images
            print(f"    Generating images...")
            img_urls = img_gen.process_story(
                {**story_data, 'category': cat, 'horror_type': dice['horror_type'],
                 'fantasy_level': dice['fantasy_level'], 'perspective': dice['perspective']},
                dice
            )

            # Build & save full story JSON
            story = storage.build_story(seed, story_data, dice, last_provider, img_urls)
            storage.save_story(story)
            storage.save_prompts(story['story_code'], img_gen.generate_prompts(story, dice))

            all_stories.append(story)
            cat_generated += 1
            consecutive_fail = 0
            print(f"    💾 Saved: {story['story_code']}")

        print(f"\n  --- {cat_name}: Generated {cat_generated}, Failed {cat_failed} ---")
        all_failed += cat_failed

    # Save daily merged
    print(f"\n[7/7] Saving daily merged JSON...")
    if all_stories:
        storage.save_daily(args.date, all_stories)
        print(f"  Saved {len(all_stories)} stories to daily/{args.date}.json")

    # Mark sources used
    news.mark_sources_used(all_stories)

    # Output for GitHub Actions
    story_codes = [s['story_code'] for s in all_stories]
    output_results(len(all_stories), all_failed, last_provider, story_codes, args.date)

    if len(all_stories) == 0:
        print("❌ No stories generated")
        sys.exit(1)

    print(f"\n✅ Done: {len(all_stories)} stories generated")


def output_results(gen: int, failed: int, provider: str, codes: List[str], date: str):
    out = os.environ.get('GITHUB_OUTPUT')
    if out:
        with open(out, 'a', encoding='utf-8') as f:
            f.write(f"generated_count={gen}\n")
            f.write(f"failed_count={failed}\n")
            f.write(f"provider_used={provider}\n")
            f.write(f"story_codes={','.join(codes)}\n")
            f.write(f"date={date}\n")
    else:
        print(f"::set-output name=generated_count::{gen}")
        print(f"::set-output name=failed_count::{failed}")
        print(f"::set-output name=provider_used::{provider}")
        print(f"::set-output name=story_codes::{','.join(codes)}")
        print(f"::set-output name=date::{date}")


if __name__ == '__main__':
    main()