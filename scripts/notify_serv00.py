import json
import requests
import sys
from typing import List
from pathlib import Path
import argparse


def notify_serv00(url: str, token: str, story_codes: List[str], content_dir: str) -> bool:
    """
    通知 Serv00 更新
    讀取 content/stories/ 下的完整故事 JSON，傳送完整故事物件陣列
    """
    if not url or not token:
        print("ERROR: SERV00_UPDATE_URL or SERV00_UPDATE_TOKEN not set")
        return False
    
    # 驗證 URL 格式
    if not url.startswith('https://') or not url.endswith('.php'):
        print(f"ERROR: SERV00_UPDATE_URL 格式錯誤，必須為 https://domain.com/api/update.php")
        print(f"       目前值: {url}")
        return False
    
    # 讀取完整故事資料
    stories = []
    stories_path = Path(content_dir) / 'stories'
    
    for code in story_codes:
        story_file = stories_path / f"{code}.json"
        if not story_file.exists():
            print(f"WARNING: Story file not found: {story_file}")
            continue
        try:
            with open(story_file, 'r', encoding='utf-8') as f:
                story = json.load(f)
                stories.append(story)
                print(f"  Loaded: {code}")
        except Exception as e:
            print(f"ERROR reading {story_file}: {e}")
            return False
    
    if not stories:
        print("ERROR: No valid stories to send")
        return False
    
    print(f"Total stories to send: {len(stories)}")
    for s in stories:
        print(f"  - {s.get('story_code', 'unknown')}: {s.get('title', 'no title')[:50]}")
    
    if not stories:
        print("ERROR: No valid stories to send")
        return False
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }
    
    payload = {
        'stories': stories,  # update.php 要求的格式
    }
    
    try:
        print(f"Notifying Serv00: {url}")
        print(f"  Stories count: {len(stories)}")
        
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        print(f"Response status: {response.status_code}")
        print(f"Response body: {response.text}")
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                print("Serv00 update successful")
                return True
            else:
                print(f"Serv00 update failed: {result.get('message', 'Unknown error')}")
                return False
        elif response.status_code == 404:
            print(f"❌ 404 Not Found: 請確認 SERV00_UPDATE_URL 正確")
            print(f"   正確格式: https://your-domain.com/api/update.php")
            print(f"   目前 URL: {url}")
            print(f"   回應: {response.text}")
            return False
        elif response.status_code == 401:
            print(f"❌ 401 Unauthorized: SERV00_UPDATE_TOKEN 錯誤或過期")
            return False
        elif response.status_code == 403:
            print(f"❌ 403 Forbidden: Token 無效或權限不足")
            return False
        else:
            print(f"HTTP error: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print("ERROR: Request timeout")
        return False
    except requests.exceptions.ConnectionError:
        print("ERROR: Connection error")
        return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Notify Serv00 of new stories')
    parser.add_argument('--url', required=True, help='SERV00_UPDATE_URL')
    parser.add_argument('--token', required=True, help='SERV00_UPDATE_TOKEN')
    parser.add_argument('--stories', required=True, help='Comma-separated story codes')
    parser.add_argument('--content-dir', required=True, help='Content directory path')
    
    args = parser.parse_args()
    
    story_codes = [s.strip() for s in args.stories.split(',') if s.strip()]
    
    if not story_codes:
        print("No story codes provided")
        sys.exit(1)
    
    success = notify_serv00(args.url, args.token, story_codes, args.content_dir)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()