import json
import argparse
import sys
from pathlib import Path
import requests


def notify_serv00(url: str, token: str, story_codes: str, content_dir: str) -> bool:
    """POST full stories to serv00 update.php."""
    storage_root = Path(content_dir)
    stories_dir = storage_root / 'stories'

    codes = [c.strip() for c in story_codes.split(',') if c.strip()]
    if not codes:
        print("No story codes to notify")
        return True

    stories = []
    for code in codes:
        path = stories_dir / f"{code}.json"
        if not path.exists():
            print(f"  ⚠️ Missing: {code}")
            continue
        try:
            story = json.loads(path.read_text(encoding='utf-8'))
            stories.append(story)
        except Exception as e:
            print(f"  ⚠️ Failed to read {code}: {e}")

    if not stories:
        print("No valid stories to send")
        return True

    payload = {'stories': stories}
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

    print(f"Posting {len(stories)} stories to {url}...")
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        result = resp.json()
        print(f"  ✅ serv00 response: {result.get('success', result)}")
        return True
    except requests.exceptions.HTTPError as e:
        print(f"  ❌ HTTP {e.response.status_code}: {e.response.text}")
        return False
    except Exception as e:
        print(f"  ❌ Notify failed: {e}")
        return False


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', required=True)
    parser.add_argument('--token', required=True)
    parser.add_argument('--stories', required=True)
    parser.add_argument('--content-dir', required=True)
    args = parser.parse_args()

    ok = notify_serv00(args.url, args.token, args.stories, args.content_dir)
    sys.exit(0 if ok else 1)