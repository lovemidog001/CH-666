#!/usr/bin/env python3
"""CH-666 daily story pipeline. Real news only; no mock fallback."""
import argparse, base64, hashlib, json, os, random, re, sys, time
from datetime import datetime, timedelta, timezone
from ftplib import FTP
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
import requests

UTC=timezone.utc
CHANNELS={
"3":{"channel":"CH-333","name":"靈頻頻道","types":["possession","haunting","ritual","curse","mediumship","ancestral_sin","spirit_contract","exorcism","afterlife_glimpse","folk_belief"],"fantasy":["slightly_unreal","supernatural","reality_bending","mythic"],"styles":["first_person","third_person_limited","epistolary","found_footage","interview_transcript","diary_entry","ritual_record","oral_tradition"]},
"6":{"channel":"CH-666","name":"怪聞頻道","types":["psychological","urban_legend","supernatural","crime","suspense","identity_horror","sci_fi_horror","surveillance_horror","unknown_phenomenon","reality_horror"],"fantasy":["grounded","slightly_unreal","supernatural","reality_bending"],"styles":["first_person","third_person_limited","third_person_omniscient","epistolary","found_footage","interview_transcript","police_report","diary_entry"]},
"9":{"channel":"CH-999","name":"禁忌頻道","types":["cognitive_hazard","memetic","ontological","reality_horror","cosmic_horror","body_horror_extreme","time_loop","identity_horror","forbidden_knowledge","apocalyptic"],"fantasy":["supernatural","reality_bending","mythic","conceptual"],"styles":["first_person","third_person_omniscient","epistolary","found_footage","interview_transcript","police_report","research_log","fragmented_memory"]}}
ENDINGS=["open","twist","tragic","unsettling_resolution","cyclic","missing_ending"]
PACINGS=["slow_burn","steady","fast_paced","fragmented","disorienting"]
PERSPECTIVES=["victim","witness","investigator","bystander","entity","object"]

def log(s): print(s,flush=True)
def now_iso(): return datetime.now(UTC).isoformat().replace("+00:00","Z")
def output(vals):
    p=os.getenv("GITHUB_OUTPUT")
    if p:
        with open(p,"a",encoding="utf-8") as f:
            for k,v in vals.items(): f.write(f"{k}={str(v).replace(chr(10),' ')}\n")

def fetch_news(target,count):
    start=datetime.strptime(target,"%Y-%m-%d").replace(tzinfo=UTC)
    end=start+timedelta(days=1)
    query='(Taiwan OR 台灣 OR 高雄 OR 台北 OR 日本 OR 韓國) (mystery OR unusual OR missing OR strange OR 異常 OR 神秘 OR 失蹤 OR 詭異 OR 事故 OR 發現) sourcelang:Chinese'
    params={"query":query,"mode":"ArtList","format":"json","maxrecords":100,"sort":"DateDesc","startdatetime":start.strftime("%Y%m%d%H%M%S"),"enddatetime":(end-timedelta(seconds=1)).strftime("%Y%m%d%H%M%S")}
    r=requests.get("https://api.gdeltproject.org/api/v2/doc/doc",params=params,timeout=40,headers={"User-Agent":"CH666-story-pipeline/3.0"})
    r.raise_for_status()
    data=r.json()
    rows=[]; seen=set()
    for a in data.get("articles",[]) or []:
        url=(a.get("url") or "").strip(); title=re.sub(r"\s+"," ",(a.get("title") or "").strip())
        if not url or not title or url in seen or urlparse(url).scheme not in ("http","https"): continue
        seen.add(url); date=target; pub=a.get("seendate","")
        if len(pub)>=8: date=f"{pub[:4]}-{pub[4:6]}-{pub[6:8]}"
        rows.append({"source_title":title,"source_summary":(a.get("domain") or "")+" | "+pub,"source_content":"","source_url":url,"source_date":date,"source_location":"台灣/亞洲新聞","source_language":"zh","unusual_detail":title,"event":title,"people":[],"source_hash":hashlib.sha256((title+"|"+url).encode()).hexdigest()[:12],"event_hash":hashlib.sha256(re.sub(r"\W","",title.lower()).encode()).hexdigest()[:12]})
        if len(rows)>=count: break
    if len(rows)<count: log(f"WARNING: only {len(rows)} real articles found for {target}; no mock stories will be added.")
    return rows

def parse_json(s):
    s=(s or "").strip(); s=re.sub(r"^\x60\x60\x60(?:json)?\s*","",s); s=re.sub(r"\s*\x60\x60\x60$","",s)
    try: return json.loads(s)
    except ValueError:
        m=re.search(r"\{.*\}",s,re.S)
        if m:
            try: return json.loads(m.group(0))
            except ValueError: pass
    return None

def call_provider(name,prompt,system):
    if name=="nvidia":
        key=os.getenv("NVIDIA_API_KEY",""); url="https://integrate.api.nvidia.com/v1/chat/completions"; model=os.getenv("NVIDIA_MODEL","nvidia/nemotron-3-super-49b-v1")
    else:
        key=os.getenv("AGNES_API_KEY",""); url="https://apihub.agnes-ai.com/v1/chat/completions"; model=os.getenv("AGNES_MODEL","agnes-2.5-flash")
    if not key: raise RuntimeError(name+" API key missing")
    body={"model":model,"messages":[{"role":"system","content":system},{"role":"user","content":prompt}],"temperature":0.85,"max_tokens":6500,"stream":False}
    last=None
    for attempt in range(2):
        try:
            r=requests.post(url,headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"},json=body,timeout=180)
            if r.status_code in (429,500,502,503,504) and attempt==0: time.sleep(3); continue
            r.raise_for_status(); obj=r.json()
            story=parse_json(obj["choices"][0]["message"]["content"])
            if not story: raise RuntimeError("invalid JSON response")
            return story,model
        except Exception as e:
            last=e
            if attempt==0: time.sleep(2)
    raise RuntimeError(f"{name} failed: {last}")

def make_story(article,cat,dice):
    c=CHANNELS[cat]
    system="你是繁體中文原創怪談作家。新聞只能當抽象靈感，不得把真實新聞改寫成故事，不可使用真實人物或機構。只輸出 JSON。"
    prompt=f"""頻道：{c['channel']}（{c['name']}）
骰選：恐怖分數 {dice['horror_score']}/100；恐怖類型 {dice['horror_type']}；幻想等級 {dice['fantasy_level']}；敘事風格 {dice['narrative_style']}；節奏 {dice['pacing']}；結局 {dice['ending_type']}；視角 {dice['perspective']}。
新聞標題（只提取抽象概念，不得沿用措辭）：{article['source_title']}
新聞資訊：{article.get('source_summary','')}
以抽象概念為靈感，重新設計人物、虛構地點、因果規則、情節與結局。故事用繁體中文，至少 1200 個中文字，分段清楚，有鋪陳、轉折和不安結尾。不可寫成新聞，不可聲稱是真實事件。
純 JSON 格式：{{"title":"15至40字標題","subtitle":"頻道檔案副標題","slug":"lowercase-ascii-slug","summary":"80至160字摘要","content":"完整故事，以\\n分段","director_analysis":{{"anomaly_core":"異常核心","character_core":"角色核心","internal_rule":"異常規則"}}}}"""
    errors=[]
    for provider in ("nvidia","agnes"):
        try:
            story,model=call_provider(provider,prompt,system)
            if not str(story.get("title","")).strip() or not str(story.get("content","")).strip(): raise RuntimeError("missing title/content")
            if len(story["content"])<900: raise RuntimeError(f"story too short ({len(story['content'])} chars)")
            slug=re.sub(r"[^a-z0-9-]+","-",str(story.get("slug") or story["title"].lower())).strip("-")[:70].strip("-") or "case-"+article["source_hash"]
            story["slug"]=slug; story["subtitle"]=str(story.get("subtitle") or c["channel"]+" 檔案 // 未知異常"); story["summary"]=str(story.get("summary") or story["content"][:160])
            story["director_analysis"]=story.get("director_analysis") if isinstance(story.get("director_analysis"),dict) else {}
            return story,provider,model
        except Exception as e:
            log(f"  {provider} failed: {e}"); errors.append(str(e))
    raise RuntimeError("all text providers failed: "+"; ".join(errors))

def generate_image(prompt):
    """Generate with NVIDIA's documented FLUX NIM payload; reject blank images and retry."""
    key=os.getenv("NVIDIA_API_KEY","")
    if not key: raise RuntimeError("NVIDIA_API_KEY missing")
    url="https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.1-dev"
    from PIL import Image, ImageStat
    last_error=None
    for attempt in range(2):
        payload={"prompt":prompt,"mode":"base","seed":0 if attempt==0 else random.randint(1,2147483646),"steps":50,"cfg_scale":5.6}
        try:
            r=requests.post(url,headers={"Authorization":"Bearer "+key,"Accept":"application/json","Content-Type":"application/json"},json=payload,timeout=240)
            r.raise_for_status()
            data=r.json()
            artifacts=data.get("artifacts") or []
            encoded=(artifacts[0].get("base64") if artifacts else None) or data.get("image") or data.get("image_base64")
            if not encoded: raise RuntimeError("NVIDIA response contains no image base64; keys="+str(list(data.keys())))
            if encoded.startswith("data:"): encoded=encoded.split(",",1)[1]
            raw=base64.b64decode(encoded,validate=True)
            im=Image.open(BytesIO(raw)).convert("RGB")
            im.thumbnail((1024,1024))
            stats=ImageStat.Stat(im)
            mean=sum(stats.mean)/3
            variation=sum(stats.stddev)/3
            if mean<7 or variation<3:
                raise RuntimeError(f"image is blank/near-black (mean={mean:.1f}, variation={variation:.1f})")
            out=BytesIO()
            im.save(out,format="WEBP",quality=88,method=6)
            result=out.getvalue()
            check=Image.open(BytesIO(result)).convert("RGB")
            stats=ImageStat.Stat(check)
            if sum(stats.mean)/3<7 or sum(stats.stddev)/3<3:
                raise RuntimeError("WebP validation detected a blank/near-black image")
            return result
        except Exception as e:
            last_error=e
            log(f"  Image attempt {attempt+1}/2 failed: {e}")
            if attempt==0: time.sleep(2)
    raise RuntimeError(f"Image generation failed after retry: {last_error}")

def upload_image(filename,data):
    required=["FTP_HOST","FTP_USER","FTP_PASS","FTP_PATH","SITE_URL"]
    missing=[k for k in required if not os.getenv(k)]
    if missing: raise RuntimeError("missing FTP settings: "+", ".join(missing))
    ftp=FTP(os.environ["FTP_HOST"],timeout=45)
    try:
        ftp.login(os.environ["FTP_USER"],os.environ["FTP_PASS"])
        remote=os.environ["FTP_PATH"].strip("/")
        if remote: ftp.cwd(remote)
        ftp.storbinary("STOR "+filename,BytesIO(data))
    finally:
        try: ftp.quit()
        except Exception: pass
    site_url=re.sub(r"\s+","",os.environ["SITE_URL"].strip()).rstrip("/")
    return site_url+"/images/"+filename

def make_images(story,cat,dice):
    palette={"3":"warm candlelight, ritual shadows, aged paper","6":"phosphor green CRT glow, analog surveillance horror, VHS scanlines","9":"clinical black, warning red, impossible geometry"}[cat]
    prompts={"cover":f"Cinematic horror cover, no text, no letters, no watermark. {palette}. Symbolic scene inspired by {story['title']}. Ominous composition, realistic film still, square.",
             "scene":f"Cinematic horror still, no text, no letters, no watermark. {palette}. A key fictional scene inspired by {story['title']}. Fantasy level {dice['fantasy_level']}, uneasy atmosphere, square."}
    urls={"cover":"","scene":""}
    for kind,prompt in prompts.items():
        try:
            filename=f"{story['story_code']}_{kind}.webp"; urls[kind]=upload_image(filename,generate_image(prompt)); log("  Uploaded "+kind+" image")
        except Exception as e: log(f"  WARNING: {kind} image failed, story retained: {e}")
    return urls

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--date",default=(datetime.now(UTC)-timedelta(days=1)).strftime("%Y-%m-%d")); p.add_argument("--count",type=int,default=6)
    p.add_argument("--config"); p.add_argument("--providers"); p.add_argument("--channels"); p.add_argument("--content-dir",default="content"); p.add_argument("--skip-images",action="store_true")
    a=p.parse_args()
    datetime.strptime(a.date,"%Y-%m-%d")
    if not 1<=a.count<=12: raise SystemExit("--count must be 1..12")
    root=Path(a.content_dir); sd=root/"stories"; dd=root/"daily"; sd.mkdir(parents=True,exist_ok=True); dd.mkdir(parents=True,exist_ok=True)
    log(f"CH-666 pipeline | date={a.date} | requested={a.count}")
    articles=fetch_news(a.date,a.count)
    if not articles: raise RuntimeError("No real news returned; refusing to generate from mock data.")
    rng=random.SystemRandom(); cats=[rng.choice(["3","6","9"]) for _ in articles]
    counts={x:cats.count(x) for x in ("3","6","9")}
    log("Channel dice: "+", ".join(f"CH-{x*3}={counts[x]}" for x in ("3","6","9")))
    maxima={"3":0,"6":0,"9":0}
    for f in sd.glob("CH-*-*.json"):
        m=re.match(r"CH-(333|666|999)-(\d+)$",f.stem)
        if m:
            c={"333":"3","666":"6","999":"9"}[m.group(1)]; maxima[c]=max(maxima[c],int(m.group(2)))
    generated=[]; failed=0
    for i,article in enumerate(articles):
        cat=cats[i]; c=CHANNELS[cat]
        rr=random.Random(hashlib.sha256(f"{a.date}|{article['event_hash']}|{os.getenv('GITHUB_RUN_ID','manual')}".encode()).hexdigest())
        dice={"horror_score":rr.randint(20,98),"horror_type":rr.sample(c["types"],rr.randint(1,3)),"fantasy_level":rr.choice(c["fantasy"]),"narrative_style":rr.choice(c["styles"]),"pacing":rr.choice(PACINGS),"ending_type":rr.choice(ENDINGS),"perspective":rr.choice(PERSPECTIVES),"dice_seed":rr.randint(0,2**31-1)}
        log(f"[{i+1}/{len(articles)}] {c['channel']} | {article['source_title'][:80]}")
        try:
            ai,provider,model=make_story(article,cat,dice); maxima[cat]+=1; code=f"CH-{cat*3}-{maxima[cat]:04d}"
            story={"story_code":code,"category":cat,"channel":c["channel"],"title":ai["title"],"subtitle":ai["subtitle"],"slug":ai["slug"],"summary":ai["summary"],"content":ai["content"],"horror_score":dice["horror_score"],"horror_type":dice["horror_type"],"fantasy_level":dice["fantasy_level"],"narrative_style":dice["narrative_style"],"pacing":dice["pacing"],"ending_type":dice["ending_type"],"perspective":dice["perspective"],"source_date":article["source_date"],"source_hash":article["source_hash"],"event_hash":article["event_hash"],"source_url":article["source_url"],"provider_used":provider,"provider_model":model,"dice_seed":dice["dice_seed"],"director_analysis":ai["director_analysis"],"created_at":now_iso(),"cover_image":"","scene_images":""}
            if not a.skip_images:
                imgs=make_images(story,cat,dice); story["cover_image"]=imgs["cover"]; story["scene_images"]=imgs["scene"]
            (sd/f"{code}.json").write_text(json.dumps(story,ensure_ascii=False,indent=2),encoding="utf-8"); generated.append(story)
            log(f"  Saved {code}; content chars={len(story['content'])}")
        except Exception as e: failed+=1; log(f"  FAILED: {e}")
    payload={"date":a.date,"count":len(generated),"stories":generated,"generated_at":now_iso(),"channel_counts":counts}
    (dd/f"{a.date}.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    (dd/"latest.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    codes=",".join(s["story_code"] for s in generated); output({"generated_count":len(generated),"failed_count":failed,"story_codes":codes})
    log(f"Finished: generated={len(generated)}, failed={failed}, codes={codes or 'none'}")
    if not generated: raise RuntimeError("No stories generated successfully")

if __name__=="__main__":
    try: main()
    except Exception as e:
        log("FATAL: "+str(e)); output({"generated_count":0,"failed_count":1,"story_codes":""}); sys.exit(1)
