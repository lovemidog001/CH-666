#!/usr/bin/env python3
"""Regenerate and upload images for an existing story JSON without creating a new story."""
import argparse, json, os, re, sys
from pathlib import Path
import main as pipeline

def output(values):
    path=os.getenv("GITHUB_OUTPUT")
    if path:
        with open(path,"a",encoding="utf-8") as f:
            for key,value in values.items():
                f.write(f"{key}={str(value).replace(chr(10),' ')}\n")

def run():
    parser=argparse.ArgumentParser()
    parser.add_argument("--story-code",required=True)
    parser.add_argument("--content-dir",default="content")
    args=parser.parse_args()
    if not re.fullmatch(r"CH-(?:333|666|999)-\d{4,}",args.story_code):
        raise ValueError("Invalid story code format")
    path=Path(args.content_dir)/"stories"/(args.story_code+".json")
    if not path.is_file():
        raise FileNotFoundError("Story JSON not found: "+str(path))
    story=json.loads(path.read_text(encoding="utf-8"))
    category=str(story.get("category",""))
    if category not in pipeline.CHANNELS:
        raise ValueError("Story category must be 3, 6, or 9")
    print("Repairing images for",args.story_code)
    images=pipeline.make_images(story,category,{"fantasy_level":story.get("fantasy_level","slightly_unreal")})
    if not images.get("cover") or not images.get("scene"):
        raise RuntimeError("Both images must generate and upload successfully; story JSON was not changed.")
    story["cover_image"]=re.sub(r"\s+","",images["cover"].strip())
    story["scene_images"]=re.sub(r"\s+","",images["scene"].strip())
    path.write_text(json.dumps(story,ensure_ascii=False,indent=2),encoding="utf-8")
    output({"generated_count":1,"failed_count":0,"story_codes":args.story_code})
    print("Updated JSON and uploaded both images for",args.story_code)

if __name__=="__main__":
    try: run()
    except Exception as exc:
        print("ERROR:",exc)
        output({"generated_count":0,"failed_count":1,"story_codes":""})
        sys.exit(1)
