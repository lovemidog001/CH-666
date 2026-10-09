#!/usr/bin/env python3
"""
ODDITY HUB / CH-666 每日故事生成主程式
統一頻道：CH (包含分類 3/6/9)
整合：新聞取得 -> Seed -> Director -> Dice -> 生成 -> 驗證 -> JSON -> 儲存 -> 通知
"""

import sys
import json
import argparse
import os
from datetime import datetime
from pathlib import Path

# 加入 scripts 目錄到路徑
sys.path.insert(0, str(Path(__file__).parent))

from config_loader import Config
from fetch_news import NewsFetcher
from build_seed import SeedBuilder
from story_director import StoryDirector
from director_dice import DirectorDice
from generate_story import StoryGenerator
from validate_story import StoryValidator
from build_json import JSONBuilder
from save_content import ContentSaver


def main():
    parser = argparse.ArgumentParser(description='CH-666 Unified Daily Story Generation (Categories 3/6/9)')
    parser.add_argument('--date', required=True, help='Target date (YYYY-MM-DD)')
    parser.add_argument('--count', type=int, default=5, help='Number of stories to generate per category (default 5)')
    parser.add_argument('--config', required=True, help='Generation config path')
    parser.add_argument('--providers', required=True, help='AI providers config path')
    parser.add_argument('--channel-config', required=True, help='Unified channel config path')
    parser.add_argument('--content-dir', required=True, help='Content directory')
    
    args = parser.parse_args()
    
    # 載入設定
    config = Config(args.config, args.providers, args.channel_config)
    
    print(f"=== CH Unified Generation for {args.date} ===")
    print(f"Requested per category: {args.count} stories")
    print(f"Categories: {', '.join(config.categories)}")
    print(f"Available providers: {len(config.providers)}")
    for p in config.providers:
        has_key = bool(os.environ.get(p['api_key_env']))
        print(f"  - {p['name']} ({p['model']}): {'✓' if has_key else '✗'}")
    
    # 初始化共用組件
    news_fetcher = NewsFetcher(api_key='', content_dir=args.content_dir)
    news_fetcher.api_key = os.environ.get('NEWSAPI_KEY', '')
    seed_builder = SeedBuilder(args.content_dir)
    
    all_generated_stories = []
    all_failed_count = 0
    all_provider_used = 'none'
    all_story_codes = []
    
    # 對每個分類生成故事
    for category in config.categories:
        cat_config = config.get_category_config(category)
        cat_name = cat_config['name']  # CH-333, CH-666, CH-999
        cat_label = cat_config['label']
        cat_color = cat_config['color']
        
        print(f"\n{'='*60}")
        print(f"=== Category {category} ({cat_name} / {cat_label}) ===")
        print(f"{'='*60}")
        
        # 初始化分類專用組件
        director = StoryDirector(cat_config)
        dice = DirectorDice(cat_config)
        generator = StoryGenerator(config.providers, cat_config)
        validator = StoryValidator(cat_config)
        json_builder = JSONBuilder(cat_config, args.content_dir)
        saver = ContentSaver(args.content_dir, cat_name)
        
        # 1. 取得最新新聞（每個分類獨立取得，或共用）
        print(f"\n[1/8] Fetching latest news for {cat_name}...")
        articles = news_fetcher.fetch_latest_news(max_results=args.count * 3)
        print(f"  Found {len(articles)} candidate articles")
        
        if not articles:
            print(f"  No articles available for {cat_name}, skipping")
            continue
        
        # 2. 建立 Seeds
        print(f"\n[2/8] Building seeds for {cat_name}...")
        seeds = []
        for article in articles[:args.count]:
            seed = seed_builder.build_seed(article, cat_config)
            seed['category'] = category
            seeds.append(seed)
            seed_builder.save_seed(seed)
        print(f"  Created {len(seeds)} seeds")
        
        # 3-7. 對每個 seed 生成故事
        cat_generated = 0
        cat_failed = 0
        cat_provider = 'none'
        
        for i, seed in enumerate(seeds):
            print(f"\n--- Processing seed {i+1}/{len(seeds)}: {seed['seed_id']} ---")
            
            try:
                # 3. Story Director 分析
                print("  [3] Story Director analyzing...")
                analysis = director.analyze_seed(seed)
                direction = director.decide_direction(analysis)
                print(f"    Anomaly: {analysis['anomaly_core']}")
                print(f"    Reality: {analysis['reality_level']}")
                
                # 4. Director Dice
                print("  [4] Director Dice rolling...")
                dice_result = dice.roll(seed, direction)
                print(f"    Horror Score: {dice_result['horror_score']}")
                print(f"    Horror Type: {dice_result['horror_type']}")
                print(f"    Fantasy: {dice_result['fantasy_level']}")
                print(f"    Style: {dice_result['narrative_style']}")
                
                # 5. 生成故事
                print("  [5] Generating story...")
                gen_result = generator.generate(seed, dice_result, direction)
                print(f"    gen_result: {gen_result}")
                
                if not gen_result['success']:
                    print(f"    FAILED: {gen_result.get('error')}")
                    cat_failed += 1
                    all_failed_count += 1
                    continue
                
                cat_provider = gen_result['provider_used']
                all_provider_used = cat_provider
                story_data = gen_result['story']
                print(f"    Generated: {story_data.get('title', '')[:40]}... via {cat_provider}")
                
                # 6. 驗證
                print("  [6] Validating...")
                
                story_json = json_builder.build_story_json_from_ai(
                    seed, story_data, dice_result, direction, cat_provider
                )
                
                is_valid, errors = validator.validate(story_json)
                if not is_valid:
                    print(f"    Validation failed: {errors}")
                    cat_failed += 1
                    all_failed_count += 1
                    continue
                
                # 驗證 Image Prompts
                image_prompts = json_builder.build_image_prompts(story_json, direction)
                img_valid, img_errors = validator.validate_image_prompts(image_prompts)
                if not img_valid:
                    print(f"    Image prompt validation failed: {img_errors}")
                
                print("    Validation passed")
                
                # 7. 儲存
                print("  [7] Saving...")
                saver.save_story(story_json)
                saver.save_image_prompts(story_json['story_code'], image_prompts)
                
                all_generated_stories.append(story_json)
                all_story_codes.append(story_json['story_code'])
                cat_generated += 1
                print(f"    Saved: {story_json['story_code']}")
                
            except Exception as e:
                print(f"    ERROR: {e}")
                import traceback
                traceback.print_exc()
                cat_failed += 1
                all_failed_count += 1
        
        print(f"\n--- {cat_name} Summary: Generated {cat_generated}, Failed {cat_failed} ---")
    
    # 8. 儲存每日合併 JSON（所有分類合併）
    print(f"\n[8] Saving daily merged JSON...")
    if all_generated_stories:
        # 使用第一個分類的 saver 來存合併檔（或建立統一 saver）
        first_cat = config.get_category_config(config.categories[0])
        unified_saver = ContentSaver(args.content_dir, first_cat['name'])
        unified_saver.save_stories_merged(args.date, all_generated_stories)
        print(f"    Saved merged: {args.date}.json ({len(all_generated_stories)} stories)")
    
    # 9. 標記新聞來源為已使用
    print("\n[9] Marking sources as used...")
    news_fetcher.mark_sources_used([s for s in all_generated_stories if s.get('source_url')])
    
    # 輸出給 GitHub Actions
    github_output = os.environ.get('GITHUB_OUTPUT')
    if github_output:
        with open(github_output, 'a', encoding='utf-8') as f:
            f.write(f"generated_count={len(all_generated_stories)}\n")
            f.write(f"failed_count={all_failed_count}\n")
            f.write(f"provider_used={all_provider_used}\n")
            f.write(f"story_codes={','.join(all_story_codes)}\n")
            f.write(f"channel=CH\n")
    else:
        print(f"::set-output name=generated_count::{len(all_generated_stories)}")
        print(f"::set-output name=failed_count::{all_failed_count}")
        print(f"::set-output name=provider_used::{all_provider_used}")
        print(f"::set-output name=story_codes::{','.join(all_story_codes)}")
        print(f"::set-output name=channel::CH")
    
    print(f"\n=== Final Summary ===")
    print(f"Date: {args.date}")
    print(f"Categories: {', '.join(config.categories)}")
    print(f"Requested per category: {args.count}")
    print(f"Total Generated: {len(all_generated_stories)}")
    print(f"Total Failed: {all_failed_count}")
    print(f"Stories: {all_story_codes}")
    
    if len(all_generated_stories) == 0:
        print("❌ No stories generated, exiting with error")
        sys.exit(1)


if __name__ == '__main__':
    main()