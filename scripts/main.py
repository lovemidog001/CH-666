#!/usr/bin/env python3
"""
ODDITY HUB / CH-666 每日故事生成主程式
支援多頻道：CH-666, CH-333, CH-999
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
    parser = argparse.ArgumentParser(description='CH-666/CH-333/CH-999 Daily Story Generation')
    parser.add_argument('--date', required=True, help='Target date (YYYY-MM-DD)')
    parser.add_argument('--count', type=int, default=5, help='Number of stories to generate per channel (default 5)')
    parser.add_argument('--config', required=True, help='Generation config path')
    parser.add_argument('--providers', required=True, help='AI providers config path')
    parser.add_argument('--channels', required=True, help='Channels config path')
    parser.add_argument('--content-dir', required=True, help='Content directory')
    parser.add_argument('--channel', default='CH-666', help='Channel code: CH-666, CH-333, CH-999 (default CH-666)')
    
    args = parser.parse_args()
    
    # 載入設定（指定頻道）
    config = Config(args.config, args.providers, args.channels, args.channel)
    channel_config = config.channel
    
    print(f"=== {args.channel} Generation for {args.date} ===")
    print(f"Requested: {args.count} stories")
    print(f"Channel: {channel_config['code']} ({channel_config.get('name', '')})")
    print(f"Genre: {channel_config.get('genre', '')}")
    print(f"Available providers: {len(config.providers)}")
    
    # 初始化組件
    news_fetcher = NewsFetcher(
        api_key='',  # 從環境變數讀取
        content_dir=args.content_dir
    )
    # 從環境變數取得 NEWSAPI_KEY
    import os
    news_fetcher.api_key = os.environ.get('NEWSAPI_KEY', '')
    
    seed_builder = SeedBuilder(args.content_dir)
    director = StoryDirector(channel_config)
    dice = DirectorDice(channel_config)
    # 除錯：印出 Provider 載入狀態
    print(f"  Loaded providers: {[(p['id'], p['name'], bool(os.environ.get(p['api_key_env']))) for p in config.providers]}")
    generator = StoryGenerator(config.providers, channel_config)
    validator = StoryValidator(channel_config)
    json_builder = JSONBuilder(channel_config, args.content_dir)
    saver = ContentSaver(args.content_dir, args.channel)
    
    # 1. 取得最新新聞（不限定日期）
    print("\n[1/8] Fetching latest news...")
    articles = news_fetcher.fetch_latest_news(max_results=args.count * 3)
    print(f"  Found {len(articles)} candidate articles")
    
    if not articles:
        print("  No articles available, exiting")
        log_result(args.date, args.count, 0, 0, 'none', [], args.channel)
        return
    
    # 2. 建立 Seeds 並去重
    print("\n[2/8] Building seeds...")
    seeds = []
    for article in articles[:args.count]:
        seed = seed_builder.build_seed(article, channel_config)
        seeds.append(seed)
        seed_builder.save_seed(seed)
    print(f"  Created {len(seeds)} seeds")
    
    # 3-7. 對每個 seed 生成故事
    generated_stories = []
    failed_count = 0
    provider_used = 'none'
    
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
                failed_count += 1
                continue
            
            provider_used = gen_result['provider_used']
            story_data = gen_result['story']
            print(f"    Generated: {story_data.get('title', '')[:40]}... via {provider_used}")
            
            # 6. 驗證
            print("  [6] Validating...")
            
            # 直接用 AI 產生的欄位建構 JSON（不再由 Python 提取標題/副標題）
            story_json = json_builder.build_story_json_from_ai(
                seed, story_data, dice_result, direction, provider_used
            )
            
            is_valid, errors = validator.validate(story_json)
            if not is_valid:
                print(f"    Validation failed: {errors}")
                failed_count += 1
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
            
            generated_stories.append(story_json)
            print(f"    Saved: {story_json['story_code']}")
            
        except Exception as e:
            print(f"    ERROR: {e}")
            import traceback
            traceback.print_exc()
            failed_count += 1
    
    # 8. 儲存每日合併 JSON
    print("\n[8] Saving daily merged JSON...")
    if generated_stories:
        saver.save_stories_merged(args.date, generated_stories)
        print(f"    Saved merged: {args.date}.json")
    
    # 9. 標記新聞來源為已使用
    print("\n[9] Marking sources as used...")
    news_fetcher.mark_sources_used([s for s in seeds if s.get('source_url')])
    
    # 提取 story codes 給日誌和 GitHub Actions
    story_codes = [s['story_code'] for s in generated_stories]
    
    # 記錄日誌
    log_result(
        args.date, 
        args.count, 
        len(generated_stories), 
        failed_count, 
        provider_used, 
        story_codes,
        args.channel
    )
    
    # 輸出給 GitHub Actions (新語法 GITHUB_OUTPUT)
    github_output = os.environ.get('GITHUB_OUTPUT')
    if github_output:
        with open(github_output, 'a', encoding='utf-8') as f:
            f.write(f"generated_count={len(generated_stories)}\n")
            f.write(f"failed_count={failed_count}\n")
            f.write(f"provider_used={provider_used}\n")
            f.write(f"story_codes={','.join(story_codes)}\n")
            f.write(f"channel={args.channel}\n")
    else:
        # 相容舊語法
        print(f"::set-output name=generated_count::{len(generated_stories)}")
        print(f"::set-output name=failed_count::{failed_count}")
        print(f"::set-output name=provider_used::{provider_used}")
        print(f"::set-output name=story_codes::{','.join(story_codes)}")
        print(f"::set-output name=channel::{args.channel}")
    
    print(f"\n=== Summary ===")
    print(f"Date: {args.date}")
    print(f"Channel: {args.channel}")
    print(f"Requested: {args.count}")
    print(f"Generated: {len(generated_stories)}")
    print(f"Failed: {failed_count}")
    print(f"Stories: {story_codes}")
    
    # 關鍵：若完全失敗，非零退出碼讓 Actions 顯示紅叉
    if len(generated_stories) == 0:
        print("❌ No stories generated, exiting with error")
        sys.exit(1)
    if failed_count == args.count:
        print("❌ All seeds failed, exiting with error")
        sys.exit(1)


def log_result(date: str, requested: int, generated: int, failed: int, 
               provider: str, stories: list, channel: str):
    """記錄執行結果（輸出 JSON 供 GitHub Actions 讀取）"""
    log_data = {
        'date': date,
        'channel': channel,
        'requested': requested,
        'generated': generated,
        'failed': failed,
        'provider_used': provider,
        'stories': stories,
    }
    github_output = os.environ.get('GITHUB_OUTPUT')
    if github_output:
        with open(github_output, 'a', encoding='utf-8') as f:
            f.write('log_data<<EOF\n')
            f.write(json.dumps(log_data, ensure_ascii=False) + '\n')
            f.write('EOF\n')
    else:
        # 相容舊語法
        print(f"::set-output name=log_data::{json.dumps(log_data, ensure_ascii=False)}")


if __name__ == '__main__':
    main()